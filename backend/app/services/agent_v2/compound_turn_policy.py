from __future__ import annotations

from datetime import date, datetime, time, timedelta
from typing import Any

from app.services.agent_v2.planner import PlanStep, ReadRequest, TurnPlan

_PACKAGE_DEPENDENCY_FACT = "depends_on_package_purchase_operation_index"
_COMPOUND_SEQUENCE_FACT = "compound_visit_sequenced"


def _write_kind(step: PlanStep) -> str | None:
    return step.write_intent.kind if step.write_intent is not None else None


def _write_parameters(step: PlanStep) -> dict[str, object]:
    return dict(step.write_intent.parameters) if step.write_intent is not None else {}


def _same_package_scope(purchase: PlanStep, booking: PlanStep) -> bool:
    purchase_params = _write_parameters(purchase)
    booking_params = _write_parameters(booking)
    if booking_params.get("package_usage") == "avoid_existing":
        return False
    purchase_service = purchase_params.get("service_id")
    booking_service = booking_params.get("service_id")
    if not purchase_service or str(purchase_service) != str(booking_service):
        return False
    purchase_device = purchase_params.get("device_key")
    booking_device = booking_params.get("device_key")
    if purchase_device in (None, "") and booking_device in (None, ""):
        return True
    return bool(purchase_device and booking_device and str(purchase_device) == str(booking_device))


def _tag_and_order_package_dependencies(steps: list[PlanStep]) -> list[PlanStep]:
    purchases = [step for step in steps if _write_kind(step) == "buy_package"]
    tagged: list[PlanStep] = []
    dependencies: dict[int, int] = {}
    for step in steps:
        if _write_kind(step) != "booking":
            tagged.append(step)
            continue
        matches = [purchase for purchase in purchases if _same_package_scope(purchase, step)]
        if len(matches) == 1:
            dependency = matches[0]
            dependencies[step.operation_index] = dependency.operation_index
            step = step.model_copy(
                update={
                    "facts": {
                        **step.facts,
                        _PACKAGE_DEPENDENCY_FACT: dependency.operation_index,
                    }
                }
            )
        tagged.append(step)

    # Stable dependency ordering. Only move a purchase in front of a booking that
    # canonically depends on the same service/device package entitlement.
    ordered = list(tagged)
    for booking_index, purchase_index in dependencies.items():
        booking_pos = next(
            (index for index, step in enumerate(ordered) if step.operation_index == booking_index),
            None,
        )
        purchase_pos = next(
            (index for index, step in enumerate(ordered) if step.operation_index == purchase_index),
            None,
        )
        if booking_pos is None or purchase_pos is None or purchase_pos < booking_pos:
            continue
        purchase = ordered.pop(purchase_pos)
        booking_pos = next(
            index for index, step in enumerate(ordered) if step.operation_index == booking_index
        )
        ordered.insert(booking_pos, purchase)
    return ordered


def _service_duration_minutes(catalog: dict[str, Any], service_id: object) -> int | None:
    rows = catalog.get("services")
    if not isinstance(rows, list):
        return None
    for row in rows:
        if not isinstance(row, dict) or str(row.get("id")) != str(service_id):
            continue
        try:
            duration = int(row.get("duration_minutes"))
        except (TypeError, ValueError):
            return None
        return duration if duration > 0 else None
    return None


def _exact_anchor(step: PlanStep) -> datetime | None:
    if _write_kind(step) != "booking" or step.write_intent is None:
        return None
    params = step.write_intent.parameters
    raw_date = params.get("date")
    raw_time = params.get("time")
    if not isinstance(raw_date, dict) or raw_date.get("mode") != "exact":
        return None
    if not isinstance(raw_time, dict) or raw_time.get("mode") != "exact":
        return None
    start_date = raw_date.get("start_date")
    start_time = raw_time.get("start_time")
    if not isinstance(start_date, str) or not isinstance(start_time, str):
        return None
    try:
        return datetime.combine(date.fromisoformat(start_date), time.fromisoformat(start_time))
    except ValueError:
        return None


