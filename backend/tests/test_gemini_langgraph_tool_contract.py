from pathlib import Path


def test_main_agent_still_uses_native_langchain_tool_binding() -> None:
    backend = Path(__file__).resolve().parent.parent
    source = (backend / "app/agents/tia_customer_agent.py").read_text(
        encoding="utf-8"
    )

    assert ".bind_tools(tools)" in source
    assert "ToolNode(" in source
    assert "invoke_model(" in source
    assert "invoke_chat_model_with_resilience" not in source
