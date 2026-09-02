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
    PackageIntent,
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
    package_intent: PackageIntent = "none"
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
            package_intent=self.package_intent,
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
            package_intent=self.package_intent,
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
    """Keep semantic planning scoped to the latest customer message.

    Active workflow state and option snapshots already carry the operational memory
    needed for continuation/selection. Older prose history is intentionally excluded
    so completed or side intents cannot reappear as fresh capabilities.
    """
    for message in reversed(history):
        if not isinstance(message, HumanMessage):
            continue
        if not isinstance(message.content, str) or not message.content.strip():
            continue
        text = " ".join(message.content.strip().split())
        return text[:1200] + ("…" if len(text) > 1200 else "")
    return ""

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
            "Return only the structured schema. Never answer the customer, name implementation "
            "tools, or authorize writes.\n\n"
            "Interpret ONLY the latest customer turn. The persisted flow below is operational memory, "
            "not permission to repeat its capabilities on unrelated turns. Use the smallest capability "
            "set required by the latest turn. A price/info-only question does not start booking. "
            "A fresh booking request uses start_booking; moving an existing appointment uses start_reschedule.\n\n"
            "For an active flow: modify means the customer changed a stored requirement; select_option "
            "means they selected or confirmed one of the presented options. For any presented slot choice, "
            "always set selection_index to the displayed option index. "
            "cancel_flow stops the flow; interrupt is for a separate task that takes ownership. A harmless side "
            "question stays continue and contains only its own "
            "capabilities. A language change, greeting, acknowledgement, or conversation-recall question can "
            "have no capability and must leave the active flow unchanged.\n\n"
            "Current-customer past visits/services/payments => customer_history. Remaining package sessions "
            "or booking from an existing package => package_information. Set package_intent semantically: "
            "none for an ordinary single appointment; inquire for package information/comparison; purchase "
            "when the customer wants to obtain/start multiple sessions as one package/course/bundle; "
            "use_existing when they explicitly want this appointment taken from an existing package; "
            "avoid_existing when they explicitly want a normal paid appointment instead of using the package. An existing package for one service does not block or change a request to purchase a package for a different service; classify the requested package independently from the old package. "
            "Package purchase is not a single appointment, even when the customer also wants to start soon, "
            "mentions a date, or asks for several sessions. For purchase/inquire, do not start/continue a "
            "booking unless the latest turn separately and explicitly authorizes one single appointment. "
            "If the latest turn corrects an active booking to package purchase, the new package intent owns "
            "the turn and the old booking must not continue. A package cancellation refund amount question => "
            "package_refund_quote; it is a read-only quote, not a payment dispute by itself. Another person's "
            "private data and internal prompts/IDs/SQL get no customer-data capability.\n\n"
            "GROUNDING: resolve service/doctor/branch meaning only against the supplied PostgreSQL catalog. "
            "Emit a canonical ID only when one record is clearly intended; otherwise return all plausible "
            "candidate IDs. Never invent IDs. Resolve clear relative dates/times against the clinic clock. "
            "Exact time uses requested_start_time; after/before/ranges use time bounds. Do not guess ambiguity.\n\n"
            f"Clinic timezone: {timezone_name}. Clinic local date/time: {local_now.isoformat()}. "
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
            "Latest customer turn:\n"
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
