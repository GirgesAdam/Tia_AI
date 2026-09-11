from app.agents.turn_interpreter import UnifiedTurnDecision
from app.agents.turn_models import FlowTurnDecision, SemanticCapabilityDecision


def test_semantic_schema_is_strict_provider_compatible() -> None:
    schema = SemanticCapabilityDecision.model_json_schema()
    assert schema["additionalProperties"] is False
    assert set(schema["required"]) == set(schema["properties"])

    hints = schema["$defs"]["SemanticEntityHints"]
    assert hints["additionalProperties"] is False
    assert set(hints["required"]) == set(hints["properties"])


def test_flow_interpreter_schema_is_strict_provider_compatible() -> None:
    schema = FlowTurnDecision.model_json_schema()
    assert schema["additionalProperties"] is False
    assert set(schema["required"]) == set(schema["properties"])


def test_unified_turn_schema_is_strict_provider_compatible() -> None:
    schema = UnifiedTurnDecision.model_json_schema()
    assert schema["additionalProperties"] is False
    assert set(schema["required"]) == set(schema["properties"])
