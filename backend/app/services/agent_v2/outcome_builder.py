from __future__ import annotations

from typing import Any

from app.agents.availability_presentation import availability_windows_from_slots
from app.agents.v2.semantic_context import SemanticContext
from app.agents.v2.turn_contract import TiaTurnUnderstanding
from app.services.agent_v2.outcome import OutcomeChoice, ResponseGoal, TurnOutcome
from app.services.agent_v2.planner import PlanStep, TurnPlan
from app.services.agent_v2.read_executor import ReadExecutionBundle, ReadResult


class OutcomeBuildError(RuntimeError):
    pass


_INTERNAL_KEYS = frozenset(
    {
        "id",
        "workspace_id",
        "patient_id",
        "appointment_id",
        "service_id",
        "doctor_id",
        "branch_id",
        "package_id",
        "package_offer_id",
        "patient_package_id",
        "purchase_transaction_id",
        "reference_transaction_id",
        "transaction_id",
        "external_id",
        "package_external_id",
        "laser_device_key",
        "device_key",
        "doctor_ids",
        "service_ids",
        "branch_ids",
    }
)


def _money(minor: object, currency: object) -> str | None:
    if minor is None or not currency:
        return None
    try:
        value = int(minor)
    except (TypeError, ValueError):
        return None
    return f"{value / 100:.2f} {str(currency).upper()}"


def _visible_dict(value: dict[str, Any]) -> dict[str, object]:
    currency = value.get("currency") or value.get("service_currency")
    visible: dict[str, object] = {}
    for key, item in value.items():
        if key in _INTERNAL_KEYS or key.endswith("_ids"):
            continue
        if key.endswith("_id"):
            continue
        if key.endswith("_minor") and currency:
            converted = _money(item, currency)
            if converted is not None:
                visible[key.removesuffix("_minor")] = converted
            continue
        if key == "billing_context":
            visible["billing"] = "package" if item == "package_prepaid" else "standard"
            continue
        normalized = _visible_value(item)
        if normalized not in (None, {}, []):
            visible[key] = normalized
    return visible


def _visible_value(value: object) -> object:
    if isinstance(value, dict):
        return _visible_dict(value)
    if isinstance(value, list):
        return [item for item in (_visible_value(row) for row in value) if item not in (None, {}, [])]
    if isinstance(value, tuple):
        return [item for item in (_visible_value(row) for row in value) if item not in (None, {}, [])]
    return value


def customer_visible_outcome(outcome: TurnOutcome) -> dict[str, object]:
    """Return the responder payload with choice refs/internal metadata removed."""
    return {
        "status": outcome.status,
        "response_goal": outcome.response_goal,
        "facts": _visible_value(outcome.facts),
        "choices": [
            {
                "label": choice.label,
                "facts": _visible_value(choice.facts),
            }
            for choice in outcome.choices
        ],
        "action_result": _visible_value(outcome.action_result),
        "active_task_summary": _visible_value(outcome.active_task_summary),
    }


def _availability_facts(result: ReadResult) -> dict[str, object]:
    payload = result.payload
    raw_slots = payload.get("slots")
    slots = raw_slots if isinstance(raw_slots, list) else []
    windows = availability_windows_from_slots(slots)
    visible_windows = [
        {
            key: window.get(key)
            for key in (
                "doctor_name",
                "laser_device_name",
                "start_local",
                "end_local",
                "start_time_24h",
                "end_time_24h",
            )
            if window.get(key) not in (None, "")
        }
        for window in windows
    ]
    prices = {
        str(_money(slot.get("price_minor"), slot.get("currency")))
        for slot in slots
        if isinstance(slot, dict) and _money(slot.get("price_minor"), slot.get("currency"))
    }
    facts: dict[str, object] = {
        "service_name": payload.get("service_name"),
        "checked_dates": payload.get("checked_dates") or [],
        "availability_windows": visible_windows,
        "available_option_count": len(slots),
        "search_truncated": bool(payload.get("search_truncated")),
    }
    if len(prices) == 1:
        facts["price"] = next(iter(prices))
    elif prices:
        facts["prices"] = sorted(prices)
    return {key: value for key, value in facts.items() if value not in (None, "", [])}


def _read_facts(result: ReadResult) -> dict[str, object]:
    if result.kind == "availability":
        return {"availability": _availability_facts(result)}
    return {result.kind: _visible_value(result.payload)}


