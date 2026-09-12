from __future__ import annotations

from datetime import UTC, date, datetime, timedelta
from typing import Any
from uuid import UUID
from zoneinfo import ZoneInfo

from app.integrations.clinic.base import AvailabilityRequest, AvailabilityResult, AvailabilitySlot
from app.integrations.clinic.registry import get_clinic_adapter
from app.models.service import Service
from app.services.agent_v2.compound_turn_policy import compound_anchor_key, compound_sequence_index
from app.services.agent_v2.planner import PlanStep, TurnPlan
from app.services.agent_v2.read_executor import ReadExecutionContext

_SEARCH_DAYS = 14
_SEQUENCE_FACT_KEYS = frozenset(
    {
        "compound_visit_sequenced",
        "compound_visit_sequence_index",
        "compound_visit_anchor_local",
        "compound_visit_selected_start_local",
    }
)


def _write_kind(step: PlanStep) -> str | None:
    return step.write_intent.kind if step.write_intent is not None else None


def _params(step: PlanStep) -> dict[str, object]:
    return dict(step.write_intent.parameters) if step.write_intent is not None else {}


def _strip_sequence_facts(facts: dict[str, object]) -> dict[str, object]:
    return {key: value for key, value in facts.items() if key not in _SEQUENCE_FACT_KEYS}


def _service_buffers(context: ReadExecutionContext, service_id: object) -> tuple[int, int]:
    """Read native Tia service buffers when available; external adapters safely fall back to zero."""
    try:
        service_uuid = UUID(str(service_id))
        row = context.db.get(Service, service_uuid)
    except Exception:
        return 0, 0
    if row is None or getattr(row, "workspace_id", None) != context.workspace.id:
        return 0, 0
    return int(row.buffer_before_minutes or 0), int(row.buffer_after_minutes or 0)