def _retime_booking(step: PlanStep, *, local_start: datetime, anchor: datetime) -> PlanStep:
    assert step.write_intent is not None
    original_params = dict(step.write_intent.parameters)
    raw_date = original_params.get("date")
    raw_time = original_params.get("time")
    assert isinstance(raw_date, dict)
    assert isinstance(raw_time, dict)
    date_constraint = {
        **raw_date,
        "start_date": local_start.date().isoformat(),
    }
    time_constraint = {
        **raw_time,
        "start_time": local_start.time().isoformat(timespec="minutes"),
    }
    parameters = {
        **original_params,
        "date": date_constraint,
        "time": time_constraint,
    }
    reads = [
        request.model_copy(
            update={
                "parameters": {
                    **request.parameters,
                    "date": date_constraint,
                    "time": time_constraint,
                }
            }
        )
        if request.kind == "availability"
        else request
        for request in step.reads
    ]
    return step.model_copy(
        update={
            "reads": reads,
            "write_intent": step.write_intent.model_copy(update={"parameters": parameters}),
            "facts": {
                **step.facts,
                "date": date_constraint,
                "time": time_constraint,
                _COMPOUND_SEQUENCE_FACT: True,
                "compound_visit_anchor_local": anchor.isoformat(timespec="minutes"),
            },
        }
    )


def _sequence_shared_anchor_bookings(
    steps: list[PlanStep],
    *,
    catalog: dict[str, Any],
) -> list[PlanStep]:
    groups: dict[datetime, list[PlanStep]] = {}
    for step in steps:
        anchor = _exact_anchor(step)
        if anchor is not None:
            groups.setdefault(anchor, []).append(step)

    replacements: dict[int, PlanStep] = {}
    for anchor, group in groups.items():
        if len(group) < 2:
            continue
        ordered = sorted(group, key=lambda step: step.operation_index)
        durations: list[int] = []
        for step in ordered:
            assert step.write_intent is not None
            duration = _service_duration_minutes(
                catalog,
                step.write_intent.parameters.get("service_id"),
            )
            if duration is None:
                durations = []
                break
            durations.append(duration)
        if not durations:
            continue

        cursor = anchor
        for step, duration in zip(ordered, durations, strict=True):
            replacements[step.operation_index] = _retime_booking(
                step,
                local_start=cursor,
                anchor=anchor,
            )
            cursor += timedelta(minutes=duration)

    return [replacements.get(step.operation_index, step) for step in steps]


def normalize_compound_turn_plan(
    plan: TurnPlan,
    *,
    catalog: dict[str, Any],
) -> TurnPlan:
    """Normalize dependencies and same-anchor bookings without inspecting customer text.

    Package purchases are ordered before bookings that canonically depend on the same
    service/device entitlement. Multiple exact bookings sharing one requested local
    start are treated as one visit anchor and placed back-to-back using canonical
    service durations; every shifted booking is still verified against availability.
    """
    if plan.handoff_category is not None or len(plan.steps) < 2:
        return plan
    steps = _tag_and_order_package_dependencies(list(plan.steps))
    steps = _sequence_shared_anchor_bookings(steps, catalog=catalog)
    return plan.model_copy(update={"steps": steps})


def apply_completed_package_dependency(
    step: PlanStep,
    *,
    completed_write_results: dict[int, dict[str, object]],
) -> tuple[PlanStep, bool]:
    """Attach the exact package created earlier in this turn to its dependent booking.

    Returns ``(step, dependency_ready)``. A missing/failed dependency is fail-closed so
    the booking cannot silently become a standalone session.
    """
    raw_dependency = step.facts.get(_PACKAGE_DEPENDENCY_FACT)
    if raw_dependency is None or _write_kind(step) != "booking" or step.write_intent is None:
        return step, True
    try:
        dependency_index = int(raw_dependency)
    except (TypeError, ValueError):
        return step, False
    result = completed_write_results.get(dependency_index)
    if result is None or result.get("ok") is not True:
        return step, False
    package_id = result.get("patient_package_id")
    if not package_id:
        return step, False
    parameters = {
        **step.write_intent.parameters,
        "package_id": str(package_id),
        "package_usage": "use_existing",
    }
    return step.model_copy(
        update={
            "write_intent": step.write_intent.model_copy(update={"parameters": parameters}),
            "facts": {**step.facts, "package_usage": "use_existing"},
        }
    ), True
