from __future__ import annotations

from datetime import datetime
from typing import Literal

from langchain_core.messages import BaseMessage, HumanMessage, SystemMessage
from pydantic import BaseModel, ConfigDict, Field

from app.agents.llm_runtime import invoke_with_fallback
from app.agents.model_provider import (
    build_semantic_router_fallback_model,
    build_semantic_router_model,
)
from app.agents.structured_output import invoke_typed_structured_output
from app.core.config import settings

SemanticDomain = Literal[
    "services",
    "clinic",
    "booking",
    "appointments",
    "patient",
    "support",
    "communications",
    "general",
]

SemanticCapability = Literal[
    "service_information",
    "pricing",
    "branch_discovery",
    "doctor_discovery",
    "availability_discovery",
    "appointment_creation",
    "appointment_list",
    "appointment_confirmation",
    "appointment_cancellation",
    "appointment_reschedule",
    "customer_profile",
    "customer_history",
    "follow_up_request",
    "marketing_preferences",
    "human_support",
]

RiskFlag = Literal["medical", "complaint", "payment", "urgent"]
HandoffCategory = Literal[
    "medical",
    "complaint",
    "payment",
    "customer_request",
    "booking_exception",
    "agent_uncertain",
    "other",
]
Priority = Literal["low", "normal", "high", "urgent"]
FlowSignal = Literal["none", "start_booking", "start_reschedule", "interrupt"]


def _require_all_schema_fields(schema: dict) -> None:
    """Keep Gemini structured-output schemas strict while preserving Python defaults."""
    properties = schema.get("properties")
    if isinstance(properties, dict):
        schema["required"] = list(properties)


class SemanticEntityHints(BaseModel):
    model_config = ConfigDict(
        extra="forbid", json_schema_extra=_require_all_schema_fields
    )

    # Natural-language observations are retained for audit/explanation only.
    # The grounded unified runtime resolves customer language to canonical IDs
    # from the PostgreSQL clinic catalog before any booking/service lookup.
    service_query: str | None
    branch_query: str | None
    doctor_query: str | None
    service_id: str | None = Field(
        default=None, description="Canonical service UUID from the supplied clinic catalog."
    )
    service_candidate_ids: list[str] = Field(
        default_factory=list,
        description="All plausible service UUIDs from the supplied clinic catalog when no single service is selected.",
    )
    branch_id: str | None = Field(
        default=None, description="Canonical branch UUID from the supplied clinic catalog."
    )
    branch_candidate_ids: list[str] = Field(
        default_factory=list,
        description="All plausible branch UUIDs from the supplied clinic catalog when no single branch is selected.",
    )
    doctor_id: str | None = Field(
        default=None, description="Canonical doctor UUID from the supplied clinic catalog."
    )
    doctor_candidate_ids: list[str] = Field(
        default_factory=list,
        description="All plausible doctor UUIDs from the supplied clinic catalog when no single doctor is selected.",
    )
    requested_date: str | None = Field(
        description="YYYY-MM-DD when semantically resolved, otherwise null."
    )
    requested_start_time: str | None = Field(
        default=None,
        description=(
            "Exact local appointment start HH:MM when the customer requests one precise "
            "start time (for example: at 6 PM / الساعة 6), otherwise null."
        ),
    )
    not_before_time: str | None = Field(
        description="Local HH:MM when semantically resolved, otherwise null."
    )
    not_after_time: str | None = Field(
        description="Local HH:MM when semantically resolved, otherwise null."
    )
    appointment_reference: str | None


class SemanticCapabilityDecision(BaseModel):
    """
    Provider-stable structured semantic contract.

    Every property is required. Semantically optional values use explicit null
    rather than omitted fields, which keeps downstream policy deterministic.
    """

    model_config = ConfigDict(
        extra="forbid", json_schema_extra=_require_all_schema_fields
    )

    domains: list[SemanticDomain]
    capabilities: list[SemanticCapability]
    risk_flags: list[RiskFlag]
    flow_signal: FlowSignal
    entity_hints: SemanticEntityHints
    missing_information: list[str]
    recommended_handoff_category: HandoffCategory
    recommended_handoff_priority: Priority
    confidence: float
    reason: str


def empty_entity_hints() -> SemanticEntityHints:
    return SemanticEntityHints(
        service_query=None,
        branch_query=None,
        doctor_query=None,
        requested_date=None,
        requested_start_time=None,
        not_before_time=None,
        not_after_time=None,
        appointment_reference=None,
    )


def _history_excerpt(history: list[BaseMessage]) -> str:
    selected = history[-settings.agent_router_history_messages :]
    lines: list[str] = []
    for message in selected:
        if not isinstance(message.content, str) or not message.content.strip():
            continue
        role = "customer" if isinstance(message, HumanMessage) else "assistant"
        text = " ".join(message.content.strip().split())
        if len(text) > 700:
            text = text[:700] + "…"
        lines.append(f"{role}: {text}")
    return "\n".join(lines)


