from __future__ import annotations

from collections import defaultdict
from datetime import date, datetime, time
from decimal import Decimal, InvalidOperation
from typing import Any, Iterable

from app.schemas.clinic_import import (
    StructuralAggregateMapping,
    StructuralFieldMapping,
    StructuralTransformMapping,
)

MAX_TRANSFORM_ROWS = 50_000


class StructuralTransformError(ValueError):
    pass


def _clean_key_part(value: Any) -> str | None:
    if value is None:
        return None
    if isinstance(value, (datetime, date, time)):
        return value.isoformat()
    if isinstance(value, Decimal):
        return format(value.normalize(), "f")
    text = str(value).strip()
    return text or None


def _qualified(alias: str, row: dict[str, Any]) -> dict[str, Any]:
    return {f"{alias}.{column}": value for column, value in row.items()}


def _reference_value(row: dict[str, Any], reference: str, *, path: str) -> Any:
    if "." not in reference:
        raise StructuralTransformError(
            f"{path}: structural reference {reference!r} must use alias.column syntax."
        )
    if reference not in row:
        raise StructuralTransformError(
            f"{path}: structural reference {reference!r} is unavailable."
        )
    return row[reference]


def _join_key(row: dict[str, Any], refs: Iterable[str], *, path: str) -> tuple[str, ...] | None:
    values: list[str] = []
    for ref in refs:
        value = _clean_key_part(_reference_value(row, ref, path=path))
        if value is None:
            return None
        values.append(value)
    return tuple(values)


def _right_key(row: dict[str, Any], columns: Iterable[str], *, path: str) -> tuple[str, ...] | None:
    values: list[str] = []
    for column in columns:
        if column not in row:
            raise StructuralTransformError(
                f"{path}: join column {column!r} does not exist in the right-hand sheet."
            )
        value = _clean_key_part(row.get(column))
        if value is None:
            return None
        values.append(value)
    return tuple(values)


def _apply_enum_mapping(value: Any, field: StructuralFieldMapping, *, path: str) -> Any:
    if not field.enum_map or value is None:
        return value
    raw = str(value).strip()
    lookup = raw if field.enum_case_sensitive else raw.casefold()
    mapping = (
        field.enum_map
        if field.enum_case_sensitive
        else {str(key).strip().casefold(): mapped for key, mapped in field.enum_map.items()}
    )
    if lookup in mapping:
        return mapping[lookup]
    if field.unmapped == "keep":
        return value
    if field.unmapped == "default":
        return field.default
    raise StructuralTransformError(
        f"{path}: value {value!r} is not present in enum_map for field {field.name!r}."
    )


def _field_value(row: dict[str, Any], field: StructuralFieldMapping, *, path: str) -> Any:
    field_path = f"{path}.field:{field.name}"
    if field.kind == "column":
        value = _reference_value(row, field.source or "", path=field_path)
    elif field.kind == "coalesce":
        value = None
        for reference in field.sources:
            candidate = _reference_value(row, reference, path=field_path)
            if candidate is not None and (not isinstance(candidate, str) or candidate.strip()):
                value = candidate
                break
    elif field.kind == "concat":
        parts = []
        for reference in field.sources:
            candidate = _reference_value(row, reference, path=field_path)
            if candidate is not None and str(candidate).strip():
                parts.append(str(candidate).strip())
        value = field.separator.join(parts) if parts else None
    else:
        value = field.value
    return _apply_enum_mapping(value, field, path=field_path)


def _decimal(value: Any, *, path: str) -> Decimal:
    if value is None or (isinstance(value, str) and not value.strip()):
        return Decimal("0")
    try:
        return Decimal(str(value).replace(",", "").strip())
    except (InvalidOperation, ValueError) as exc:
        raise StructuralTransformError(
            f"{path}: aggregate sum requires numeric values, got {value!r}."
        ) from exc


