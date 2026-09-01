from __future__ import annotations

import json
from datetime import datetime
from typing import Literal

from langchain_core.messages import BaseMessage, HumanMessage, SystemMessage
from pydantic import BaseModel, ConfigDict, Field

from app.agents.clinic_grounding import validate_grounded_entity_ids
from app.agents.flow_interpreter import ClearableFlowEntity, FlowTurnDecision
from app.agents.llm_runtime import invoke_with_model_chain
from app.agents.model_provider import (
    build_realtime_interpreter_emergency_model,
    build_realtime_interpreter_fallback_model,
    build_realtime_interpreter_model,
)
from app.agents.semantic_router import (
    FlowSignal,
    HandoffCategory,
    Priority,
    RiskFlag,
    SemanticCapability,
    SemanticCapabilityDecision,
    SemanticDomain,
    SemanticEntityHints,
    _require_all_schema_fields,
)
from app.agents.structured_output import invoke_typed_structured_output
from app.core.config import settings
from app.models.conversation_flow_state import ConversationFlowState

UnifiedTurnAction = Literal[
    "continue",
    "modify",
    "select_option",
    "cancel_flow",
    "interrupt",
]


class UnifiedTurnDecision(BaseModel):
    """One semantic contract for both fresh turns and active workflows.

    This model replaces the split semantic-router / flow-interpreter decision
    surface when the experimental simple-orchestrator flag is enabled. It still
    does not expose implementation tool names and never grants write permission.
    """

    model_config = ConfigDict(
        extra="forbid", json_schema_extra=_require_all_schema_fields
    )

    domains: list[SemanticDomain]
    capabilities: list[SemanticCapability]
    risk_flags: list[RiskFlag]
    flow_signal: FlowSignal
    action: UnifiedTurnAction
    entity_hints: SemanticEntityHints
    clear_entity_fields: list[ClearableFlowEntity] = Field(default_factory=list)
    selection_index: int | None
    selection_time: str | None
    missing_information: list[str]
    recommended_handoff_category: HandoffCategory
    recommended_handoff_priority: Priority
    confidence: float
    reason: str

    def as_semantic_decision(self) -> SemanticCapabilityDecision:
        return SemanticCapabilityDecision(
            domains=self.domains,
            capabilities=self.capabilities,
            risk_flags=self.risk_flags,
            flow_signal=self.flow_signal,
            entity_hints=self.entity_hints,
            missing_information=self.missing_information,
            recommended_handoff_category=self.recommended_handoff_category,
            recommended_handoff_priority=self.recommended_handoff_priority,
            confidence=self.confidence,
            reason=self.reason,
        )

    def as_flow_turn_decision(self) -> FlowTurnDecision:
        return FlowTurnDecision(
            action=self.action,
            capabilities=self.capabilities,
            risk_flags=self.risk_flags,
            entity_hints=self.entity_hints,
            clear_entity_fields=self.clear_entity_fields,
            selection_index=self.selection_index,
            selection_time=self.selection_time,
            missing_information=self.missing_information,
            recommended_handoff_category=self.recommended_handoff_category,
            recommended_handoff_priority=self.recommended_handoff_priority,
            confidence=self.confidence,
            reason=self.reason,
        )


def _history_excerpt(history: list[BaseMessage]) -> str:
    selected = history[-settings.agent_router_history_messages :]
    lines: list[str] = []
    for message in selected:
        if not isinstance(message.content, str) or not message.content.strip():
            continue
        role = message.type or "message"
        text = " ".join(message.content.strip().split())
        if len(text) > 700:
            text = text[:700] + "…"
        lines.append(f"{role}: {text}")
    return "\n".join(lines)


