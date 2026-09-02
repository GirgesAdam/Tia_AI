import pytest

from app.agents.capability_policy import (
    ToolAuthorizationError,
    authorize_tool_execution,
    resolve_capability_policy,
)
from app.agents.semantic_router import (
    SemanticCapabilityDecision,
    empty_entity_hints,
)


def decision(**kwargs):
    return SemanticCapabilityDecision(
        domains=kwargs.get("domains", ["booking"]),
        capabilities=kwargs.get("capabilities", []),
        risk_flags=kwargs.get("risk_flags", []),
        flow_signal=kwargs.get("flow_signal", "none"),
        entity_hints=empty_entity_hints(),
        missing_information=[],
        recommended_handoff_category=kwargs.get("category", "other"),
        recommended_handoff_priority=kwargs.get("priority", "normal"),
        confidence=0.95,
        reason="test",
    )


def test_multi_capability_policy_unions_tools() -> None:
    policy = resolve_capability_policy(
        decision(
            capabilities=[
                "pricing",
                "availability_discovery",
                "appointment_creation",
            ]
        )
    )
    assert "search_services" in policy.allowed_tools
    assert "get_booking_options" in policy.allowed_tools
    assert "book_appointment" in policy.allowed_tools


def test_medical_risk_overrides_simultaneous_booking_write() -> None:
    policy = resolve_capability_policy(
        decision(
            capabilities=[
                "pricing",
                "availability_discovery",
                "appointment_creation",
            ],
            risk_flags=["medical"],
            category="medical",
            priority="high",
        )
    )
    assert policy.requires_human is True
    assert policy.allowed_tools == {"escalate_to_human"}


def test_normal_policy_does_not_expose_handoff_tool() -> None:
    policy = resolve_capability_policy(decision(capabilities=["pricing"]))

    assert policy.requires_human is False
    assert "escalate_to_human" not in policy.allowed_tools


def test_explicit_human_support_exposes_handoff() -> None:
    policy = resolve_capability_policy(
        decision(
            capabilities=["human_support"],
            category="customer_request",
        )
    )

    assert policy.requires_human is True
    assert policy.allowed_tools == {"escalate_to_human"}


def test_write_tool_requires_semantic_capability() -> None:
    policy = resolve_capability_policy(decision(capabilities=["availability_discovery"]))
    with pytest.raises(ToolAuthorizationError):
        authorize_tool_execution(policy, "book_appointment")


def test_booking_write_is_authorized_when_capability_exists() -> None:
    policy = resolve_capability_policy(
        decision(
            capabilities=[
                "availability_discovery",
                "appointment_creation",
            ]
        )
    )
    authorize_tool_execution(policy, "book_appointment")
