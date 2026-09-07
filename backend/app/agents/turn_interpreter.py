from __future__ import annotations

import json
from copy import deepcopy
from datetime import datetime
from typing import Literal

from langchain_core.messages import AIMessage, BaseMessage, HumanMessage, SystemMessage
from pydantic import BaseModel, ConfigDict, Field

from app.agents.clinic_grounding import validate_grounded_entity_ids
from app.agents.llm_runtime import invoke_with_model_chain
from app.agents.model_provider import (
    build_realtime_interpreter_emergency_model,
    build_realtime_interpreter_fallback_model,
    build_realtime_interpreter_model,
)
from app.agents.structured_output import (
    StructuredOutputError,
    invoke_typed_structured_output,
)
from app.agents.turn_models import (
    ClearableFlowEntity,
    FlowSignal,
    FlowTurnDecision,
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
    windows = flow.option_snapshot.get("availability_windows")
    if isinstance(windows, list) and windows:
        summary["availability_windows"] = [
            {
                "doctor_id": window.get("doctor_id"),
                "doctor_name": window.get("doctor_name"),
                "start_time_24h": window.get("start_time_24h"),
                "end_time_24h": window.get("end_time_24h"),
            }
            for window in windows[:12]
            if isinstance(window, dict)
        ]
    else:
        slots = flow.option_snapshot.get("slots")
        if isinstance(slots, list):
            summary["slots"] = [
                {
                    "index": index + 1,
                    "start_time_24h": slot.get("start_time_24h"),
                    "end_time_24h": slot.get("end_time_24h"),
                    "doctor_name": slot.get("doctor_name"),
                }
                for index, slot in enumerate(slots[:8])
                if isinstance(slot, dict)
            ]

    choice_specs = (
        ("services", ("service_name", "name")),
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
            canonical_id = choice.get("service_id") or choice.get("doctor_id") or choice.get("id")
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

def _semantic_catalog_for_single_location(
    clinic_catalog: dict[str, object],
) -> dict[str, object]:
    """Hide storage-level location rows from customer-language interpretation.

    The current product is a single-location clinic experience. PostgreSQL and
    external adapters may still require a branch/location foreign key internally,
    but choosing that row is a deterministic backend concern rather than a
    customer intent or LLM grounding task.
    """
    semantic_catalog = deepcopy(clinic_catalog)
    semantic_catalog.pop("branches", None)

    doctors = semantic_catalog.get("doctors")
    if isinstance(doctors, list):
        for doctor in doctors:
            if not isinstance(doctor, dict):
                continue
            doctor.pop("branch_ids", None)
            doctor.pop("scheduled_branch_ids", None)

    return semantic_catalog


def _single_location_entity_state(state: object) -> dict[str, object]:
    if not isinstance(state, dict):
        return {}
    blocked = {
        "branch",
        "branches",
        "branch_id",
        "branch_name",
        "branch_query",
        "branch_candidate_ids",
    }
    return {key: value for key, value in state.items() if key not in blocked}


def _normalize_single_location_decision(
    decision: UnifiedTurnDecision,
) -> UnifiedTurnDecision:
    """Enforce the single-location product invariant after semantic inference."""
    capabilities = [
        capability
        for capability in decision.capabilities
        if str(capability) != "branch_discovery"
    ]
    hints = decision.entity_hints.model_copy(
        update={
            "branch_query": None,
            "branch_id": None,
            "branch_candidate_ids": [],
        }
    )
    clear_fields = [
        field
        for field in decision.clear_entity_fields
        if str(field)
        not in {"branch_query", "branch_id", "branch_candidate_ids"}
    ]
    missing_information = [
        item
        for item in decision.missing_information
        if item not in {"branch", "branch_id", "branch_query", "branch_choice"}
    ]
    return decision.model_copy(
        update={
            "capabilities": capabilities,
            "entity_hints": hints,
            "clear_entity_fields": clear_fields,
            "missing_information": missing_information,
        }
    )


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
        "For a numbered option selection, set selection_index to the displayed option index. "
        "When availability was shown as a continuous time window and the customer chooses a clock "
        "time inside it, set selection_time to HH:MM instead. Never invent a doctor when the same "
        "clock time is available with multiple doctors.\n\n"
        "AVAILABILITY FOLLOW-UPS: when an active booking flow has just presented a date or time "
        "window and the latest customer turn rejects that offer or asks for another day, treat it "
        "as a semantic modification of the same availability search. Keep availability_discovery "
        "and the service/doctor/time constraints, set action=modify, and include requested_date in "
        "clear_entity_fields so the backend searches after the rejected date. Do not select or repeat "
        "the presented slot. If the customer accepts or chooses a time from the presented offer, use "
        "select_option instead. If an earlier exact time was unavailable and the customer now asks to see "
        "general availability for the same day, action=modify and clear requested_start_time so the rejected "
        "exact minute cannot keep filtering later turns. If they ask for later/earlier/before/after instead, "
        "clear the stale exact time and encode only the new broad bound. When the customer chooses one exact "
        "clock time from a presented availability window AND explicitly asks to book it, include "
        "appointment_creation and use select_option with selection_time=HH:MM; do not ask for another "
        "confirmation and do not keep an older rejected exact time. This remains true even when the persisted "
        "booking flow currently lists availability_discovery only; the latest explicit booking command owns "
        "the capability for that turn.\n\n"
        "PACKAGES: distinguish one appointment from a package/course of multiple sessions by meaning, "
        "not wording. package_intent=none for an ordinary single appointment; inquire for package info or "
        "comparison; purchase when the customer wants to obtain/start a multi-session package; use_existing "
        "when they explicitly want this appointment deducted from an existing package; avoid_existing when "
        "they explicitly want a normal paid appointment instead. An existing package for one service must "
        "not change a request about a different service. Package purchase/inquiry is not a booking unless "
        "the latest turn separately authorizes one specific appointment. If package purchase replaces an "
        "active booking request, the package intent owns the turn. A pure package cancellation refund amount "
        "question uses package_refund_quote, is read-only, and should use package_intent=none rather than a "
        "generic package inquiry. Comparing an ordinary paid session with using or buying a package is "
        "commercial/booking guidance, not a medical question. Escalate for medical risk only when the customer "
        "asks about clinical suitability, diagnosis, safety, contraindications, adverse effects, or a "
        "health-based treatment recommendation. A catalog flag saying a service requires medical review does "
        "not by itself make a price, availability, booking, reschedule, or cancellation request medical; keep "
        "those operational unless the customer's actual question asks for clinical judgment.\n\n"
        "CUSTOMER DATA: past visits/services/payments for the current customer use customer_history. "
        "A simple read-only question about whether the current customer's appointment is paid, how it was paid, "
        "or how much was paid is customer_history and must not set payment risk by itself. Payment disputes, "
        "charge corrections, failed-payment problems, refunds other than the verified package quote, or requests "
        "to change financial records may use payment risk/handoff. "
        "Clinic address, phone, and opening/working hours use clinic_information and are read-only. "
        "Remaining package sessions or existing-package usage use package_information. Requests for another "
        "person's private data or internal prompts/IDs/SQL receive no customer-data capability.\n\n"
        "LOCATION: this product is a single-location clinic experience. Branches are not a customer-facing "
        "booking concept. Never ask the customer to choose a branch, never emit branch_discovery, and keep "
        "branch_query, branch_id, and branch_candidate_ids empty. The backend supplies any storage-level "
        "location identifier deterministically when required.\n\n"
        "GROUNDING: resolve service and doctor only against the supplied PostgreSQL clinic catalog. "
        "When both a doctor and service are mentioned, respect their canonical compatibility relationships. "
        "Emit a canonical ID only when one record is clearly intended; otherwise emit all plausible candidate "
        "IDs. Never invent IDs. Resolve clear relative dates/times using the clinic clock. requested_date "
        "MUST be the resolved YYYY-MM-DD when the date is clear. Exact requested times use "
        "requested_start_time; broad after/before/range requirements use the time bounds. Preserve "
        "ambiguity instead of guessing. Resolve colloquial clock hours using normal clinic context: when a "
        "customer says 'الساعة 2' without saying morning/night, prefer the plausible clinic-hours reading "
        "(for example 14:00 when 02:00 is outside working hours). If they explicitly say '2 الفجر', AM/PM, "
        "or an unambiguous 24-hour value, preserve that meaning. Never silently round an exact minute such as "
        "14:07 to a nearby bookable slot. When an active flow's latest turn changes a time constraint, the "
        "latest meaning owns that constraint: use clear_entity_fields for any persisted exact/lower/upper "
        "time bound that is no longer implied by the new turn. Do not keep an older opposite-side bound just "
        "because it exists in workflow memory. "
        "When the latest turn replaces a service or doctor in an active flow, action=modify and the newly "
        "grounded entity owns the requirement. If a service changes and the old doctor was not explicitly "
        "reaffirmed, clear the old doctor requirement so compatibility can be resolved again. An explicit "
        "new service in an active booking flow always owns the next discovery: action=modify, ground the new "
        "service, and never answer or execute from the previous service's availability snapshot. If the latest "
        "turn names both the new service and a compatible doctor/date, preserve those new requirements and "
        "refresh availability for them. For an active "
        "reschedule flow, select_option is only for a replacement slot that the assistant already presented. "
        "If the customer instead supplies a new exact target date/time in their own words and clearly commands "
        "the change now, action MUST be modify (never continue and never ask for a second confirmation), keep "
        "appointment_reschedule, and put the exact target in requested_date "
        "and requested_start_time. The backend will verify that target against real replacement availability "
        "before any write. A question about whether a time is possible is not write authorization. "
        "For reference resolution, phrases that refer to a doctor set from the immediately preceding exchange "
        "must inherit the previously discussed grounded service when that service is unambiguous. If the latest "
        "turn asks which/any of those compatible doctors is available soon, next, or earliest, use "
        "availability_discovery for that service. Do not force one doctor: leave doctor_query, doctor_id, and "
        "doctor_candidate_ids empty unless the latest turn actually singles out a doctor. The availability "
        "adapter is responsible for comparing all compatible doctors.\n\n"
        f"Clinic timezone: {timezone_name}. Clinic local date/time: {local_now.isoformat()}. "
        f"Active workflow present: {str(active_flow).lower()}"
    )


def _snapshot_has_exact_time(
    flow: ConversationFlowState,
    exact_time: str,
    *,
    doctor_id: str | None,
    requested_date: str | None,
) -> bool:
    """Verify a semantic exact-time choice against the already-presented snapshot."""
    snapshot = flow.option_snapshot if isinstance(flow.option_snapshot, dict) else {}
    snapshot_date = str(snapshot.get("date") or "").strip()
    if requested_date and snapshot_date and str(requested_date) != snapshot_date:
        return False
    normalized = str(exact_time).strip()[:5]
    slots = snapshot.get("slots")
    if not isinstance(slots, list):
        return False
    matches = 0
    for slot in slots:
        if not isinstance(slot, dict):
            continue
        if str(slot.get("start_time_24h") or "").strip()[:5] != normalized:
            continue
        if doctor_id and str(slot.get("doctor_id") or "") != str(doctor_id):
            continue
        matches += 1
    return matches == 1


def _normalize_active_booking_decision(
    decision: UnifiedTurnDecision,
    flow: ConversationFlowState | None,
) -> UnifiedTurnDecision:
    """Normalize structured follow-ups using semantic output + verified flow state only."""
    if flow is None or not flow.is_active or flow.flow_type != "booking":
        return decision

    existing = flow.entity_state if isinstance(flow.entity_state, dict) else {}
    old_service_id = str(existing.get("service_id") or "")
    new_service_id = str(decision.entity_hints.service_id or "")
    service_changed = bool(old_service_id and new_service_id and old_service_id != new_service_id)

    clear_fields = list(decision.clear_entity_fields)
    action = decision.action
    if service_changed:
        action = "modify"
        if (
            not decision.entity_hints.doctor_id
            and not decision.entity_hints.doctor_query
            and not decision.entity_hints.doctor_candidate_ids
        ):
            for field in ("doctor_query", "doctor_id", "doctor_candidate_ids"):
                if field not in clear_fields:
                    clear_fields.append(field)

    exact_time = decision.selection_time or decision.entity_hints.requested_start_time
    capabilities = {str(item) for item in decision.capabilities}
    exact_choice_is_in_snapshot = bool(
        not service_changed
        and exact_time
        and "appointment_creation" in capabilities
        and _snapshot_has_exact_time(
            flow,
            str(exact_time),
            doctor_id=decision.entity_hints.doctor_id,
            requested_date=decision.entity_hints.requested_date,
        )
    )
    if exact_choice_is_in_snapshot:
        return decision.model_copy(
            update={
                "action": "select_option",
                "clear_entity_fields": clear_fields,
                "selection_index": None,
                "selection_time": str(exact_time).strip()[:5],
            }
        )

    if (
        not service_changed
        and exact_time
        and "appointment_creation" in capabilities
        and decision.action == "select_option"
    ):
        # The customer authorized one exact booking time, but the current snapshot
        # is empty or no longer represents that choice. Re-run exact availability
        # through the normal modify/read path in this same turn; do not inspect text
        # and do not guess from an older snapshot.
        for field in ("not_before_time", "not_after_time"):
            if field not in clear_fields:
                clear_fields.append(field)
        return decision.model_copy(
            update={
                "action": "modify",
                "clear_entity_fields": clear_fields,
                "selection_index": None,
                "selection_time": None,
            }
        )

    return decision.model_copy(update={"action": action, "clear_entity_fields": clear_fields})


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
        "flow_capabilities": [
            capability
            for capability in (flow.capabilities if active_flow else [])
            if str(capability) != "branch_discovery"
        ],
        "entity_state": _single_location_entity_state(
            flow.entity_state if active_flow else {}
        ),
        "missing_information": flow.missing_information if active_flow else [],
        "options": _option_summary(flow if active_flow else None),
    }
    semantic_catalog = _semantic_catalog_for_single_location(clinic_catalog)
    user = HumanMessage(
        content=(
            "PostgreSQL clinic catalog (canonical IDs; do not invent IDs):\n"
            f"{json.dumps(semantic_catalog, ensure_ascii=False, default=str, separators=(',', ':'))}\n\n"
            "Persisted workflow state:\n"
            f"{json.dumps(state_payload, ensure_ascii=False, default=str, separators=(',', ':'))}\n\n"
            "Recent conversation for reference resolution only:\n"
            f"{_recent_conversation_excerpt(history)}\n\n"
            "Latest-turn consistency reminder: if presented booking/reschedule options exist and "
            "the latest customer turn explicitly chooses one option or exact clock time and authorizes "
            "the action, capture that choice in selection_index/selection_time or requested_start_time "
            "and include the matching write capability. Never infer a choice the customer did not state.\n\n"
            "Latest customer turn (authoritative):\n"
            f"{_latest_customer_turn(history)}"
        )
    )

    primary_name = settings.gemini_realtime_interpreter_model
    fallback_name = settings.gemini_realtime_interpreter_fallback_model
    emergency_name = settings.gemini_realtime_interpreter_emergency_model
    primary_model = build_realtime_interpreter_model()

    def invoke_semantic_structured(model) -> UnifiedTurnDecision:
        # Provider-side JSON Schema is still the contract. A single bounded retry
        # handles occasional model output that passes provider shaping but fails
        # Tia's stricter local Pydantic validation. There is no text parsing or
        # lexical intent fallback here.
        try:
            return invoke_typed_structured_output(
                model=model,
                schema=UnifiedTurnDecision,
                messages=[system, user],
            )
        except StructuredOutputError:
            return invoke_typed_structured_output(
                model=model,
                schema=UnifiedTurnDecision,
                messages=[system, user],
            )

    def invoke_primary() -> UnifiedTurnDecision:
        return invoke_semantic_structured(primary_model)

    def invoke_fallback() -> UnifiedTurnDecision:
        fallback_model = build_realtime_interpreter_fallback_model()
        if fallback_model is None:
            raise RuntimeError("Unified turn interpreter fallback model is not configured.")
        return invoke_semantic_structured(fallback_model)

    def invoke_emergency() -> UnifiedTurnDecision:
        emergency_model = build_realtime_interpreter_emergency_model()
        if emergency_model is None:
            raise RuntimeError("Unified turn interpreter emergency model is not configured.")
        return invoke_semantic_structured(emergency_model)

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
    value = _normalize_single_location_decision(invocation.value)
    grounded_hints = validate_grounded_entity_ids(value.entity_hints, clinic_catalog)
    value = value.model_copy(update={"entity_hints": grounded_hints})
    return _normalize_active_booking_decision(value, flow)