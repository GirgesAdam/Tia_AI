from pathlib import Path


def test_main_agent_keeps_native_tool_binding_with_bounded_custom_tool_loop() -> None:
    backend = Path(__file__).resolve().parent.parent
    source = (backend / "app/agents/tia_customer_agent.py").read_text(encoding="utf-8")

    assert ".bind_tools(tools)" in source
    assert "StateGraph(MessagesState)" in source
    assert 'builder.add_node("tools", call_tools)' in source
    assert "tools_condition" in source
    assert "ToolNode(" not in source
    assert "invoke_model(" in source
    assert "invoke_chat_model_with_resilience" not in source
