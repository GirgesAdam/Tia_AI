from pathlib import Path


def test_v2_language_boundary_is_limited_to_interpreter_and_future_responder() -> None:
    backend = Path(__file__).resolve().parent.parent
    semantic = (backend / "app/agents/v2/turn_interpreter.py").read_text(encoding="utf-8")
    planner = (backend / "app/services/agent_v2/planner.py").read_text(encoding="utf-8")
    state = (backend / "app/services/agent_v2/state_rules.py").read_text(encoding="utf-8")

    assert "BaseMessage" in semantic
    assert "BaseMessage" not in planner
    assert "HumanMessage" not in planner
    assert "AIMessage" not in planner
    assert "BaseMessage" not in state
    assert "HumanMessage" not in state
    assert "AIMessage" not in state
