from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from datetime import date, datetime
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP
from typing import Any

from app.integrations.clinic.structural_transform import (
    StructuralTransformError,
    apply_structural_transforms,
    validate_structural_transform_schema,
)
from app.integrations.clinic.sync_contract import (
    ClinicRawSyncFetchRequest,
    ClinicRawSyncPage,
    ClinicRawSyncSource,
    ClinicSyncDomain,
    ClinicSyncFetchRequest,
    ClinicSyncPage,
    ClinicSyncSource,
    ExternalAppointmentSyncRecord,
    ExternalPatientSyncRecord,
    ExternalPaymentAllocationSyncRecord,
    ExternalPaymentSyncRecord,
)
from app.schemas.clinic_connector_mapping import (
    ClinicConnectorSchemaSnapshot,
    ClinicSyncMapping,
)


class ClinicMappedSyncError(ValueError):
    pass


@dataclass(frozen=True)
class ClinicSyncExtractionPlan:
    domain: ClinicSyncDomain
    target_sheets: tuple[str, ...]
    root_sheet: str
    raw_sheets: frozenset[str]
    transformations: tuple[Any, ...]


def sync_mapping_extraction_plan(
    mapping: ClinicSyncMapping, domain: ClinicSyncDomain
) -> ClinicSyncExtractionPlan:
    section = {
        ClinicSyncDomain.PATIENTS: mapping.patients,
        ClinicSyncDomain.APPOINTMENTS: mapping.appointments,
        ClinicSyncDomain.PAYMENTS: mapping.payments,
    }[domain]
    if section is None:
        raise ClinicMappedSyncError(
            f"Approved mapping does not configure {domain.value} sync."
        )

    transform_by_name = {item.name: item for item in mapping.transformations}
    relevant_names: set[str] = set()
    raw_sheets: set[str] = set()

    def collect(sheet: str) -> None:
        transform = transform_by_name.get(sheet)
        if transform is None:
            raw_sheets.add(sheet)
            return
        if transform.name in relevant_names:
            return
        relevant_names.add(transform.name)
        collect(transform.source_sheet)
        for join in transform.joins:
            collect(join.sheet)

    target_sheets = [section.sheet]
    if domain == ClinicSyncDomain.PAYMENTS and mapping.payment_allocations is not None:
        target_sheets.append(mapping.payment_allocations.sheet)
    for sheet in target_sheets:
        collect(sheet)

    root = section.sheet
    seen: set[str] = set()
    while root in transform_by_name:
        if root in seen:
            raise ClinicMappedSyncError("Connector transform source graph contains a cycle.")
        seen.add(root)
        root = transform_by_name[root].source_sheet
    if root not in raw_sheets:
        raw_sheets.add(root)

    transforms = tuple(
        item for item in mapping.transformations if item.name in relevant_names
    )
    return ClinicSyncExtractionPlan(
        domain=domain,
        target_sheets=tuple(target_sheets),
        root_sheet=root,
        raw_sheets=frozenset(raw_sheets),
        transformations=transforms,
    )


