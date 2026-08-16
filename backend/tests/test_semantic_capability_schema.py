from app.agents.semantic_router import (
    SemanticCapabilityDecision,
    empty_entity_hints,
)


def route(*, capabilities, risk_flags=None):
    return SemanticCapabilityDecision(
        domains=["services", "booking"],
        capabilities=capabilities,
        risk_flags=risk_flags or [],
        flow_signal="start_booking",
        entity_hints=empty_entity_hints(),
        missing_information=[],
        recommended_handoff_category="medical" if risk_flags else "other",
        recommended_handoff_priority="high" if risk_flags else "normal",
        confidence=0.97,
        reason="test",
    )


def test_one_turn_can_have_pricing_and_booking_capabilities() -> None:
    decision = route(
        capabilities=[
            "pricing",
            "availability_discovery",
            "appointment_creation",
        ]
    )
    assert "pricing" in decision.capabilities
    assert "appointment_creation" in decision.capabilities


def test_medical_risk_is_independent_of_booking_capability() -> None:
    decision = route(
        capabilities=[
            "service_information",
            "availability_discovery",
            "appointment_creation",
        ],
        risk_flags=["medical"],
    )
    assert "medical" in decision.risk_flags
    assert "appointment_creation" in decision.capabilities