def route_customer_message(
    *,
    history: list[BaseMessage],
    timezone_name: str,
    local_now: datetime,
) -> SemanticCapabilityDecision:
    """Route by semantic capabilities, not one exclusive intent and not keywords."""
    if not settings.agent_semantic_router_enabled:
        return SemanticCapabilityDecision(
            domains=["general"],
            capabilities=[],
            risk_flags=[],
            flow_signal="none",
            entity_hints=empty_entity_hints(),
            missing_information=[],
            recommended_handoff_category="other",
            recommended_handoff_priority="normal",
            confidence=0.0,
            reason="Semantic router disabled by configuration.",
        )

    system = SystemMessage(
        content=(
            "You are Tia's semantic capability router for an aesthetic clinic. "
            "Return only the structured schema. Never answer the customer. "
            "Do not return implementation tool names. Classify the meaning of the "
            "whole customer turn, allowing multiple simultaneous capabilities.\n\n"
            "IMPORTANT OUTPUT CONTRACT: every schema field must be present. "
            "For unknown optional entity values, use null. For no capabilities, "
            "risks, domains, or missing items, use an empty array.\n\n"
            "Examples of valid multi-capability meaning:\n"
            "- asking price + wanting a booking => pricing + availability_discovery "
            "+ appointment_creation.\n"
            "- asking about a service while asking for doctors => service_information "
            "+ doctor_discovery.\n"
            "- asking what the current customer previously did at the clinic, which services "
            "they received, when they last visited, or how much they previously paid => "
            "customer_history. This is a read-only history request, not a payment dispute.\n"
            "- asking the clinic to call/contact/remind the current customer later, at a "
            "specific future time => follow_up_request. This is a CRM staff follow-up, "
            "not an appointment reminder automation.\n"
            "- explicitly asking to stop/start promotional or marketing messages => "
            "marketing_preferences. This is the current customer's own consent preference.\n\n"
            "Safety semantics:\n"
            "- diagnosis, symptoms, pregnancy/breastfeeding, medication interactions, "
            "personalized treatment suitability, or medical risk => risk_flags includes "
            "medical and recommend medical handoff.\n"
            "- complaints, payment disputes, explicit request for staff, or urgent "
            "customer-service ownership => include human_support and the relevant risk.\n"
            "Medical risk must not be hidden by a simultaneous booking capability.\n\n"
            "Flow signals:\n"
            "- start_booking when the customer is beginning/continuing discovery for a "
            "new appointment.\n"
            "- start_reschedule when moving an existing appointment.\n"
            "- interrupt when the current task clearly needs to yield to human/safety.\n"
            "- none otherwise.\n\n"
            "Entity hints are semantic observations only and never authorize a write. This "
            "legacy router is not given the clinic catalog, so service_id/branch_id/doctor_id "
            "must be null and all *_candidate_ids lists must be empty. The grounded unified "
            "interpreter is the only path that selects canonical clinic IDs.\n\n"
            f"Clinic timezone: {timezone_name}\n"
            f"Clinic local date/time now: {local_now.isoformat()}\n"
            "Resolve relative date/time language such as today, tomorrow, next Thursday, "
            "النهارده, بكرة, or الخميس الجاي against this clinic-local clock. When the "
            "relative date is semantically clear, requested_date MUST be the resolved "
            "YYYY-MM-DD rather than null. Time semantics must distinguish exact starts from "
            "windows: 'at 6 PM' / 'الساعة 6' => requested_start_time='18:00' and both "
            "not_before_time/not_after_time null; 'after 6' => not_before_time='18:00'; "
            "'before 8' => not_after_time='20:00'; 'from 6 to 8' => both bounds. Never "
            "encode an exact start as a zero-width time window. Do not guess when the "
            "customer's wording is genuinely ambiguous."
        )
    )
    user = HumanMessage(content=(f"Recent conversation:\n{_history_excerpt(history)}"))
    primary_model = build_semantic_router_model()
    fallback_name = settings.gemini_router_fallback_model

    def invoke_fallback():
        fallback_model = build_semantic_router_fallback_model()
        if fallback_model is None:
            raise RuntimeError("Semantic router fallback model is not configured.")
        return invoke_typed_structured_output(
            model=fallback_model,
            schema=SemanticCapabilityDecision,
            messages=[system, user],
        )

    has_fallback = bool(fallback_name and fallback_name != settings.gemini_router_model)
    invocation = invoke_with_fallback(
        primary_call=lambda: invoke_typed_structured_output(
            model=primary_model,
            schema=SemanticCapabilityDecision,
            messages=[system, user],
        ),
        primary_model_name=settings.gemini_router_model,
        fallback_call=invoke_fallback if has_fallback else None,
        fallback_model_name=fallback_name if has_fallback else None,
        operation="semantic-router",
        circuit_breaker_cooldown_seconds=settings.llm_realtime_circuit_breaker_cooldown_seconds,
    )
    return invocation.value
