from app.core.config import Settings

BASE = {
    "DATABASE_URL": "postgresql+psycopg://user:pass@localhost:5432/db",
    "MIGRATION_DATABASE_URL": "postgresql+psycopg://user:pass@localhost:5432/db",
    "SUPABASE_URL": "https://abcdefghijklmnop.supabase.co",
    "SUPABASE_PUBLISHABLE_KEY": "sb_publishable_test",
    "SUPABASE_SECRET_KEY": "sb_secret_test",
}


def _set_base(monkeypatch) -> None:
    for key, value in BASE.items():
        monkeypatch.setenv(key, value)


def test_gemini_is_the_only_configured_provider(monkeypatch) -> None:
    _set_base(monkeypatch)

    settings = Settings(_env_file=None)

    assert settings.llm_provider == "gemini"
    assert settings.gemini_agent_model == "gemini-3.6-flash"
    assert settings.gemini_router_model == "gemini-3.6-flash"
    assert settings.gemini_flow_model == "gemini-3.6-flash"
    # Realtime provider calls do not retry the same overloaded model.
    assert settings.llm_realtime_max_retries == 0


def test_legacy_customer_runtime_defaults_to_35_failover(monkeypatch) -> None:
    _set_base(monkeypatch)

    settings = Settings(_env_file=None)

    assert settings.gemini_agent_fallback_model == "gemini-3.5-flash"
    assert settings.gemini_router_fallback_model == "gemini-3.5-flash"
    assert settings.gemini_flow_fallback_model == "gemini-3.5-flash"


def test_realtime_agent_loop_is_bounded(monkeypatch) -> None:
    _set_base(monkeypatch)

    settings = Settings(_env_file=None)

    assert settings.agent_recursion_limit == 8
    assert settings.agent_max_tool_rounds == 2
    assert settings.agent_prefetch_reads_enabled is True
    assert settings.channel_dispatch_max_attempts == 5


def test_runtime_fallbacks_can_be_disabled_with_empty_env_values(monkeypatch) -> None:
    _set_base(monkeypatch)
    monkeypatch.setenv("GEMINI_AGENT_FALLBACK_MODEL", "")
    monkeypatch.setenv("GEMINI_ROUTER_FALLBACK_MODEL", "")
    monkeypatch.setenv("GEMINI_FLOW_FALLBACK_MODEL", "")

    settings = Settings(_env_file=None)

    assert settings.gemini_agent_fallback_model is None
    assert settings.gemini_router_fallback_model is None
    assert settings.gemini_flow_fallback_model is None
