from pathlib import Path

BACKEND = Path(__file__).resolve().parent.parent


def test_customer_runtime_has_one_semantic_interpreter() -> None:
    source = (BACKEND / "app/services/agent_chat.py").read_text(encoding="utf-8")

    assert "interpret_customer_turn(" in source
    assert "route_customer_message" not in source
    assert "interpret_active_flow_turn" not in source
    assert "agent_unified_turn_interpreter_enabled" not in source


def test_legacy_interpreter_modules_do_not_call_llms() -> None:
    semantic = (BACKEND / "app/agents/semantic_router.py").read_text(encoding="utf-8")
    flow = (BACKEND / "app/agents/flow_interpreter.py").read_text(encoding="utf-8")
    unified = (BACKEND / "app/agents/turn_interpreter.py").read_text(encoding="utf-8")

    for source in (semantic, flow):
        assert "invoke_typed_structured_output" not in source
        assert "build_semantic_router_model" not in source
        assert "build_flow_interpreter_model" not in source
    assert "invoke_typed_structured_output" in unified