def _option_summary(flow: ConversationFlowState | None) -> dict[str, object]:
    if flow is None or not isinstance(flow.option_snapshot, dict):
        return {}

    summary: dict[str, object] = {}
    slots = flow.option_snapshot.get("slots")
    if isinstance(slots, list):
        summary["slots"] = [
            {
                "index": index + 1,
                "start_time_24h": slot.get("start_time_24h"),
                "end_time_24h": slot.get("end_time_24h"),
                "doctor_name": slot.get("doctor_name"),
                "branch_name": slot.get("branch_name"),
            }
            for index, slot in enumerate(slots[:8])
            if isinstance(slot, dict)
        ]

    choice_specs = (
        ("services", ("service_name", "name")),
        ("branches", ("branch_name", "name")),
        ("doctors", ("doctor_name", "name")),
    )
    for collection_name, name_keys in choice_specs:
        choices = flow.option_snapshot.get(collection_name)
        if not isinstance(choices, list):
            continue
        summarized: list[dict[str, object]] = []
        for index, choice in enumerate(choices[:8]):
            if not isinstance(choice, dict):
                continue
            display_name = next(
                (choice.get(key) for key in name_keys if choice.get(key)),
                None,
            )
            canonical_id = (
                choice.get("service_id")
                or choice.get("branch_id")
                or choice.get("doctor_id")
                or choice.get("id")
            )
            summarized.append(
                {
                    "index": index + 1,
                    "id": canonical_id,
                    "name": display_name,
                }
            )
        if summarized:
            summary[collection_name] = summarized
    return summary


