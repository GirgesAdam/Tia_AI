from pathlib import Path

BACKEND = Path(__file__).resolve().parent.parent


def test_customer_agent_has_bounded_tool_execution() -> None:
    source = (BACKEND / "app/agents/tia_customer_agent.py").read_text(encoding="utf-8")

    assert "agent_max_tool_rounds" in source
    assert "allowed_tool_names" in source
    assert "format_verified_tool_fallback" in source


def test_chat_runtime_keeps_deterministic_authorization_and_retry_recovery() -> None:
    source = (BACKEND / "app/services/agent_chat.py").read_text(encoding="utf-8")

    assert "authorize_tool_execution" in source
    assert "_existing_agent_response_for_inbound" in source
    assert "in_reply_to_message_id" in source
    assert "lock_conversation_ownership" in source


def test_package_write_path_stays_deterministic() -> None:
    source = (BACKEND / "app/services/agent_chat.py").read_text(encoding="utf-8")

    assert "_apply_single_matching_package_to_booking" in source
    assert "validate_package_for_booking" in source
    assert "reserve_package_usage" in source
    assert "_structured_flow_write" in source


def test_response_guard_is_invariant_only() -> None:
    source = (BACKEND / "app/agents/response_guard.py").read_text(encoding="utf-8")

    assert "_FULL_UUID" in source
    assert "replacements =" not in source
    assert "لقد حولت" not in source