def _facts_from_reads(bundle: ReadExecutionBundle | None) -> dict[str, object]:
    if bundle is None:
        return {}
    facts: dict[str, object] = {}
    for result in bundle.results:
        current = _read_facts(result)
        for key, value in current.items():
            if key not in facts:
                facts[key] = value
                continue
            existing = facts[key]
            if isinstance(existing, list):
                existing.append(value)
            else:
                facts[key] = [existing, value]
    return facts


def _model_rows(context: SemanticContext, collection: str) -> list[dict[str, object]]:
    rows = context.model_input.get(collection)
    if not isinstance(rows, list):
        return []
    return [dict(row) for row in rows if isinstance(row, dict)]


def _row_by_ref(context: SemanticContext, ref: str) -> dict[str, object] | None:
    for collection in ("services", "doctors", "appointments", "packages"):
        for row in _model_rows(context, collection):
            if row.get("ref") == ref:
                return row
    for service in _model_rows(context, "services"):
        devices = service.get("devices")
        if not isinstance(devices, list):
            continue
        for device in devices:
            if isinstance(device, dict) and device.get("ref") == ref:
                return dict(device)
    return None


def _label_for_ref(context: SemanticContext, ref: str) -> str:
    row = _row_by_ref(context, ref)
    if row is None:
        return "خيار متاح"
    name = row.get("name")
    if name:
        return str(name)
    service_ref = row.get("service_ref")
    doctor_ref = row.get("doctor_ref")
    pieces: list[str] = []
    if isinstance(service_ref, str):
        service = _row_by_ref(context, service_ref)
        if service and service.get("name"):
            pieces.append(str(service["name"]))
    if isinstance(doctor_ref, str):
        doctor = _row_by_ref(context, doctor_ref)
        if doctor and doctor.get("name"):
            pieces.append(str(doctor["name"]))
    if row.get("start_local"):
        pieces.append(str(row["start_local"]))
    return " · ".join(pieces) if pieces else "خيار متاح"


def _semantic_choices(
    *,
    step: PlanStep,
    turn: TiaTurnUnderstanding,
    semantic_context: SemanticContext,
) -> list[OutcomeChoice]:
    if step.clarification_field not in {"service", "doctor", "device", "appointment", "package"}:
        return []
    try:
        operation = turn.operations[step.operation_index]
    except IndexError:
        return []
    entity = getattr(operation.entities, step.clarification_field)
    if entity is None:
        return []
    return [
        OutcomeChoice(
            ref=ref,
            label=_label_for_ref(semantic_context, ref),
            facts={},
        )
        for ref in entity.candidate_refs
        if semantic_context.resolve(ref) is not None
    ]


def _choices_from_appointments(bundle: ReadExecutionBundle | None) -> list[OutcomeChoice]:
    if bundle is None:
        return []
    choices: list[OutcomeChoice] = []
    for result in bundle.results:
        if result.kind != "appointments":
            continue
        rows = result.payload.get("appointments")
        if not isinstance(rows, list):
            continue
        for index, row in enumerate(rows, start=1):
            if not isinstance(row, dict):
                continue
            label_parts = [
                str(row.get("service_name") or "موعد"),
                str(row.get("doctor_name") or ""),
                str(row.get("start_local") or ""),
            ]
            choices.append(
                OutcomeChoice(
                    ref=f"appointment-choice-{index}",
                    label=" · ".join(part for part in label_parts if part),
                    facts={"appointment_id": row.get("appointment_id")},
                )
            )
    return choices


def _choices_from_packages(bundle: ReadExecutionBundle | None) -> list[OutcomeChoice]:
    if bundle is None:
        return []
    choices: list[OutcomeChoice] = []
    for result in bundle.results:
        if result.kind not in {"customer_packages", "package_offers", "package_refund_quote"}:
            continue
        rows = (
            result.payload.get("packages")
            or result.payload.get("offers")
            or result.payload.get("quotes")
        )
        if not isinstance(rows, list):
            continue
        for index, row in enumerate(rows, start=1):
            if not isinstance(row, dict):
                continue
            name = row.get("name") or row.get("package_name") or row.get("service_name") or "باكيدج"
            choices.append(
                OutcomeChoice(
                    ref=f"package-choice-{index}",
                    label=str(name),
                    facts=_visible_dict(row),
                )
            )
    return choices