def _aggregate(rows: list[dict[str, Any]], aggregate: StructuralAggregateMapping, *, path: str) -> Any:
    source = aggregate.source
    if aggregate.operation == "count":
        if not source:
            return len(rows)
        return sum(
            1
            for row in rows
            if _reference_value(row, source, path=path) is not None
        )

    assert source is not None
    values = [_reference_value(row, source, path=path) for row in rows]
    non_null = [value for value in values if value is not None]
    if aggregate.operation == "sum":
        total = sum((_decimal(value, path=path) for value in non_null), Decimal("0"))
        return total
    if not non_null:
        return None
    if aggregate.operation == "min":
        return min(non_null)
    if aggregate.operation == "max":
        return max(non_null)
    raise StructuralTransformError(f"{path}: unsupported aggregate {aggregate.operation!r}.")


def _transform_one(
    sheets: dict[str, list[dict[str, Any]]],
    transform: StructuralTransformMapping,
    *,
    known_columns: dict[str, set[str]],
) -> list[dict[str, Any]]:
    path = f"transform:{transform.name}"
    if transform.source_sheet not in sheets:
        raise StructuralTransformError(
            f"{path}: source sheet {transform.source_sheet!r} does not exist."
        )

    working = [
        _qualified(transform.source_alias, row)
        for row in sheets[transform.source_sheet]
    ]

    for join in transform.joins:
        join_path = f"{path}.join:{join.alias}"
        if join.sheet not in sheets:
            raise StructuralTransformError(
                f"{join_path}: sheet {join.sheet!r} does not exist."
            )
        right_rows = sheets[join.sheet]
        right_sheet_columns = set(known_columns.get(join.sheet, set()))
        right_sheet_columns.update(column for row in right_rows for column in row)
        index: dict[tuple[str, ...], list[dict[str, Any]]] = defaultdict(list)
        right_columns = [key.right for key in join.on]
        for row in right_rows:
            key = _right_key(row, right_columns, path=join_path)
            if key is not None:
                index[key].append(row)
        if join.cardinality == "one":
            ambiguous = next((key for key, rows in index.items() if len(rows) > 1), None)
            if ambiguous is not None:
                raise StructuralTransformError(
                    f"{join_path}: expected one right-hand row per join key, but key {ambiguous!r} "
                    "matches multiple rows. Use cardinality='many' only when row expansion is intended."
                )

        expanded: list[dict[str, Any]] = []
        left_refs = [key.left for key in join.on]
        for left_row in working:
            key = _join_key(left_row, left_refs, path=join_path)
            matches = index.get(key, []) if key is not None else []
            if not matches:
                if join.how == "left":
                    merged = dict(left_row)
                    merged.update({f"{join.alias}.{column}": None for column in right_sheet_columns})
                    expanded.append(merged)
                continue
            for right_row in matches:
                merged = dict(left_row)
                merged.update(_qualified(join.alias, right_row))
                expanded.append(merged)
                if len(expanded) > MAX_TRANSFORM_ROWS:
                    raise StructuralTransformError(
                        f"{join_path}: transformed row count exceeds safety limit {MAX_TRANSFORM_ROWS}."
                    )
        working = expanded

    if not transform.aggregates:
        return [
            {
                field.name: _field_value(row, field, path=path)
                for field in transform.fields
            }
            for row in working
        ]

    grouped: dict[tuple[Any, ...], list[dict[str, Any]]] = defaultdict(list)
    projected_group_values: dict[tuple[Any, ...], dict[str, Any]] = {}
    group_fields = [
        next(field for field in transform.fields if field.name == name)
        for name in transform.group_by
    ]
    for row in working:
        values = {
            field.name: _field_value(row, field, path=path)
            for field in group_fields
        }
        key = tuple(_clean_key_part(values[name]) for name in transform.group_by)
        grouped[key].append(row)
        projected_group_values.setdefault(key, values)

    output: list[dict[str, Any]] = []
    for key, rows in grouped.items():
        item = dict(projected_group_values[key])
        for aggregate in transform.aggregates:
            item[aggregate.name] = _aggregate(
                rows,
                aggregate,
                path=f"{path}.aggregate:{aggregate.name}",
            )
        output.append(item)
    return output


