from pathlib import Path

from app.core.config import Settings


def test_default_runtime_is_gemini_37_flash() -> None:
    assert Settings.model_fields["llm_provider"].default == "gemini"
    assert Settings.model_fields["gemini_agent_model"].default == "gemini-3.7-flash"
    assert Settings.model_fields["gemini_router_model"].default == "gemini-3.7-flash"
    assert Settings.model_fields["gemini_flow_model"].default == "gemini-3.7-flash"


def test_model_roles_have_expected_thinking_levels() -> None:
    assert Settings.model_fields["gemini_agent_thinking_level"].default == "medium"
    assert Settings.model_fields["gemini_router_thinking_level"].default == "low"
    assert Settings.model_fields["gemini_flow_thinking_level"].default == "low"
    assert Settings.model_fields["gemini_onboarding_thinking_level"].default == "medium"
    assert Settings.model_fields["gemini_utility_thinking_level"].default == "minimal"


def test_runtime_files_have_no_groq_dependency() -> None:
    backend = Path(__file__).resolve().parent.parent
    files = (
        "app/core/config.py",
        "app/agents/model_provider.py",
        "app/agents/structured_output.py",
        "app/agents/llm_runtime.py",
    )
    source = "\\n".join(
        (backend / relative).read_text(encoding="utf-8")
        for relative in files
    ).lower()

    assert "chatgroq" not in source
    assert "langchain_groq" not in source
    assert "groq_api_key" not in source
    assert "llm_rate_limit_max_retries" not in source
