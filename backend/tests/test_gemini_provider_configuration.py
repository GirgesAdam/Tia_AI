from pathlib import Path

from app.core.config import Settings


def test_legacy_agent_runtime_defaults_keep_37_off_realtime_critical_path() -> None:
    assert Settings.model_fields["llm_provider"].default == "gemini"
    assert Settings.model_fields["gemini_agent_model"].default == "gemini-3.6-flash"
    assert Settings.model_fields["gemini_router_model"].default == "gemini-3.6-flash"
    assert Settings.model_fields["gemini_flow_model"].default == "gemini-3.6-flash"
    assert Settings.model_fields["gemini_agent_fallback_model"].default == "gemini-3.5-flash"
    assert Settings.model_fields["gemini_router_fallback_model"].default == "gemini-3.5-flash"
    assert Settings.model_fields["gemini_flow_fallback_model"].default == "gemini-3.5-flash"
    assert Settings.model_fields["llm_realtime_max_retries"].default == 0


def test_realtime_runtime_uses_low_thinking_and_bounded_tool_loop() -> None:
    assert Settings.model_fields["gemini_agent_thinking_level"].default == "low"
    assert Settings.model_fields["gemini_router_thinking_level"].default == "low"
    assert Settings.model_fields["gemini_flow_thinking_level"].default == "low"
    assert Settings.model_fields["gemini_onboarding_thinking_level"].default == "medium"
    assert Settings.model_fields["gemini_utility_thinking_level"].default == "minimal"
    assert Settings.model_fields["agent_max_tool_rounds"].default == 2
    assert Settings.model_fields["agent_recursion_limit"].default == 8


def test_runtime_files_have_no_groq_dependency() -> None:
    backend = Path(__file__).resolve().parent.parent
    files = (
        "app/core/config.py",
        "app/agents/model_provider.py",
        "app/agents/structured_output.py",
        "app/agents/llm_runtime.py",
    )
    source = "\n".join(
        (backend / relative).read_text(encoding="utf-8") for relative in files
    ).lower()

    assert "chatgroq" not in source
    assert "langchain_groq" not in source
    assert "groq_api_key" not in source
    assert "llm_rate_limit_max_retries" not in source


def test_gemini_base_models_are_process_cached() -> None:
    backend = Path(__file__).resolve().parent.parent
    source = (backend / "app/agents/model_provider.py").read_text(encoding="utf-8")
    assert "@lru_cache(maxsize=32)" in source
    assert "def _cached_gemini_model" in source