def apply_structural_transforms(
    sheets: dict[str, list[dict[str, Any]]],
    transforms: list[StructuralTransformMapping],
) -> tuple[dict[str, list[dict[str, Any]]], dict[str, int]]:
    """Materialize deterministic virtual sheets without mutating raw input sheets."""

    materialized = {name: list(rows) for name, rows in sheets.items()}
    known_columns = {
        name: {column for row in rows for column in row}
        for name, rows in materialized.items()
    }
    produced: dict[str, int] = {}
    for transform in transforms:
        if transform.name in materialized:
            raise StructuralTransformError(
                f"transform:{transform.name}: output name conflicts with an existing sheet."
            )
        rows = _transform_one(
            materialized,
            transform,
            known_columns=known_columns,
        )
        if len(rows) > MAX_TRANSFORM_ROWS:
            raise StructuralTransformError(
                f"transform:{transform.name}: transformed row count exceeds safety limit {MAX_TRANSFORM_ROWS}."
            )
        materialized[transform.name] = rows
        known_columns[transform.name] = {
            *(field.name for field in transform.fields),
            *(aggregate.name for aggregate in transform.aggregates),
        }
        produced[transform.name] = len(rows)
    return materialized, produced


def validate_structural_transform_schema(
    transforms: list[StructuralTransformMapping],
    columns_by_sheet: dict[str, set[str]],
) -> dict[str, set[str]]:
    """Validate transform references against an uploaded schema snapshot.

    Returns raw + virtual sheet columns so ordinary mapping fields can reference
    transform outputs during onboarding confirmation.
    """

    available = {name: set(columns) for name, columns in columns_by_sheet.items()}
    for transform in transforms:
        path = f"transform:{transform.name}"
        if transform.name in available:
            raise StructuralTransformError(
                f"{path}: output name conflicts with an existing sheet."
            )
        if transform.source_sheet not in available:
            raise StructuralTransformError(
                f"{path}: source sheet {transform.source_sheet!r} does not exist."
            )
        aliases: dict[str, set[str]] = {
            transform.source_alias: available[transform.source_sheet]
        }
        for join in transform.joins:
            if join.sheet not in available:
                raise StructuralTransformError(
                    f"{path}.join:{join.alias}: sheet {join.sheet!r} does not exist."
                )
            for key in join.on:
                alias, column = _split_reference(key.left, path=f"{path}.join:{join.alias}")
                if alias not in aliases or column not in aliases[alias]:
                    raise StructuralTransformError(
                        f"{path}.join:{join.alias}: left reference {key.left!r} does not exist."
                    )
                if key.right not in available[join.sheet]:
                    raise StructuralTransformError(
                        f"{path}.join:{join.alias}: right column {key.right!r} does not exist."
                    )
            aliases[join.alias] = available[join.sheet]

        for field in transform.fields:
            refs: list[str] = []
            if field.source:
                refs.append(field.source)
            refs.extend(field.sources)
            for ref in refs:
                alias, column = _split_reference(ref, path=f"{path}.field:{field.name}")
                if alias not in aliases or column not in aliases[alias]:
                    raise StructuralTransformError(
                        f"{path}.field:{field.name}: reference {ref!r} does not exist."
                    )
        for aggregate in transform.aggregates:
            if aggregate.source:
                alias, column = _split_reference(
                    aggregate.source, path=f"{path}.aggregate:{aggregate.name}"
                )
                if alias not in aliases or column not in aliases[alias]:
                    raise StructuralTransformError(
                        f"{path}.aggregate:{aggregate.name}: reference {aggregate.source!r} does not exist."
                    )
        available[transform.name] = {
            *(field.name for field in transform.fields),
            *(aggregate.name for aggregate in transform.aggregates),
        }
    return available


def _split_reference(reference: str, *, path: str) -> tuple[str, str]:
    if "." not in reference:
        raise StructuralTransformError(
            f"{path}: structural reference {reference!r} must use alias.column syntax."
        )
    alias, column = reference.split(".", 1)
    if not alias or not column:
        raise StructuralTransformError(
            f"{path}: invalid structural reference {reference!r}."
        )
    return alias, column