def sync_mapping_required_raw_columns(
    mapping: ClinicSyncMapping, domain: ClinicSyncDomain
) -> dict[str, frozenset[str]]:
    plan = sync_mapping_extraction_plan(mapping, domain)
    required: dict[str, set[str]] = {sheet: set() for sheet in plan.raw_sheets}
    transform_names = {item.name for item in mapping.transformations}

    def add_reference(alias_to_sheet: dict[str, str], reference: str) -> None:
        if "." not in reference:
            return
        alias, column = reference.split(".", 1)
        sheet = alias_to_sheet.get(alias)
        if sheet in required and sheet not in transform_names:
            required[sheet].add(column)

    for transform in plan.transformations:
        alias_to_sheet = {transform.source_alias: transform.source_sheet}
        for join in transform.joins:
            for key in join.on:
                add_reference(alias_to_sheet, key.left)
                if join.sheet in required and join.sheet not in transform_names:
                    required[join.sheet].add(key.right)
            alias_to_sheet[join.alias] = join.sheet
        for field in transform.fields:
            if field.source:
                add_reference(alias_to_sheet, field.source)
            for reference in field.sources:
                add_reference(alias_to_sheet, reference)
        for aggregate in transform.aggregates:
            if aggregate.source:
                add_reference(alias_to_sheet, aggregate.source)

    section = {
        ClinicSyncDomain.PATIENTS: mapping.patients,
        ClinicSyncDomain.APPOINTMENTS: mapping.appointments,
        ClinicSyncDomain.PAYMENTS: mapping.payments,
    }[domain]
    if section is not None and section.sheet in required:
        fields = {
            ClinicSyncDomain.PATIENTS: (
                "external_id", "first_name", "last_name", "phone", "gender",
                "birth_date", "status", "preferred_language", "source",
                "source_created_at", "source_updated_at",
            ),
            ClinicSyncDomain.APPOINTMENTS: (
                "external_id", "patient_external_id", "branch_external_id",
                "service_external_id", "doctor_external_id", "status", "start_at",
                "end_at", "status_at", "price_minor", "currency", "source_updated_at",
            ),
            ClinicSyncDomain.PAYMENTS: (
                "external_id", "patient_external_id", "transaction_type", "amount_minor",
                "currency", "payment_method", "created_at", "external_reference",
                "reference_payment_external_id",
            ),
        }[domain]
        for field_name in fields:
            column = getattr(section, field_name, None)
            if column:
                required[section.sheet].add(column)

    if domain == ClinicSyncDomain.PAYMENTS and mapping.payment_allocations is not None:
        allocation = mapping.payment_allocations
        if allocation.sheet in required:
            required[allocation.sheet].update(
                {allocation.payment_external_id, allocation.appointment_external_id, allocation.amount_minor}
            )

    return {sheet: frozenset(columns) for sheet, columns in required.items()}


def schema_fingerprint(snapshot: ClinicConnectorSchemaSnapshot) -> str:
    """Fingerprint structural schema only, never changing row/profile statistics."""

    payload = {
        "tables": [
            {
                "name": table.name,
                "columns": [
                    {
                        "name": column.name,
                        "kind": column.kind,
                        "nullable": column.nullable,
                        "primary_key": column.primary_key,
                        "references_table": column.references_table,
                        "references_column": column.references_column,
                    }
                    for column in sorted(table.columns, key=lambda item: item.name)
                ],
            }
            for table in sorted(snapshot.tables, key=lambda item: item.name)
        ]
    }
    encoded = json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
    return hashlib.sha256(encoded.encode("utf-8")).hexdigest()


def _schema_columns(snapshot: ClinicConnectorSchemaSnapshot) -> dict[str, set[str]]:
    return {table.name: {column.name for column in table.columns} for table in snapshot.tables}


def _column_refs(mapping: ClinicSyncMapping) -> list[tuple[str, str, str]]:
    refs: list[tuple[str, str, str]] = []
    sections: list[tuple[str, Any, tuple[str, ...]]] = [
        ("patients", mapping.patients, ("external_id", "first_name", "last_name", "phone", "gender", "birth_date", "status", "preferred_language", "source", "source_created_at", "source_updated_at")),
        ("appointments", mapping.appointments, ("external_id", "patient_external_id", "branch_external_id", "service_external_id", "doctor_external_id", "status", "start_at", "end_at", "status_at", "price_minor", "currency", "source_updated_at")),
        ("payments", mapping.payments, ("external_id", "patient_external_id", "transaction_type", "amount_minor", "currency", "payment_method", "created_at", "external_reference", "reference_payment_external_id")),
        ("payment_allocations", mapping.payment_allocations, ("payment_external_id", "appointment_external_id", "amount_minor")),
    ]
    for section_name, section, fields in sections:
        if section is None:
            continue
        for field in fields:
            column = getattr(section, field, None)
            if column:
                refs.append((section.sheet, f"{section_name}.{field}", column))
    for reference_name, reference in (
        ("branches", mapping.references.branches),
        ("services", mapping.references.services),
        ("doctors", mapping.references.doctors),
    ):
        if reference is None:
            continue
        refs.append((reference.sheet, f"references.{reference_name}.external_id", reference.external_id))
        if reference.label:
            refs.append((reference.sheet, f"references.{reference_name}.label", reference.label))
    return refs


