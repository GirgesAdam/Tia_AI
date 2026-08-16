from functools import lru_cache
from typing import Literal

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    app_name: str = "Tia AI"
    environment: str = "staging"
    debug: bool = False
    api_v1_prefix: str = "/api/v1"
    docs_enabled: bool = True
    log_level: str = "INFO"

    database_url: str
    migration_database_url: str

    supabase_url: str
    supabase_publishable_key: str
    supabase_secret_key: str

    llm_provider: Literal["gemini"] = "gemini"
    llm_timeout_seconds: int = Field(default=60, ge=5, le=300)
    llm_max_retries: int = Field(default=2, ge=0, le=6)
    llm_max_output_tokens: int = Field(default=2048, ge=256, le=8192)

    # Conversation/context budgets are product-quality bounds, not free-tier hacks.
    agent_history_messages: int = Field(default=24, ge=4, le=80)
    agent_operational_context_items: int = Field(default=8, ge=1, le=20)
    agent_operational_context_max_chars: int = Field(
        default=16000,
        ge=2000,
        le=50000,
    )
    agent_recursion_limit: int = Field(default=16, ge=4, le=64)

    agent_semantic_router_enabled: bool = True
    agent_router_max_output_tokens: int = Field(default=1024, ge=256, le=4096)
    agent_router_history_messages: int = Field(default=8, ge=2, le=24)

    agent_flow_ttl_hours: int = Field(default=24, ge=1, le=168)
    agent_flow_interpreter_max_output_tokens: int = Field(
        default=1024,
        ge=256,
        le=4096,
    )
    agent_flow_interpreter_history_messages: int = Field(
        default=8,
        ge=2,
        le=24,
    )

    gemini_api_key: str | None = None

    gemini_agent_model: str = "gemini-3.7-flash"
    gemini_agent_thinking_level: Literal["low", "medium", "high"] = "medium"

    gemini_router_model: str = "gemini-3.7-flash"
    gemini_router_thinking_level: Literal["low", "medium", "high"] = "low"

    gemini_flow_model: str = "gemini-3.7-flash"
    gemini_flow_thinking_level: Literal["low", "medium", "high"] = "low"

    # AI-assisted onboarding: primary quality model plus a stable same-family
    # failover used only after retryable 5xx capacity failures exhaust the
    # Google/LangChain client retries. 400/429 never switch models.
    gemini_onboarding_model: str = "gemini-3.7-flash"
    gemini_onboarding_fallback_model: str | None = "gemini-3.6-flash"
    gemini_onboarding_thinking_level: Literal["low", "medium", "high"] = "medium"
    gemini_onboarding_max_output_tokens: int = Field(
        default=8192,
        ge=2048,
        le=65536,
    )

    # Cheap background/utility workload model. Not used for write authorization.
    gemini_utility_model: str = "gemini-3.5-flash-lite"
    gemini_utility_thinking_level: Literal[
        "minimal",
        "low",
        "medium",
        "high",
    ] = "minimal"

    gemini_embedding_model: str = "gemini-embedding-001"

    cors_origins: list[str] = Field(default_factory=list)

    db_pool_size: int = 5
    db_max_overflow: int = 5
    db_pool_timeout_seconds: int = 30
    db_pool_recycle_seconds: int = 1800

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    @field_validator("cors_origins", mode="before")
    @classmethod
    def parse_cors_origins(cls, value: object) -> list[str]:
        if value is None or value == "":
            return []
        if isinstance(value, str):
            return [item.strip() for item in value.split(",") if item.strip()]
        if isinstance(value, list):
            return value
        raise ValueError("CORS_ORIGINS must be a comma-separated string or list.")

    @field_validator("database_url", "migration_database_url")
    @classmethod
    def require_psycopg_scheme(cls, value: str) -> str:
        if not value.startswith("postgresql+psycopg://"):
            raise ValueError(
                "Database URLs must start with postgresql+psycopg:// for SQLAlchemy + Psycopg 3."
            )
        return value

    @field_validator("supabase_url")
    @classmethod
    def validate_supabase_url(cls, value: str) -> str:
        normalized = value.rstrip("/")
        if not normalized.startswith("https://") or ".supabase.co" not in normalized:
            raise ValueError("SUPABASE_URL must be the hosted https://<project-ref>.supabase.co URL.")
        return normalized

    @field_validator("supabase_publishable_key")
    @classmethod
    def validate_publishable_key(cls, value: str) -> str:
        if not value.startswith("sb_publishable_"):
            raise ValueError("Use a Supabase sb_publishable_... key for SUPABASE_PUBLISHABLE_KEY.")
        return value

    @field_validator("supabase_secret_key")
    @classmethod
    def validate_secret_key(cls, value: str) -> str:
        if not value.startswith("sb_secret_"):
            raise ValueError("Use a Supabase sb_secret_... key for SUPABASE_SECRET_KEY.")
        return value

    @field_validator(
        "gemini_api_key",
        "gemini_onboarding_fallback_model",
        mode="before",
    )
    @classmethod
    def normalize_optional_api_key(cls, value: object) -> object:
        if isinstance(value, str):
            value = value.strip()
            return value or None
        return value

    @property
    def supabase_auth_issuer(self) -> str:
        return f"{self.supabase_url}/auth/v1"

    @property
    def is_production(self) -> bool:
        return self.environment.lower() == "production"


@lru_cache
def get_settings() -> Settings:
    return Settings()


settings = get_settings()