def _clarification_choices(
    *,
    step: PlanStep,
    turn: TiaTurnUnderstanding,
    semantic_context: SemanticContext,
    reads: ReadExecutionBundle | None,
) -> list[OutcomeChoice]:
    semantic = _semantic_choices(step=step, turn=turn, semantic_context=semantic_context)
    if semantic:
        return semantic
    if step.clarification_field == "appointment":
        return _choices_from_appointments(reads)
    if step.clarification_field == "package":
        return _choices_from_packages(reads)
    return []


def _availability_has_options(bundle: ReadExecutionBundle | None) -> bool | None:
    if bundle is None:
        return None
    for result in bundle.results:
        if result.kind != "availability":
            continue
        slots = result.payload.get("slots")
        return bool(slots) if isinstance(slots, list) else False
    return None


def _time_is_exact(step: PlanStep) -> bool:
    value = step.facts.get("time")
    return isinstance(value, dict) and value.get("mode") == "exact"


def _result_requires_staff(bundle: ReadExecutionBundle | None) -> bool:
    if bundle is None:
        return False
    return any(result.error_code == "refund_quote_requires_staff" for result in bundle.results)


def build_handoff_outcome(plan: TurnPlan) -> TurnOutcome:
    if plan.handoff_category is None:
        raise OutcomeBuildError("Turn plan does not require handoff.")
    return TurnOutcome(
        status="handoff",
        response_goal="handoff",
        facts={
            "category": plan.handoff_category,
            "priority": plan.handoff_priority or "normal",
        },
    )


def build_step_outcome(
    step: PlanStep,
    *,
    turn: TiaTurnUnderstanding,
    semantic_context: SemanticContext,
    reads: ReadExecutionBundle | None = None,
    action_result: dict[str, object] | None = None,
    active_task_summary: dict[str, object] | None = None,
) -> TurnOutcome:
    """Convert deterministic planning/execution facts into one responder-safe outcome."""
    read_facts = _facts_from_reads(reads)
    base_facts = {**_visible_dict(step.facts), **read_facts}
    active_summary = _visible_dict(dict(active_task_summary or {}))

    if step.disposition == "handoff":
        return TurnOutcome(
            status="handoff",
            response_goal="handoff",
            facts=base_facts,
            active_task_summary=active_summary,
        )

    if step.disposition == "clarify":
        choices = _clarification_choices(
            step=step,
            turn=turn,
            semantic_context=semantic_context,
            reads=reads,
        )
        requested_goal: ResponseGoal = step.response_goal or "clarification"
        goal = requested_goal if choices or not requested_goal.startswith("ask_") else "clarification"
        return TurnOutcome(
            status="needs_input",
            response_goal=goal,
            facts={**base_facts, "needed": step.clarification_field or "clarification"},
            choices=choices,
            active_task_summary=active_summary,
        )

    if step.disposition == "blocked":
        return TurnOutcome(
            status="blocked",
            response_goal=step.response_goal or "clarification",
            facts=base_facts,
            active_task_summary=active_summary,
        )

    if step.disposition == "write_ready":
        if action_result is None:
            raise OutcomeBuildError("A write-ready step cannot claim a customer outcome before execution.")
        if action_result.get("requires_human"):
            return TurnOutcome(
                status="handoff",
                response_goal="handoff",
                facts=base_facts,
                action_result=_visible_dict(action_result),
                active_task_summary=active_summary,
            )
        if action_result.get("ok") is not True:
            return TurnOutcome(
                status="blocked",
                response_goal=step.response_goal or "clarification",
                facts=base_facts,
                action_result=_visible_dict(action_result),
                active_task_summary=active_summary,
            )
        return TurnOutcome(
            status="completed",
            response_goal=step.response_goal or "clarification",
            facts=base_facts,
            action_result=_visible_dict(action_result),
            active_task_summary=active_summary,
        )

    if _result_requires_staff(reads):
        return TurnOutcome(
            status="blocked",
            response_goal=step.response_goal or "package_refund_quote",
            facts={**base_facts, "requires_staff_review": True},
            active_task_summary=active_summary,
        )

    has_availability = _availability_has_options(reads)
    if step.operation_type in {"availability", "book", "reschedule"} and has_availability is False:
        goal: ResponseGoal = "requested_time_unavailable" if _time_is_exact(step) else "no_availability"
        return TurnOutcome(
            status="blocked",
            response_goal=goal,
            facts=base_facts,
            active_task_summary=active_summary,
        )

    status = "answered"
    return TurnOutcome(
        status=status,
        response_goal=step.response_goal or "clarification",
        facts=base_facts,
        active_task_summary=active_summary,
    )
