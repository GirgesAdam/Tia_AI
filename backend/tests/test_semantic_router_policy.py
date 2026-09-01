from app.agents.capability_policy import resolve_capability_policy
from app.agents.semantic_router import (
    SemanticCapabilityDecision,
    empty_entity_hints,
)


def make(capabilities, *, risks=None):
    return SemanticCapabilityDecision(
        domains=["booking"],
        capabilities=capabilities,
        risk_flags=risks or [],
        flow_signal="none",
        entity_hints=empty_entity_hints(),
        missing_information=[],
        recommended_handoff_category="medical" if risks else "other",
        recommended_handoff_priority="high" if risks else "normal",
        confidence=0.95,
        reason="test",
    )


def test_booking_capabilities_map_to_booking_tools() -> None:
    tools = resolve_capability_policy(
        make(["availability_discovery", "appointment_creation"])
    ).allowed_tools
    assert "get_booking_options" in tools
    assert "book_appointment" in tools


def test_medical_risk_collapses_tool_surface_to_handoff() -> None:
    policy = resolve_capability_policy(
        make(
            ["service_information", "appointment_creation"],
            risks=["medical"],
        )
    )
    assert policy.allowed_tools == {"escalate_to_human"}


def test_followup_request_maps_to_one_backend_validated_write_tool() -> None:
    policy = resolve_capability_policy(make(["follow_up_request"]))
    assert policy.allowed_tools == {"create_follow_up_task", "escalate_to_human"}
    assert policy.write_capabilities == {"follow_up_request"}