def validate_sync_mapping_schema(
    mapping: ClinicSyncMapping,
    snapshot: ClinicConnectorSchemaSnapshot,
) -> None:
    columns = _schema_columns(snapshot)
    try:
        available = validate_structural_transform_schema(mapping.transformations, columns)
    except StructuralTransformError as exc:
        raise ClinicMappedSyncError(str(exc)) from exc
    for sheet, path, column in _column_refs(mapping):
        if sheet not in available:
            raise ClinicMappedSyncError(f"{path}: mapped sheet {sheet!r} does not exist in connector schema.")
        if column not in available[sheet]:
            raise ClinicMappedSyncError(
                f"{path}: mapped column {column!r} does not exist in sheet {sheet!r}."
            )


def _required_text(row: dict[str, Any], column: str, *, path: str) -> str:
    value = row.get(column)
    text = str(value).strip() if value is not None else ""
    if not text:
        raise ClinicMappedSyncError(f"{path}: source value is required.")
    return text


def _optional_text(row: dict[str, Any], column: str | None) -> str | None:
    if not column:
        return None
    value = row.get(column)
    if value is None:
        return None
    text = str(value).strip()
    return text or None


def _date_value(row: dict[str, Any], column: str | None, *, path: str) -> date | None:
    if not column:
        return None
    value = row.get(column)
    if value is None or (isinstance(value, str) and not value.strip()):
        return None
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date):
        return value
    try:
        return date.fromisoformat(str(value).strip())
    except ValueError as exc:
        raise ClinicMappedSyncError(f"{path}: expected an ISO date value.") from exc


def _datetime_value(row: dict[str, Any], column: str | None, *, path: str) -> datetime | None:
    if not column:
        return None
    value = row.get(column)
    if value is None or (isinstance(value, str) and not value.strip()):
        return None
    if isinstance(value, datetime):
        result = value
    else:
        text = str(value).strip()
        if text.endswith("Z"):
            text = text[:-1] + "+00:00"
        try:
            result = datetime.fromisoformat(text)
        except ValueError as exc:
            raise ClinicMappedSyncError(f"{path}: expected an ISO datetime value.") from exc
    if result.tzinfo is None or result.utcoffset() is None:
        raise ClinicMappedSyncError(f"{path}: datetime must include a timezone offset.")
    return result


def _minor_units(row: dict[str, Any], column: str, *, scale: int, path: str) -> int:
    value = row.get(column)
    if value is None or (isinstance(value, str) and not value.strip()):
        raise ClinicMappedSyncError(f"{path}: amount is required.")
    try:
        amount = Decimal(str(value).replace(",", "").strip()) * Decimal(scale)
    except (InvalidOperation, ValueError) as exc:
        raise ClinicMappedSyncError(f"{path}: expected a numeric amount.") from exc
    integral = amount.quantize(Decimal("1"), rounding=ROUND_HALF_UP)
    if amount != integral:
        raise ClinicMappedSyncError(
            f"{path}: amount_scale={scale} does not produce exact integer minor units."
        )
    result = int(integral)
    if result < 0:
        raise ClinicMappedSyncError(f"{path}: amount cannot be negative.")
    return result


def _rows(materialized: dict[str, list[dict[str, Any]]], sheet: str) -> list[dict[str, Any]]:
    if sheet not in materialized:
        raise ClinicMappedSyncError(f"Mapped sheet {sheet!r} is unavailable in connector page.")
    return materialized[sheet]


