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

    # Recruiter/public demo sandbox. The agent and database writes remain real,
    # while provider delivery is disabled unless explicitly allowed.
    demo_mode: bool = False
    demo_allow_external_dispatch: bool = False
    demo_agent_hourly_turn_limit: int = Field(default=60, ge=1, le=500)

    database_url: str
    migration_database_url: str

    supabase_url: str
    supabase_publishable_key: str
    supabase_secret_key: str

    llm_provider: Literal["gemini"] = "gemini"
    llm_timeout_seconds: int = Field(default=60, ge=5, le=300)
    llm_max_retries: int = Field(default=2, ge=0, le=6)
    # Customer-facing WhatsApp/API turns are latency-sensitive. With the current
    # langchain-google-genai/google-genai stack, max_retries=1 maps to one total
    # provider attempt (zero same-model retries). That lets a provider 5xx cross
    # over to the configured fallback immediately instead of waiting on repeated
    # calls to the same overloaded model. Onboarding/background workloads keep
    # the normal llm_max_retries policy above.
    llm_realtime_max_retries: int = Field(default=0, ge=0, le=2)
    # After a realtime primary-model 5xx, temporarily bypass that model for new
    # turns instead of paying the same capacity timeout on every message.
    llm_realtime_circuit_breaker_cooldown_seconds: int = Field(default=120, ge=0, le=900)
    llm_max_output_tokens: int = Field(default=2048, ge=256, le=8192)

    # Conversation/context budgets are product-quality bounds, not free-tier hacks.
    agent_history_messages: int = Field(default=24, ge=4, le=80)
    agent_operational_context_items: int = Field(default=8, ge=1, le=20)
    agent_operational_context_max_chars: int = Field(
        default=16000,
        ge=2000,
        le=50000,
    )
    agent_recursion_limit: int = Field(default=8, ge=4, le=32)
    agent_max_tool_rounds: int = Field(default=2, ge=1, le=4)
    agent_prefetch_reads_enabled: bool = True

    # PostgreSQL owns outbound retry state. n8n performs one provider attempt per
    # claimed dispatch, then reports the real provider result back here.
    channel_dispatch_max_attempts: int = Field(default=5, ge=1, le=20)

    # Unified customer-turn orchestration is now the default realtime path. The
    # legacy split router/flow interpreter remains behind this flag as rollback
    # insurance while deterministic policy/state/tool/database layers stay authoritative.
    agent_unified_turn_interpreter_enabled: bool = True

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

    # Realtime customer path. Gemini 3.5 Flash-Lite is intentionally the first
    # interpreter/composer model: it is optimized for low-latency, high-throughput
    # extraction/routing workloads and supports structured output. Provider-side
    # 5xx failures advance through the bounded model chain below; each model has
    # its own process-local circuit breaker in llm_runtime.py.
    gemini_realtime_interpreter_model: str = "gemini-3.5-flash-lite"
    gemini_realtime_interpreter_fallback_model: str | None = "gemini-3.6-flash"
    gemini_realtime_interpreter_emergency_model: str | None = "gemini-3.5-flash"
    gemini_realtime_interpreter_thinking_level: Literal[
        "minimal", "low", "medium", "high"
    ] = "minimal"

    gemini_realtime_composer_model: str = "gemini-3.5-flash-lite"
    gemini_realtime_composer_fallback_model: str | None = "gemini-3.6-flash"
    gemini_realtime_composer_thinking_level: Literal[
        "minimal", "low", "medium", "high"
    ] = "minimal"

    # Legacy customer-agent / split-router rollback path. 3.7 stays out of the
    # realtime critical path while its availability is observed separately.
    gemini_agent_model: str = "gemini-3.6-flash"
    gemini_agent_fallback_model: str | None = "gemini-3.5-flash"
    gemini_agent_thinking_level: Literal["minimal", "low", "medium", "high"] = "low"

    gemini_router_model: str = "gemini-3.6-flash"
    gemini_router_fallback_model: str | None = "gemini-3.5-flash"
    gemini_router_thinking_level: Literal["minimal", "low", "medium", "high"] = "low"

    gemini_flow_model: str = "gemini-3.6-flash"
    gemini_flow_fallback_model: str | None = "gemini-3.5-flash"
    gemini_flow_thinking_level: Literal["minimal", "low", "medium", "high"] = "low"

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

    # Analytics uses its own small connection pool so expensive reporting reads
    # cannot consume every connection needed by booking/customer operations.
    analytics_db_pool_size: int = Field(default=2, ge=1, le=20)
    analytics_db_max_overflow: int = Field(default=0, ge=0, le=20)
    analytics_db_pool_timeout_seconds: int = Field(default=3, ge=1, le=30)
    analytics_statement_timeout_ms: int = Field(default=10_000, ge=1_000, le=60_000)

    # Aggregate-only micro-cache. Patient lists and CSV exports never use it.
    # A short TTL absorbs duplicate refreshes while keeping staleness bounded.
    analytics_aggregate_cache_ttl_seconds: int = Field(default=5, ge=0, le=60)
    analytics_aggregate_cache_max_entries: int = Field(default=256, ge=0, le=2048)
    analytics_export_max_rows: int = Field(default=5_000, ge=100, le=50_000)
    analytics_export_max_bytes: int = Field(default=5_000_000, ge=100_000, le=50_000_000)

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
            raise ValueError(
                "SUPABASE_URL must be the hosted https://<project-ref>.supabase.co URL."
            )
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
        "gemini_realtime_interpreter_fallback_model",
        "gemini_realtime_interpreter_emergency_model",
        "gemini_realtime_composer_fallback_model",
        "gemini_agent_fallback_model",
        "gemini_router_fallback_model",
        "gemini_flow_fallback_model",
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
