from pathlib import Path


def test_realtime_defaults_use_lite_first_and_no_37_critical_path() -> None:
    backend = Path(__file__).resolve().parent.parent
    config = (backend / "app/core/config.py").read_text(encoding="utf-8")

    assert 'gemini_realtime_interpreter_model: str = "gemini-3.5-flash-lite"' in config
    assert 'gemini_realtime_interpreter_fallback_model: str | None = "gemini-3.6-flash"' in config
    assert 'gemini_realtime_interpreter_emergency_model: str | None = "gemini-3.5-flash"' in config
    assert 'gemini_realtime_composer_model: str = "gemini-3.5-flash-lite"' in config
    assert 'gemini_realtime_composer_fallback_model: str | None = "gemini-3.6-flash"' in config
    assert 'gemini_agent_model: str = "gemini-3.6-flash"' in config
    assert 'gemini_router_model: str = "gemini-3.6-flash"' in config
    assert 'gemini_flow_model: str = "gemini-3.6-flash"' in config


def test_realtime_model_chain_source_has_no_customer_text_heuristics() -> None:
    backend = Path(__file__).resolve().parent.parent
    runtime = (backend / "app/agents/llm_runtime.py").read_text(encoding="utf-8").lower()
    turn = (backend / "app/agents/turn_interpreter.py").read_text(encoding="utf-8").lower()

    # Regex in llm_runtime is allowed only for provider-secret redaction; customer
    # language interpretation remains semantic/LLM-owned rather than lexical.
    assert "_sensitive_provider_patterns" in runtime
    for token in ("re.search", "re.match", "difflib."):
        assert token not in runtime
    for token in ("re.compile", "re.search", "re.match", "difflib."):
        assert token not in turn
