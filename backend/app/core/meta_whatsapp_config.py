from __future__ import annotations

from functools import lru_cache

from pydantic import field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class MetaWhatsAppSettings(BaseSettings):
    meta_app_id: str | None = None
    meta_app_secret: str | None = None
    meta_whatsapp_embedded_signup_config_id: str | None = None
    meta_graph_api_version: str | None = None
    meta_webhook_verify_token: str | None = None
    channel_credential_encryption_key: str | None = None
    channel_transport_worker_token: str | None = None

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    @field_validator(
        "meta_app_id",
        "meta_app_secret",
        "meta_whatsapp_embedded_signup_config_id",
        "meta_graph_api_version",
        "meta_webhook_verify_token",
        "channel_credential_encryption_key",
        "channel_transport_worker_token",
        mode="before",
    )
    @classmethod
    def normalize_optional_text(cls, value: object) -> object:
        if isinstance(value, str):
            value = value.strip()
            return value or None
        return value


@lru_cache
def get_meta_whatsapp_settings() -> MetaWhatsAppSettings:
    return MetaWhatsAppSettings()


meta_whatsapp_settings = get_meta_whatsapp_settings()