def _slot_interval_minutes(results: list[AvailabilityResult]) -> int:
    differences: list[int] = []
    for result in results:
        starts = sorted({slot.start_at for slot in result.slots})
        for left, right in zip(starts, starts[1:]):
            minutes = int((right - left).total_seconds() // 60)
            if minutes > 0:
                differences.append(minutes)
    return min(differences) if differences else 15


def _ceil_local(value: datetime, interval_minutes: int, timezone_name: str) -> datetime:
    local = value.astimezone(ZoneInfo(timezone_name))
    midnight = local.replace(hour=0, minute=0, second=0, microsecond=0)
    elapsed = int((local - midnight).total_seconds() // 60)
    remainder = elapsed % interval_minutes
    if remainder == 0 and local.second == 0 and local.microsecond == 0:
        return local.astimezone(UTC)
    rounded = local + timedelta(minutes=interval_minutes - remainder)
    return rounded.replace(second=0, microsecond=0).astimezone(UTC)


def _same_resource(left: AvailabilitySlot, right: AvailabilitySlot) -> bool:
    if left.doctor_id == right.doctor_id:
        return True
    return bool(
        left.laser_device_key
        and right.laser_device_key
        and left.laser_device_key == right.laser_device_key
    )


def _required_next_start(
    selected: list[AvailabilitySlot],
    *,
    next_service_id: object,
    context: ReadExecutionContext,
    interval_minutes: int,
    timezone_name: str,
    candidate_resource: AvailabilitySlot,
) -> datetime:
    previous = selected[-1]
    required = previous.end_at
    next_before, _next_after = _service_buffers(context, next_service_id)
    next_before_delta = timedelta(minutes=next_before)
    for prior in selected:
        if not _same_resource(prior, candidate_resource):
            continue
        _prior_before, prior_after = _service_buffers(context, prior.service_id)
        resource_required = prior.end_at + timedelta(minutes=prior_after) + next_before_delta
        if resource_required > required:
            required = resource_required
    return _ceil_local(required, interval_minutes, timezone_name)


def _chain_for_first(
    first: AvailabilitySlot,
    results: list[AvailabilityResult],
    steps: list[PlanStep],
    *,
    context: ReadExecutionContext,
    timezone_name: str,
) -> list[AvailabilitySlot] | None:
    selected = [first]
    interval = _slot_interval_minutes(results)
    for result, step in zip(results[1:], steps[1:], strict=True):
        params = _params(step)
        matches: list[AvailabilitySlot] = []
        for slot in result.slots:
            required = _required_next_start(
                selected,
                next_service_id=params.get("service_id"),
                context=context,
                interval_minutes=interval,
                timezone_name=timezone_name,
                candidate_resource=slot,
            )
            if slot.start_at == required:
                matches.append(slot)
        if not matches:
            return None
        matches.sort(key=lambda slot: (slot.start_at, slot.doctor_id, slot.laser_device_key or ""))
        selected.append(matches[0])
    return selected


def _availability_for_day(
    steps: list[PlanStep],
    *,
    booking_date: date,
    context: ReadExecutionContext,
) -> list[AvailabilityResult] | None:
    adapter = context.adapter or get_clinic_adapter(db=context.db, workspace=context.workspace)
    branch_default = context.workspace.primary_branch_id
    results: list[AvailabilityResult] = []
    for step in steps:
        params = _params(step)
        service_id = params.get("service_id")
        doctor_id = params.get("doctor_id")
        branch_id = params.get("branch_id") or branch_default
        if service_id is None or doctor_id is None or branch_id is None:
            return None
        if bool(step.facts.get("service_requires_laser_device")) and not params.get("device_key"):
            return None
        result = adapter.get_availability(
            AvailabilityRequest(
                branch_id=str(branch_id),
                service_id=str(service_id),
                booking_date=booking_date,
                doctor_id=str(doctor_id),
                now=context.now,
                laser_device_key=str(params["device_key"]) if params.get("device_key") else None,
            )
        )
        results.append(result)
    return results


def _find_joint_chain(
    steps: list[PlanStep],
    *,
    requested_anchor: datetime,
    context: ReadExecutionContext,
    timezone_name: str,
) -> tuple[list[AvailabilitySlot] | None, bool]:
    tz = ZoneInfo(timezone_name)
    anchor_aware = requested_anchor.replace(tzinfo=tz).astimezone(UTC)
    for offset in range(_SEARCH_DAYS):
        current_date = requested_anchor.date() + timedelta(days=offset)
        results = _availability_for_day(steps, booking_date=current_date, context=context)
        if results is None:
            return None, False
        first_slots = sorted(
            (
                slot
                for slot in results[0].slots
                if offset > 0 or slot.start_at >= anchor_aware
            ),
            key=lambda slot: (slot.start_at, slot.doctor_id, slot.laser_device_key or ""),
        )
        for first in first_slots:
            chain = _chain_for_first(
                first,
                results,
                steps,
                context=context,
                timezone_name=timezone_name,
            )
            if chain is not None:
                return chain, first.start_at == anchor_aware
    return None, False


def _constraints_for_slot(slot: AvailabilitySlot, timezone_name: str) -> tuple[dict[str, object], dict[str, object]]:
    local = slot.start_at.astimezone(ZoneInfo(timezone_name))
    return (
        {"mode": "exact", "start_date": local.date().isoformat(), "end_date": None},
        {
            "mode": "exact",
            "start_time": local.strftime("%H:%M"),
            "end_time": None,
            "start_time_ambiguity": "none",
            "end_time_ambiguity": "none",
        },
    )


def _rewrite_step_for_slot(
    step: PlanStep,
    slot: AvailabilitySlot,
    *,
    timezone_name: str,
    requested_anchor: datetime,
    allow_write: bool,
) -> PlanStep:
    date_constraint, time_constraint = _constraints_for_slot(slot, timezone_name)
    base_params = _params(step)
    parameters: dict[str, object] = {
        **base_params,
        "branch_id": slot.branch_id,
        "service_id": slot.service_id,
        "doctor_id": slot.doctor_id,
        "date": date_constraint,
        "time": time_constraint,
    }
    if slot.laser_device_key:
        parameters["device_key"] = slot.laser_device_key
    reads = [
        request.model_copy(
            update={
                "parameters": {
                    **request.parameters,
                    **parameters,
                }
            }
        )
        if request.kind == "availability"
        else request
        for request in step.reads
    ]
    facts = {
        **_strip_sequence_facts(step.facts),
        "date": date_constraint,
        "time": time_constraint,
        "exact_time_requested": allow_write,
        "compound_visit_preflight_resolved": True,
        "compound_visit_requested_anchor_local": requested_anchor.isoformat(timespec="minutes"),
        "compound_visit_alternative": not allow_write,
    }
    write_intent = None
    if allow_write and step.write_intent is not None:
        write_intent = step.write_intent.model_copy(update={"parameters": parameters})
    return step.model_copy(
        update={
            "disposition": "read",
            "reads": reads,
            "write_intent": write_intent,
            "state_action": step.state_action if allow_write else "none",
            "response_goal": step.response_goal if allow_write else "present_availability",
            "facts": facts,
        }
    )


def _suppress_group_write(step: PlanStep, *, requested_anchor: datetime) -> PlanStep:
    return step.model_copy(
        update={
            "disposition": "blocked",
            "reads": [],
            "write_intent": None,
            "state_action": "none",
            "response_goal": "no_availability",
            "facts": {
                **_strip_sequence_facts(step.facts),
                "compound_visit_preflight_resolved": True,
                "compound_visit_no_joint_window": True,
                "compound_visit_requested_anchor_local": requested_anchor.isoformat(timespec="minutes"),
                "compound_visit_search_days": _SEARCH_DAYS,
            },
        }
    )


def preflight_compound_visit_plan(
    plan: TurnPlan,
    *,
    context: ReadExecutionContext,
    timezone_name: str,
) -> TurnPlan:
    """Resolve a same-visit booking group before any business write is allowed.

    If the customer's exact anchor can fit the full ordered visit, every booking is
    rewritten to the verified exact chain and normal per-step verification/writes may
    proceed. If the exact anchor cannot fit the whole group, no booking is allowed to
    write; the nearest joint window is returned as read-only availability instead.
    This prevents partial visits such as booking service A and only then discovering
    that service B cannot follow it.
    """
    groups: dict[str, list[PlanStep]] = {}
    for step in plan.steps:
        if _write_kind(step) != "booking":
            continue
        anchor = compound_anchor_key(step)
        sequence = compound_sequence_index(step)
        if anchor is None or sequence is None:
            continue
        groups.setdefault(anchor, []).append(step)
    if not groups:
        return plan

    replacements: dict[int, PlanStep] = {}
    for anchor_raw, group in groups.items():
        if len(group) < 2:
            continue
        try:
            requested_anchor = datetime.fromisoformat(anchor_raw)
        except ValueError:
            continue
        ordered = sorted(group, key=lambda step: compound_sequence_index(step) or 0)
        chain, exact_anchor_fits = _find_joint_chain(
            ordered,
            requested_anchor=requested_anchor,
            context=context,
            timezone_name=timezone_name,
        )
        if chain is None:
            for step in ordered:
                replacements[step.operation_index] = _suppress_group_write(
                    step,
                    requested_anchor=requested_anchor,
                )
            continue
        for step, slot in zip(ordered, chain, strict=True):
            replacements[step.operation_index] = _rewrite_step_for_slot(
                step,
                slot,
                timezone_name=timezone_name,
                requested_anchor=requested_anchor,
                allow_write=exact_anchor_fits,
            )

    if not replacements:
        return plan
    return plan.model_copy(
        update={
            "steps": [replacements.get(step.operation_index, step) for step in plan.steps],
        }
    )
