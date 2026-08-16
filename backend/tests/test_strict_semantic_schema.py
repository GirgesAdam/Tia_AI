from app.agents.flow_interpreter import FlowTurnDecision
from app.agents.semantic_router import (
    SemanticCapabilityDecision,
    SemanticEntityHints,
)


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
