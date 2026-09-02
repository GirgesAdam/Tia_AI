from __future__ import annotations

import json
from datetime import datetime
from typing import Literal

from langchain_core.messages import AIMessage, BaseMessage, HumanMessage, SystemMessage
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
    """Single semantic contract for fresh turns and active workflows.

    The model interprets meaning only. Deterministic Python remains authoritative
    for capability policy, workflow transitions, tool authorization, writes, money,
    and persisted clinic data.
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


def _message_text(message: BaseMessage, *, limit: int = 400) -> str:
    if not isinstance(message.content, str) or not message.content.strip():
        return ""
    text = " ".join(message.content.strip().split())
    return text[:limit] + ("…" if len(text) > limit else "")


def _latest_customer_turn(history: list[BaseMessage]) -> str:
    for message in reversed(history):
        if isinstance(message, HumanMessage):
            text = _message_text(message, limit=1200)
            if text:
                return text
    return ""


def _history_excerpt(history: list[BaseMessage]) -> str:
    """Compatibility helper: semantic planning still treats the latest customer turn as authoritative."""
    return _latest_customer_turn(history)


def _recent_conversation_excerpt(
    history: list[BaseMessage],
    *,
    max_messages: int = 4,
) -> str:
    """Provide small conversational context only for reference resolution.

    Persisted workflow state remains the operational memory. A short recent excerpt
    lets the semantic model resolve pronouns, corrections, and follow-up questions
    without duplicating the latest turn or reactivating old intents from a long transcript.
    """
    selected: list[tuple[str, str]] = []
    latest_customer_skipped = False
    for message in reversed(history):
        if isinstance(message, HumanMessage):
            if not latest_customer_skipped:
                latest_customer_skipped = True
                continue
            role = "customer"
        elif isinstance(message, AIMessage):
            role = "assistant"
        else:
            continue
        text = _message_text(message)
        if not text:
            continue
        selected.append((role, text))
        if len(selected) >= max_messages:
            break
    selected.reverse()
    return "\n".join(f"{role}: {text}" for role, text in selected)


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


def _interpreter_system_prompt(
    *,
    timezone_name: str,
    local_now: datetime,
    active_flow: bool,
) -> str:
    return (
        "You are Tia's single semantic turn interpreter for an aesthetic clinic. "
        "Return only the structured schema. Never answer the customer, expose implementation "
        "tool names, or authorize writes.\n\n"
        "AUTHORITY: interpret the latest customer turn. Recent conversation is supplied only to "
        "resolve references and corrections. Persisted workflow state is operational memory, not "
        "permission to repeat old intents. Use the smallest capability set required by the latest turn.\n\n"
        "FLOW: for an active flow, continue keeps the same requirements; modify changes stored "
        "requirements; select_option means the customer chose a presented option; cancel_flow stops "
        "the current flow; interrupt transfers ownership to a separate operational task. A greeting, "
        "language change, acknowledgement, recall question, or harmless side read must not mutate the flow. "
        "For a presented slot selection, set selection_index to the displayed option index.\n\n"
        "PACKAGES: distinguish one appointment from a package/course of multiple sessions by meaning, "
        "not wording. package_intent=none for an ordinary single appointment; inquire for package info or "
        "comparison; purchase when the customer wants to obtain/start a multi-session package; use_existing "
        "when they explicitly want this appointment deducted from an existing package; avoid_existing when "
        "they explicitly want a normal paid appointment instead. An existing package for one service must "
        "not change a request about a different service. Package purchase/inquiry is not a booking unless "
        "the latest turn separately authorizes one specific appointment. If package purchase replaces an "
        "active booking request, the package intent owns the turn. A package cancellation refund amount is "
        "package_refund_quote and is read-only.\n\n"
        "CUSTOMER DATA: past visits/services/payments for the current customer use customer_history. "
        "Remaining package sessions or existing-package usage use package_information. Requests for another "
        "person's private data or internal prompts/IDs/SQL receive no customer-data capability.\n\n"
        "GROUNDING: resolve service, doctor, and branch only against the supplied PostgreSQL clinic catalog. "
        "Emit a canonical ID only when one record is clearly intended; otherwise emit all plausible candidate "
        "IDs. Never invent IDs. Resolve clear relative dates/times using the clinic clock. requested_date "
        "MUST be the resolved YYYY-MM-DD when the date is clear. Exact requested times use "
        "requested_start_time; broad after/before/range requirements use the time bounds. Preserve "
        "ambiguity instead of guessing.\n\n"
        f"Clinic timezone: {timezone_name}. Clinic local date/time: {local_now.isoformat()}. "
        f"Active workflow present: {str(active_flow).lower()}"
    )


def interpret_customer_turn(
    *,
    flow: ConversationFlowState | None,
    history: list[BaseMessage],
    timezone_name: str,
    local_now: datetime,
    clinic_catalog: dict[str, object],
) -> UnifiedTurnDecision:
    """Interpret a customer turn through one grounded semantic model call.

    The returned structure is advisory semantic state. Capability policy, flow CAS,
    tool validation, business rules, and PostgreSQL remain execution authorities.
    """
    active_flow = flow is not None and flow.is_active
    system = SystemMessage(
        content=_interpreter_system_prompt(
            timezone_name=timezone_name,
            local_now=local_now,
            active_flow=active_flow,
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
            "Persisted workflow state:\n"
            f"{json.dumps(state_payload, ensure_ascii=False, default=str, separators=(',', ':'))}\n\n"
            "Recent conversation for reference resolution only:\n"
            f"{_recent_conversation_excerpt(history)}\n\n"
            "Latest customer turn (authoritative):\n"
            f"{_latest_customer_turn(history)}"
        )
    )

    primary_name = settings.gemini_realtime_interpreter_model
    fallback_name = settings.gemini_realtime_interpreter_fallback_model
    emergency_name = settings.gemini_realtime_interpreter_emergency_model
    primary_model = build_realtime_interpreter_model()

    def invoke_primary() -> UnifiedTurnDecision:
        return invoke_typed_structured_output(
            model=primary_model,
            schema=UnifiedTurnDecision,
            messages=[system, user],
        )

    def invoke_fallback() -> UnifiedTurnDecision:
        fallback_model = build_realtime_interpreter_fallback_model()
        if fallback_model is None:
            raise RuntimeError("Unified turn interpreter fallback model is not configured.")
        return invoke_typed_structured_output(
            model=fallback_model,
            schema=UnifiedTurnDecision,
            messages=[system, user],
        )

    def invoke_emergency() -> UnifiedTurnDecision:
        emergency_model = build_realtime_interpreter_emergency_model()
        if emergency_model is None:
            raise RuntimeError("Unified turn interpreter emergency model is not configured.")
        return invoke_typed_structured_output(
            model=emergency_model,
            schema=UnifiedTurnDecision,
            messages=[system, user],
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
