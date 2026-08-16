from app.agents.flow_interpreter import FlowTurnDecision
from app.agents.semantic_router import empty_entity_hints


def test_flow_turn_can_represent_structured_selection_without_keywords() -> None:
    turn = FlowTurnDecision(
        action="select_option",
        capabilities=["appointment_creation"],
        risk_flags=[],
        entity_hints=empty_entity_hints(),
        selection_index=2,
        selection_time=None,
        missing_information=[],
        recommended_handoff_category="other",
        recommended_handoff_priority="normal",
        confidence=0.98,
        reason="Customer chose the second previously offered option.",
    )
    assert turn.action == "select_option"
    assert turn.selection_index == 2


def test_flow_turn_can_interrupt_for_medical_risk() -> None:
    turn = FlowTurnDecision(
        action="interrupt",
        capabilities=["human_support"],
        risk_flags=["medical"],
        entity_hints=empty_entity_hints(),
        selection_index=None,
        selection_time=None,
        missing_information=[],
        recommended_handoff_category="medical",
        recommended_handoff_priority="high",
        confidence=0.99,
        reason="Medical suitability requires clinical review.",
    )
    assert "medical" in turn.risk_flags