def interpret_customer_turn(
    *,
    flow: ConversationFlowState | None,
    history: list[BaseMessage],
    timezone_name: str,
    local_now: datetime,
    clinic_catalog: dict[str, object],
) -> UnifiedTurnDecision:
    """Interpret every turn through one semantic planner.

    The planner sees persisted workflow state when present, but the deterministic
    capability policy, flow CAS, tool validation, and PostgreSQL remain the only
    authorities for execution.
    """
    active_flow = flow is not None and flow.is_active
    system = SystemMessage(
        content=(
            "You are Tia's unified semantic turn interpreter for an aesthetic clinic. "
            "Return only the structured schema. Never answer the customer. Never return "
            "implementation tool names and never authorize writes. Your job is only to "
            "describe meaning, entity changes, workflow action, safety, and option selection.\n\n"
            "Every schema field must be present. Use null for unresolved optional scalar "
            "values and [] for empty lists.\n\n"
            "Capabilities can be simultaneous, e.g. pricing + availability_discovery + "
            "appointment_creation. Asking what the current customer did at the clinic before, "
            "which services they received, when they last visited, or what they historically paid "
            "is customer_history and is read-only. A request for the clinic to contact/call/remind the current "
            "customer at a specific future time is follow_up_request; it is a CRM follow-up, "
            "not an appointment reminder automation. Medical diagnosis/symptoms/pregnancy/medication or "
            "personalized treatment suitability => medical risk and human handoff.\n\n"
            "Workflow action semantics:\n"
            "- continue: no material requirement change; also use this for a normal fresh "
            "turn when there is no active workflow.\n"
            "- modify: an active workflow requirement is changed, replaced, broadened, or "
            "removed.\n"
            "- select_option: the customer clearly selects an option previously presented. "
            "Set selection_index or selection_time when resolvable.\n"
            "- cancel_flow: stop the active workflow itself.\n"
            "- interrupt: safety/human-support or a clearly separate task takes ownership.\n\n"
            "For a fresh booking request use flow_signal=start_booking. For moving an existing "
            "appointment use start_reschedule. Use interrupt when safety/handoff should own "
            "the turn, otherwise none.\n\n"
            "Requirement relaxation is semantic, not lexical: clear_entity_fields only when "
            "the customer intentionally removes/replaces a stored requirement. If an exact "
            "time failed and the customer asks for other times that day, preserve service, "
            "branch, doctor and date but clear requested_start_time plus any obsolete time "
            "bounds. Never clear "
            "stored fields merely because the newest message does not repeat them.\n\n"
            "GROUNDING CONTRACT: A compact clinic catalog from PostgreSQL is included below. "
            "Resolve service, doctor, and branch meaning semantically against that catalog. "
            "Do not use literal string-pattern heuristics or invented aliases. "
            "When one catalog record is clearly intended, set its canonical *_id and keep the "
            "corresponding *_candidate_ids empty. When multiple catalog records are genuinely "
            "plausible, leave the selected *_id null and return ALL plausible canonical IDs in "
            "*_candidate_ids so the customer can choose. For broad information questions such "
            "as asking for laser services, return all relevant service IDs rather than an arbitrary "
            "top subset. Every ID you emit MUST appear verbatim in the supplied catalog.\n\n"
            "Entity query strings are audit-friendly observations only; canonical IDs are the runtime "
            "authority for clinic entity resolution. Preserve explicit service, branch, doctor, date "
            "and time meaning. Resolve clear relative dates/times against the clinic local clock. "
            "One precise requested start ('at 6 PM' / 'الساعة 6') must use "
            "requested_start_time='18:00' with null time-window bounds; 'after 6' uses "
            "not_before_time; 'before 8' uses not_after_time; 'from 6 to 8' uses both. "
            "Never encode an exact start as not_before_time == not_after_time and never guess "
            "genuinely ambiguous values.\n\n"
            f"Clinic timezone: {timezone_name}\n"
            f"Clinic local date/time now: {local_now.isoformat()}\n"
            f"Active workflow present: {str(active_flow).lower()}"
        )
    )

    state_payload = {
        "active_flow": active_flow,
        "flow_type": flow.flow_type if active_flow else None,
        "flow_status": flow.status if active_flow else None,
        "flow_capabilities": flow.capabilities if active_flow else [],
        "entity_state": flow.entity_state if active_flow else {},
        "missing_information": flow.missing_information if active_flow else [],
        "options": _option_summary(flow if active_flow else None),
    }
    user = HumanMessage(
        content=(
            "PostgreSQL clinic catalog (canonical IDs; do not invent IDs):\n"
            f"{json.dumps(clinic_catalog, ensure_ascii=False, default=str, separators=(',', ':'))}\n\n"
            "Persisted state:\n"
            f"{json.dumps(state_payload, ensure_ascii=False, default=str)}\n\n"
            "Recent conversation:\n"
            f"{_history_excerpt(history)}"
        )
    )

    primary_name = settings.gemini_realtime_interpreter_model
    fallback_name = settings.gemini_realtime_interpreter_fallback_model
    emergency_name = settings.gemini_realtime_interpreter_emergency_model
    primary_model = build_realtime_interpreter_model()

    def invoke_primary() -> UnifiedTurnDecision:
        return invoke_typed_structured_output(
            model=primary_model, schema=UnifiedTurnDecision, messages=[system, user]
        )

    def invoke_fallback() -> UnifiedTurnDecision:
        fallback_model = build_realtime_interpreter_fallback_model()
        if fallback_model is None:
            raise RuntimeError("Unified turn interpreter fallback model is not configured.")
        return invoke_typed_structured_output(
            model=fallback_model, schema=UnifiedTurnDecision, messages=[system, user]
        )

    def invoke_emergency() -> UnifiedTurnDecision:
        emergency_model = build_realtime_interpreter_emergency_model()
        if emergency_model is None:
            raise RuntimeError("Unified turn interpreter emergency model is not configured.")
        return invoke_typed_structured_output(
            model=emergency_model, schema=UnifiedTurnDecision, messages=[system, user]
        )

    model_calls = [(primary_name, invoke_primary)]
    if fallback_name and fallback_name != primary_name:
        model_calls.append((fallback_name, invoke_fallback))
    if emergency_name and emergency_name not in {primary_name, fallback_name}:
        model_calls.append((emergency_name, invoke_emergency))

    invocation = invoke_with_model_chain(
        model_calls=model_calls,
        operation="unified-turn-interpreter",
        circuit_breaker_cooldown_seconds=settings.llm_realtime_circuit_breaker_cooldown_seconds,
    )
    value = invocation.value
    grounded_hints = validate_grounded_entity_ids(value.entity_hints, clinic_catalog)
    return value.model_copy(update={"entity_hints": grounded_hints})
