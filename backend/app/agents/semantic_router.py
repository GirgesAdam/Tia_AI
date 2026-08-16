from __future__ import annotations

from typing import Literal

from langchain_core.messages import BaseMessage, HumanMessage, SystemMessage
from pydantic import BaseModel, ConfigDict, Field

from app.agents.model_provider import build_semantic_router_model
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
    "email_communication",
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


class SemanticEntityHints(BaseModel):
    model_config = ConfigDict(extra="forbid")

    service_query: str | None
    branch_query: str | None
    doctor_query: str | None
    requested_date: str | None = Field(
        description="YYYY-MM-DD when semantically resolved, otherwise null."
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

    model_config = ConfigDict(extra="forbid")

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
            "- asking to send the current customer details/summary to their saved "
            "email => email_communication. Never infer permission to email a third "
            "party.\n\n"
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
            "Entity hints are semantic observations only. They are not database IDs and "
            "never authorize a write."
        )
    )
    user = HumanMessage(
        content=(
            "Recent conversation:\n"
            f"{_history_excerpt(history)}"
        )
    )
    return invoke_typed_structured_output(
        model=build_semantic_router_model(),
        schema=SemanticCapabilityDecision,
        messages=[system, user],
    )
