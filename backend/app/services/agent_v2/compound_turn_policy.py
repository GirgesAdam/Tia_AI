from __future__ import annotations

from datetime import date, datetime, time, timedelta
from typing import Any
from zoneinfo import ZoneInfo

from app.services.agent_v2.planner import PlanStep, TurnPlan
from app.services.agent_v2.read_executor import ReadExecutionBundle, ReadResult

_PACKAGE_DEPENDENCY_FACT = "depends_on_package_purchase_operation_index"
_COMPOUND_SEQUENCE_FACT = "compound_visit_sequenced"
_COMPOUND_SEQUENCE_INDEX_FACT = "compound_visit_sequence_index"
_COMPOUND_ANCHOR_FACT = "compound_visit_anchor_local"
_COMPOUND_WRITE_GROUP_FACT = "compound_write_group"
_COMPOUND_GROUPED_FACT = "compound_visit_grouped"


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
        if _write_kind(step) != "booking" or step.write_intent is None:
            tagged.append(step)
            continue
        matches = [purchase for purchase in purchases if _same_package_scope(purchase, step)]
        if len(matches) == 1:
            dependency = matches[0]
            dependencies[step.operation_index] = dependency.operation_index
            parameters = {
                **step.write_intent.parameters,
                # If the same turn is buying the entitlement that this booking uses,
                # never silently fall back to standalone if the purchase cannot complete.
                "package_usage": "use_existing",
            }
            step = step.model_copy(
                update={
                    "write_intent": step.write_intent.model_copy(update={"parameters": parameters}),
                    "facts": {
                        **step.facts,
                        "package_usage": "use_existing",
                        _PACKAGE_DEPENDENCY_FACT: dependency.operation_index,
                    },
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


def _retime_booking(
    step: PlanStep,
    *,
    local_start: datetime,
    anchor: datetime,
    sequence_index: int,
    mode: str,
) -> PlanStep:
    assert step.write_intent is not None
    original_params = dict(step.write_intent.parameters)
    raw_date = original_params.get("date")
    raw_time = original_params.get("time")
    assert isinstance(raw_date, dict)
    assert isinstance(raw_time, dict)
    date_constraint = {
        **raw_date,
        "mode": "exact",
        "start_date": local_start.date().isoformat(),
        "end_date": None,
    }
    time_constraint = {
        **raw_time,
        "mode": mode,
        "start_time": local_start.time().isoformat(timespec="minutes"),
        "end_time": None,
        "start_time_ambiguity": "none",
        "end_time_ambiguity": "none",
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
                "exact_time_requested": mode == "exact",
                _COMPOUND_SEQUENCE_FACT: True,
                _COMPOUND_SEQUENCE_INDEX_FACT: sequence_index,
                _COMPOUND_ANCHOR_FACT: anchor.isoformat(timespec="minutes"),
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
        for sequence_index, (step, duration) in enumerate(zip(ordered, durations, strict=True)):
            replacements[step.operation_index] = _retime_booking(
                step,
                local_start=cursor,
                anchor=anchor,
                sequence_index=sequence_index,
                mode="exact" if sequence_index == 0 else "after",
            )
            cursor += timedelta(minutes=duration)

    return [replacements.get(step.operation_index, step) for step in steps]



def _tag_compound_write_group(steps: list[PlanStep]) -> list[PlanStep]:
    """Tag a multi-service booking and any package purchases it depends on as one write group."""
    bookings = [step for step in steps if _write_kind(step) == "booking"]
    service_ids = {
        str(_write_parameters(step).get("service_id"))
        for step in bookings
        if _write_parameters(step).get("service_id")
    }
    if len(bookings) < 2 or len(service_ids) < 2:
        return steps

    group_key = "compound:" + ",".join(str(step.operation_index) for step in bookings)
    purchase_indexes = {
        int(step.facts[_PACKAGE_DEPENDENCY_FACT])
        for step in bookings
        if step.facts.get(_PACKAGE_DEPENDENCY_FACT) is not None
    }
    tagged: list[PlanStep] = []
    for step in steps:
        if step in bookings or step.operation_index in purchase_indexes:
            step = step.model_copy(
                update={
                    "facts": {
                        **step.facts,
                        _COMPOUND_WRITE_GROUP_FACT: group_key,
                        _COMPOUND_GROUPED_FACT: True,
                    }
                }
            )
        tagged.append(step)
    return tagged


def compound_write_group(step: PlanStep) -> str | None:
    value = step.facts.get(_COMPOUND_WRITE_GROUP_FACT)
    return str(value) if value not in (None, "") else None


def normalize_compound_turn_plan(
    plan: TurnPlan,
    *,
    catalog: dict[str, Any],
) -> TurnPlan:
    """Normalize dependencies and same-anchor bookings without inspecting customer text.

    Package purchases are ordered before bookings that canonically depend on the same
    service/device entitlement. Multiple exact bookings sharing one requested local
    start are treated as one visit anchor. The first remains exact; later bookings are
    converted to "first available after" constraints. Runtime re-reads availability
    after each successful write, so buffers, doctor/device conflicts, and appointments
    created earlier in the same turn are authoritative.
    """
    if plan.handoff_category is not None or len(plan.steps) < 2:
        return plan
    steps = _tag_and_order_package_dependencies(list(plan.steps))
    steps = _tag_compound_write_group(steps)
    steps = _sequence_shared_anchor_bookings(steps, catalog=catalog)
    return plan.model_copy(update={"steps": steps})


def compound_sequence_index(step: PlanStep) -> int | None:
    raw = step.facts.get(_COMPOUND_SEQUENCE_INDEX_FACT)
    if raw is None:
        return None
    try:
        return int(raw)
    except (TypeError, ValueError):
        return None


def compound_anchor_key(step: PlanStep) -> str | None:
    value = step.facts.get(_COMPOUND_ANCHOR_FACT)
    return str(value) if value not in (None, "") else None


def apply_compound_runtime_cursor(
    step: PlanStep,
    *,
    previous_end_at: datetime | None,
    timezone_name: str,
) -> PlanStep:
    """Move a later visit booking to start searching at the actual prior session end."""
    sequence_index = compound_sequence_index(step)
    if sequence_index is None or sequence_index < 1 or previous_end_at is None:
        return step
    anchor_raw = compound_anchor_key(step)
    if anchor_raw is None:
        return step
    try:
        anchor = datetime.fromisoformat(anchor_raw)
        local_cursor = previous_end_at.astimezone(ZoneInfo(timezone_name))
    except (ValueError, TypeError):
        return step
    return _retime_booking(
        step,
        local_start=local_cursor.replace(tzinfo=None),
        anchor=anchor,
        sequence_index=sequence_index,
        mode="after",
    )


def _availability_results(reads: ReadExecutionBundle) -> list[tuple[int, ReadResult]]:
    return [
        (index, result)
        for index, result in enumerate(reads.results)
        if result.kind == "availability"
    ]


def _slot_start(slot: dict[str, object]) -> datetime:
    return datetime.fromisoformat(str(slot["start_at"]))


def _clarification_field(step: PlanStep) -> str:
    params = _write_parameters(step)
    if "doctor_id" not in params:
        return "doctor"
    if bool(step.facts.get("service_requires_laser_device")) and "device_key" not in params:
        return "device"
    return "selection"


def resolve_compound_followup_after_reads(
    step: PlanStep,
    reads: ReadExecutionBundle,
) -> tuple[PlanStep, ReadExecutionBundle, bool]:
    """Promote a later compound booking from the earliest live verified slot.

    This runs only for sequence items after the first. Availability is read after
    earlier writes in the same transaction, so a pre-existing or just-created conflict
    automatically pushes the booking to the next valid slot instead of overlapping it.
    """
    sequence_index = compound_sequence_index(step)
    if (
        sequence_index is None
        or sequence_index < 1
        or _write_kind(step) != "booking"
        or step.write_intent is None
    ):
        return step, reads, False

    availability_results = _availability_results(reads)
    if not availability_results:
        return step, reads, False
    result_index, availability = availability_results[0]
    raw_slots = availability.payload.get("slots")
    slots = [dict(slot) for slot in raw_slots if isinstance(slot, dict)] if isinstance(raw_slots, list) else []
    if not slots:
        blocked = step.model_copy(
            update={
                "disposition": "blocked",
                "response_goal": "no_availability",
            }
        )
        return blocked, reads, True

    earliest_start = min(_slot_start(slot) for slot in slots)
    earliest = [slot for slot in slots if _slot_start(slot) == earliest_start]
    if len(earliest) != 1:
        field = _clarification_field(step)
        clarified = step.model_copy(
            update={
                "disposition": "clarify",
                "clarification_field": field,
                "response_goal": "ask_doctor_choice" if field == "doctor" else "clarification",
            }
        )
        return clarified, reads, True

    selected = earliest[0]
    start_local = datetime.fromisoformat(str(selected["start_local"]))
    exact_date = {
        "mode": "exact",
        "start_date": start_local.date().isoformat(),
        "end_date": None,
    }
    exact_time = {
        "mode": "exact",
        "start_time": start_local.strftime("%H:%M"),
        "end_time": None,
        "start_time_ambiguity": "none",
        "end_time_ambiguity": "none",
    }
    parameters = {
        **step.write_intent.parameters,
        "branch_id": selected["branch_id"],
        "service_id": selected["service_id"],
        "doctor_id": selected["doctor_id"],
        "start_at": selected["start_at"],
        "date": exact_date,
        "time": exact_time,
    }
    device_key = selected.get("laser_device_key")
    if device_key:
        parameters["device_key"] = device_key

    narrowed_results = list(reads.results)
    narrowed_payload = {
        **availability.payload,
        "slots": [selected],
        "matching_slot_count": 1,
    }
    narrowed_results[result_index] = availability.model_copy(update={"payload": narrowed_payload})
    narrowed_reads = reads.model_copy(update={"results": narrowed_results})

    advanced = step.model_copy(
        update={
            "disposition": "write_ready",
            "write_intent": step.write_intent.model_copy(update={"parameters": parameters}),
            "response_goal": "booking_completed",
            "facts": {
                **step.facts,
                "date": exact_date,
                "time": exact_time,
                "exact_time_requested": True,
                "compound_visit_selected_start_local": start_local.isoformat(),
            },
        }
    )
    return advanced, narrowed_reads, True


def completed_compound_booking_end(reads: ReadExecutionBundle) -> datetime | None:
    """Return the verified selected slot end for the cursor after a successful write."""
    for _index, result in _availability_results(reads):
        raw_slots = result.payload.get("slots")
        if not isinstance(raw_slots, list) or len(raw_slots) != 1:
            continue
        slot = raw_slots[0]
        if not isinstance(slot, dict) or not slot.get("end_at"):
            continue
        try:
            return datetime.fromisoformat(str(slot["end_at"]))
        except ValueError:
            continue
    return None
