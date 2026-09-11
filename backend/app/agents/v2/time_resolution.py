from __future__ import annotations

from datetime import date, time, timedelta
from typing import Literal

from app.agents.v2.semantic_context import SemanticContext
from app.agents.v2.turn_contract import (
    DateConstraint,
    Selection,
    TiaTurnUnderstanding,
    TimeConstraint,
)

BoundaryKind = Literal["lower", "upper", "exact"]


def _minutes(value: str) -> int:
    parsed = time.fromisoformat(value)
    return parsed.hour * 60 + parsed.minute


def _clock(minutes: int) -> str:
    normalized = minutes % (24 * 60)
    return f"{normalized // 60:02d}:{normalized % 60:02d}"


def _twelve_hour_candidates(value: str) -> tuple[int, int]:
    base = _minutes(value)
    alternate = (base + 12 * 60) % (24 * 60)
    return base, alternate


def _operating_hours(context: SemanticContext) -> list[dict[str, object]]:
    raw = context.model_input.get("clinic_operating_hours")
    if not isinstance(raw, list):
        return []
    return [dict(row) for row in raw if isinstance(row, dict)]


def _relevant_weekdays(constraint: DateConstraint | None) -> set[int] | None:
    if constraint is None or constraint.mode in {"from_date", "next_available"}:
        return None
    if constraint.start_date is None:
        return None

    start = date.fromisoformat(constraint.start_date)
    if constraint.mode == "exact":
        return {start.weekday()}
    if constraint.mode != "range" or constraint.end_date is None:
        return None

    end = date.fromisoformat(constraint.end_date)
    span = (end - start).days
    if span >= 6:
        return set(range(7))
    return {(start + timedelta(days=offset)).weekday() for offset in range(span + 1)}


def _candidate_is_open(
    candidate_minutes: int,
    *,
    rows: list[dict[str, object]],
    weekdays: set[int] | None,
    boundary: BoundaryKind,
) -> bool:
    for row in rows:
        weekday = row.get("weekday")
        if not isinstance(weekday, int):
            continue
        if weekdays is not None and weekday not in weekdays:
            continue
        start = str(row.get("start") or "")[:5]
        end = str(row.get("end") or "")[:5]
        if len(start) != 5 or len(end) != 5:
            continue
        try:
            start_minutes = _minutes(start)
            end_minutes = _minutes(end)
        except ValueError:
            continue
        if boundary == "upper":
            if start_minutes < candidate_minutes <= end_minutes:
                return True
        elif start_minutes <= candidate_minutes < end_minutes:
            return True
    return False


def _resolve_boundary(
    value: str | None,
    ambiguity: str,
    *,
    rows: list[dict[str, object]],
    weekdays: set[int] | None,
    boundary: BoundaryKind,
) -> tuple[str | None, str]:
    if value is None:
        return None, "none"
    if ambiguity != "twelve_hour":
        return value, "none"
    if not rows:
        return None, "twelve_hour"

    valid = [
        candidate
        for candidate in dict.fromkeys(_twelve_hour_candidates(value))
        if _candidate_is_open(
            candidate,
            rows=rows,
            weekdays=weekdays,
            boundary=boundary,
        )
    ]
    if len(valid) != 1:
        return None, "twelve_hour"
    return _clock(valid[0]), "none"


def _active_task_date(context: SemanticContext) -> DateConstraint | None:
    raw_task = context.model_input.get("active_task")
    if not isinstance(raw_task, dict):
        return None
    task_type = raw_task.get("task_type")
    if task_type == "booking":
        raw_constraints = raw_task.get("constraints")
    elif task_type == "reschedule":
        raw_constraints = raw_task.get("replacement")
    else:
        return None
    if not isinstance(raw_constraints, dict):
        return None
    raw_date = raw_constraints.get("date")
    if not isinstance(raw_date, dict):
        return None
    try:
        return DateConstraint.model_validate(raw_date)
    except ValueError:
        return None


def resolve_time_constraint_by_clinic_hours(
    constraint: TimeConstraint | None,
    *,
    date_constraint: DateConstraint | None,
    context: SemanticContext,
) -> TimeConstraint | None:
    """Resolve only structurally-declared 12-hour ambiguity using verified clinic hours.

    No customer text is inspected here. If operating hours do not produce exactly one
    valid AM/PM candidate, the time is cleared so downstream planning cannot execute
    or filter availability using an arbitrary period guess.
    """
    if constraint is None:
        return None
    rows = _operating_hours(context)
    weekdays = _relevant_weekdays(date_constraint)

    start_boundary: BoundaryKind = "upper" if constraint.mode == "before" else "lower"
    if constraint.mode == "exact":
        start_boundary = "exact"
    resolved_start, start_ambiguity = _resolve_boundary(
        constraint.start_time,
        constraint.start_time_ambiguity,
        rows=rows,
        weekdays=weekdays,
        boundary=start_boundary,
    )
    if constraint.start_time is not None and resolved_start is None:
        return None

    resolved_end = constraint.end_time
    end_ambiguity = constraint.end_time_ambiguity
    if constraint.mode == "range":
        resolved_end, end_ambiguity = _resolve_boundary(
            constraint.end_time,
            constraint.end_time_ambiguity,
            rows=rows,
            weekdays=weekdays,
            boundary="upper",
        )
        if constraint.end_time is not None and resolved_end is None:
            return None

    return constraint.model_copy(
        update={
            "start_time": resolved_start,
            "end_time": resolved_end,
            "start_time_ambiguity": start_ambiguity,
            "end_time_ambiguity": end_ambiguity,
        }
    )


def _resolve_selection(
    selection: Selection | None,
    *,
    date_constraint: DateConstraint | None,
    context: SemanticContext,
) -> Selection | None:
    if selection is None or selection.kind != "time" or selection.time is None:
        return selection
    if selection.time_ambiguity != "twelve_hour":
        return selection

    resolved, ambiguity = _resolve_boundary(
        selection.time,
        selection.time_ambiguity,
        rows=_operating_hours(context),
        weekdays=_relevant_weekdays(date_constraint),
        boundary="exact",
    )
    if resolved is None:
        return None
    return selection.model_copy(update={"time": resolved, "time_ambiguity": ambiguity})


def resolve_turn_times_by_clinic_hours(
    turn: TiaTurnUnderstanding,
    context: SemanticContext,
) -> TiaTurnUnderstanding:
    """Normalize semantic clock ambiguity before deterministic planning."""
    inherited_date = _active_task_date(context)
    operations = []
    for operation in turn.operations:
        date_constraint = operation.entities.date or inherited_date
        resolved_time = resolve_time_constraint_by_clinic_hours(
            operation.entities.time,
            date_constraint=date_constraint,
            context=context,
        )
        entities = operation.entities.model_copy(update={"time": resolved_time})
        selection = _resolve_selection(
            operation.selection,
            date_constraint=date_constraint,
            context=context,
        )
        operations.append(
            operation.model_copy(update={"entities": entities, "selection": selection})
        )
    return turn.model_copy(update={"operations": operations})
