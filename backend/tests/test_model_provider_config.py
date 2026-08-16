from app.core.config import Settings


BASE = {
    "DATABASE_URL": "postgresql+psycopg://user:pass@localhost:5432/db",
    "MIGRATION_DATABASE_URL": "postgresql+psycopg://user:pass@localhost:5432/db",
    "SUPABASE_URL": "https://abcdefghijklmnop.supabase.co",
    "SUPABASE_PUBLISHABLE_KEY": "sb_publishable_test",
    "SUPABASE_SECRET_KEY": "sb_secret_test",
}


def test_groq_is_default_provider(monkeypatch) -> None:
    for key, value in BASE.items():
        monkeypatch.setenv(key, value)

    settings = Settings(_env_file=None)

    assert settings.llm_provider == "groq"
    assert settings.groq_model == "openai/gpt-oss-20b"


def test_openai_can_still_be_selected(monkeypatch) -> None:
    for key, value in BASE.items():
        monkeypatch.setenv(key, value)

    monkeypatch.setenv("LLM_PROVIDER", "openai")
    monkeypatch.setenv("OPENAI_API_KEY", "sk-test")

    settings = Settings(_env_file=None)

    assert settings.llm_provider == "openai"
    assert settings.openai_api_key == "sk-test"