def canonicalize_raw_sync_page(
    *,
    raw_page: ClinicRawSyncPage,
    mapping: ClinicSyncMapping,
    expected_schema_fingerprint: str,
) -> ClinicSyncPage:
    if raw_page.schema_fingerprint != expected_schema_fingerprint:
        raise ClinicMappedSyncError(
            "Connector schema changed after mapping approval. Re-run schema discovery and approve a new mapping."
        )
    sheets = {name: [dict(row) for row in rows] for name, rows in raw_page.tables.items()}
    try:
        plan = sync_mapping_extraction_plan(mapping, raw_page.domain)
        materialized, _summary = apply_structural_transforms(sheets, list(plan.transformations))
    except StructuralTransformError as exc:
        raise ClinicMappedSyncError(str(exc)) from exc

    records: list[Any] = []
    if raw_page.domain == ClinicSyncDomain.PATIENTS:
        section = mapping.patients
        if section is None:
            raise ClinicMappedSyncError("Approved mapping does not configure patient sync.")
        for index, row in enumerate(_rows(materialized, section.sheet)):
            records.append(
                ExternalPatientSyncRecord(
                    external_id=_required_text(row, section.external_id, path=f"patients[{index}].external_id"),
                    first_name=_required_text(row, section.first_name, path=f"patients[{index}].first_name"),
                    last_name=_optional_text(row, section.last_name),
                    phone=_optional_text(row, section.phone),
                    gender=_optional_text(row, section.gender),
                    birth_date=_date_value(row, section.birth_date, path=f"patients[{index}].birth_date"),
                    status=_optional_text(row, section.status) or section.default_status,
                    preferred_language=_optional_text(row, section.preferred_language) or section.default_preferred_language,
                    source=_optional_text(row, section.source) or section.default_source,
                    source_created_at=_datetime_value(row, section.source_created_at, path=f"patients[{index}].source_created_at"),
                    source_updated_at=_datetime_value(row, section.source_updated_at, path=f"patients[{index}].source_updated_at"),
                )
            )
    elif raw_page.domain == ClinicSyncDomain.APPOINTMENTS:
        section = mapping.appointments
        if section is None:
            raise ClinicMappedSyncError("Approved mapping does not configure appointment sync.")
        for index, row in enumerate(_rows(materialized, section.sheet)):
            price_minor = (
                _minor_units(row, section.price_minor, scale=section.price_scale, path=f"appointments[{index}].price_minor")
                if section.price_minor else None
            )
            start_at = _datetime_value(row, section.start_at, path=f"appointments[{index}].start_at")
            end_at = _datetime_value(row, section.end_at, path=f"appointments[{index}].end_at")
            if start_at is None or end_at is None:
                raise ClinicMappedSyncError(
                    f"appointments[{index}]: start_at and end_at are required."
                )
            records.append(
                ExternalAppointmentSyncRecord(
                    external_id=_required_text(row, section.external_id, path=f"appointments[{index}].external_id"),
                    patient_external_id=_required_text(row, section.patient_external_id, path=f"appointments[{index}].patient_external_id"),
                    branch_external_id=_required_text(row, section.branch_external_id, path=f"appointments[{index}].branch_external_id"),
                    service_external_id=_required_text(row, section.service_external_id, path=f"appointments[{index}].service_external_id"),
                    doctor_external_id=_required_text(row, section.doctor_external_id, path=f"appointments[{index}].doctor_external_id"),
                    status=_required_text(row, section.status, path=f"appointments[{index}].status"),
                    start_at=start_at,
                    end_at=end_at,
                    status_at=_datetime_value(row, section.status_at, path=f"appointments[{index}].status_at"),
                    price_minor=price_minor,
                    currency=_optional_text(row, section.currency) or section.default_currency,
                    source_updated_at=_datetime_value(row, section.source_updated_at, path=f"appointments[{index}].source_updated_at"),
                )
            )
    elif raw_page.domain == ClinicSyncDomain.PAYMENTS:
        section = mapping.payments
        if section is None:
            raise ClinicMappedSyncError("Approved mapping does not configure payment sync.")
        allocations_by_payment: dict[str, list[ExternalPaymentAllocationSyncRecord]] = {}
        alloc = mapping.payment_allocations
        if alloc is not None:
            merged: dict[tuple[str, str], int] = {}
            for index, row in enumerate(_rows(materialized, alloc.sheet)):
                payment_id = _required_text(row, alloc.payment_external_id, path=f"allocations[{index}].payment_external_id")
                appointment_id = _required_text(row, alloc.appointment_external_id, path=f"allocations[{index}].appointment_external_id")
                amount = _minor_units(row, alloc.amount_minor, scale=alloc.amount_scale, path=f"allocations[{index}].amount_minor")
                merged[(payment_id, appointment_id)] = merged.get((payment_id, appointment_id), 0) + amount
            for (payment_id, appointment_id), amount in sorted(merged.items()):
                allocations_by_payment.setdefault(payment_id, []).append(
                    ExternalPaymentAllocationSyncRecord(
                        appointment_external_id=appointment_id,
                        amount_minor=amount,
                    )
                )
        for index, row in enumerate(_rows(materialized, section.sheet)):
            external_id = _required_text(row, section.external_id, path=f"payments[{index}].external_id")
            created_at = _datetime_value(row, section.created_at, path=f"payments[{index}].created_at")
            assert created_at is not None
            records.append(
                ExternalPaymentSyncRecord(
                    external_id=external_id,
                    patient_external_id=_required_text(row, section.patient_external_id, path=f"payments[{index}].patient_external_id"),
                    transaction_type=_optional_text(row, section.transaction_type) or section.default_transaction_type,
                    amount_minor=_minor_units(row, section.amount_minor, scale=section.amount_scale, path=f"payments[{index}].amount_minor"),
                    currency=_optional_text(row, section.currency) or section.default_currency,
                    payment_method=_optional_text(row, section.payment_method) or section.default_payment_method,
                    created_at=created_at,
                    external_reference=_optional_text(row, section.external_reference),
                    reference_payment_external_id=_optional_text(row, section.reference_payment_external_id),
                    allocations=tuple(allocations_by_payment.get(external_id, [])),
                )
            )
    else:
        raise ClinicMappedSyncError("Unsupported connector sync domain.")

    return ClinicSyncPage(
        domain=raw_page.domain,
        records=tuple(records),
        cursor=raw_page.cursor,
        next_cursor=raw_page.next_cursor,
        source_revision=raw_page.source_revision,
        has_more=raw_page.has_more,
    )


