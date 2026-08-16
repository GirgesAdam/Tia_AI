from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable

from app.agents.semantic_router import (
    HandoffCategory,
    Priority,
    RiskFlag,
    SemanticCapability,
    SemanticCapabilityDecision,
)


CAPABILITY_TOOL_POLICY: dict[str, frozenset[str]] = {
    "service_information": frozenset({"search_services"}),
    "pricing": frozenset({"search_services"}),
    "branch_discovery": frozenset({"list_branches"}),
    "doctor_discovery": frozenset({"list_doctors"}),
    "availability_discovery": frozenset({"get_booking_options"}),
    "appointment_creation": frozenset({"book_appointment"}),
    "appointment_list": frozenset({"get_customer_appointments"}),
    "appointment_confirmation": frozenset(
        {"get_customer_appointments", "confirm_appointment"}
    ),
    "appointment_cancellation": frozenset(
        {"get_customer_appointments", "cancel_appointment"}
    ),
    "appointment_reschedule": frozenset(
        {
            "get_customer_appointments",
            "get_reschedule_options",
            "reschedule_appointment",
        }
    ),
    "customer_profile": frozenset({"get_customer_profile"}),
    "email_communication": frozenset({"send_email_to_customer"}),
    "human_support": frozenset({"escalate_to_human"}),
}

WRITE_TOOL_CAPABILITY: dict[str, str] = {
    "book_appointment": "appointment_creation",
    "confirm_appointment": "appointment_confirmation",
    "cancel_appointment": "appointment_cancellation",
    "reschedule_appointment": "appointment_reschedule",
    "send_email_to_customer": "email_communication",
    "escalate_to_human": "human_support",
}

WRITE_CAPABILITIES = frozenset(WRITE_TOOL_CAPABILITY.values())


@dataclass(frozen=True)
class CapabilityPolicyDecision:
    capabilities: frozenset[str]
    allowed_tools: frozenset[str]
    write_capabilities: frozenset[str]
    requires_human: bool
    handoff_category: str
    handoff_priority: str
    risk_flags: frozenset[str]


class ToolAuthorizationError(PermissionError):
    pass


def _risk_handoff(
    risks: set[str],
    decision: SemanticCapabilityDecision,
) -> tuple[bool, HandoffCategory, Priority]:
    if "medical" in risks:
        return True, "medical", "high"
    if "complaint" in risks:
        return True, "complaint", decision.recommended_handoff_priority
    if "payment" in risks:
        return True, "payment", decision.recommended_handoff_priority
    if "urgent" in risks:
        return True, decision.recommended_handoff_category, "urgent"
    if "human_support" in decision.capabilities:
        return (
            True,
            decision.recommended_handoff_category
            if decision.recommended_handoff_category != "other"
            else "customer_request",
            decision.recommended_handoff_priority,
        )
    return False, "other", "normal"


def resolve_capability_policy(
    decision: SemanticCapabilityDecision,
    *,
    inherited_capabilities: Iterable[str] = (),
) -> CapabilityPolicyDecision:
    """
    Deterministic policy boundary.

    The LLM describes semantic capabilities. Python maps them to tool exposure
    and write authority. Medical/customer-support risk can override simultaneous
    booking capabilities.
    """
    capabilities = {
        str(item)
        for item in (*decision.capabilities, *tuple(inherited_capabilities))
        if str(item) in CAPABILITY_TOOL_POLICY
    }
    risks = {str(item) for item in decision.risk_flags}

    requires_human, category, priority = _risk_handoff(risks, decision)
    if requires_human:
        capabilities.add("human_support")
        allowed_tools = {"escalate_to_human"}
    else:
        allowed_tools: set[str] = {"escalate_to_human"}
        for capability in capabilities:
            allowed_tools.update(CAPABILITY_TOOL_POLICY[capability])

    write_caps = capabilities.intersection(WRITE_CAPABILITIES)

    return CapabilityPolicyDecision(
        capabilities=frozenset(capabilities),
        allowed_tools=frozenset(allowed_tools),
        write_capabilities=frozenset(write_caps),
        requires_human=requires_human,
        handoff_category=category,
        handoff_priority=priority,
        risk_flags=frozenset(risks),
    )


def authorize_tool_execution(
    policy: CapabilityPolicyDecision,
    tool_name: str,
) -> None:
    if tool_name not in policy.allowed_tools:
        raise ToolAuthorizationError(
            f"Tool {tool_name!r} is not enabled by the current capability policy."
        )

    required = WRITE_TOOL_CAPABILITY.get(tool_name)
    if required is not None and required not in policy.capabilities:
        raise ToolAuthorizationError(
            f"Write tool {tool_name!r} requires capability {required!r}."
        )
