from langchain_openai import ChatOpenAI

from app.agents.model_provider import build_chat_model
from app.core.config import Settings, settings


def _settings_kwargs() -> dict[str, str]:
    return {
        "database_url": "postgresql+psycopg://user:pass@localhost:5432/test",
        "migration_database_url": "postgresql+psycopg://user:pass@localhost:5432/test",
        "supabase_url": "https://example.supabase.co",
        "supabase_publishable_key": "sb_publishable_test",
        "supabase_secret_key": "sb_secret_test",
    }


def test_openai_provider_maps_generation_roles_to_luna() -> None:
    configured = Settings(
        _env_file=None,
        **_settings_kwargs(),
        llm_provider="openai",
        openai_api_key="sk-test-not-a-real-key",
        openai_model="gpt-5.6-luna",
    )

    assert configured.gemini_realtime_interpreter_model == "gpt-5.6-luna"
    assert configured.gemini_realtime_interpreter_fallback_model is None
    assert configured.gemini_realtime_composer_model == "gpt-5.6-luna"
    assert configured.gemini_agent_model == "gpt-5.6-luna"
    assert configured.gemini_agent_fallback_model is None
    assert configured.gemini_router_model == "gpt-5.6-luna"
    assert configured.gemini_flow_model == "gpt-5.6-luna"
    assert configured.gemini_onboarding_model == "gpt-5.6-luna"
    assert configured.gemini_utility_model == "gpt-5.6-luna"


def test_openai_provider_builds_responses_api_model(monkeypatch) -> None:
    monkeypatch.setattr(settings, "llm_provider", "openai")
    monkeypatch.setattr(settings, "openai_api_key", "sk-test-not-a-real-key")
    monkeypatch.setattr(settings, "openai_reasoning_effort", "low")
    monkeypatch.setattr(settings, "gemini_agent_model", "gpt-5.6-luna")
    monkeypatch.setattr(settings, "gemini_agent_fallback_model", None)

    model = build_chat_model()

    assert isinstance(model, ChatOpenAI)
    assert model.model_name == "gpt-5.6-luna"
    assert model.use_responses_api is True
    assert model.store is False
    assert model.reasoning == {"effort": "low"}