class MappedClinicSyncSource(ClinicSyncSource):
    def __init__(
        self,
        *,
        source: ClinicRawSyncSource,
        mapping: ClinicSyncMapping,
        schema_fingerprint_value: str,
    ) -> None:
        self.source = source
        self.mapping = mapping
        self.schema_fingerprint_value = schema_fingerprint_value

    @property
    def sync_domains(self) -> frozenset[ClinicSyncDomain]:
        mapped = {
            domain
            for domain, section in (
                (ClinicSyncDomain.PATIENTS, self.mapping.patients),
                (ClinicSyncDomain.APPOINTMENTS, self.mapping.appointments),
                (ClinicSyncDomain.PAYMENTS, self.mapping.payments),
            )
            if section is not None
        }
        return frozenset(mapped & set(self.source.raw_sync_domains))

    def fetch_sync_page(self, request: ClinicSyncFetchRequest) -> ClinicSyncPage:
        if request.domain not in self.sync_domains:
            raise ClinicMappedSyncError(
                f"Approved connector mapping does not expose {request.domain.value} sync."
            )
        raw = self.source.fetch_raw_sync_page(
            ClinicRawSyncFetchRequest(
                domain=request.domain,
                cursor=request.cursor,
                limit=request.limit,
            )
        )
        return canonicalize_raw_sync_page(
            raw_page=raw,
            mapping=self.mapping,
            expected_schema_fingerprint=self.schema_fingerprint_value,
        )
