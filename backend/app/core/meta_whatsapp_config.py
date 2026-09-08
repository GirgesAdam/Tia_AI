from __future__ import annotations

from functools import lru_cache

from pydantic import field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class MetaWhatsAppSettings(BaseSettings):
    meta_graph_api_version: str | None = None
    channel_credential_encryption_key: str | None = None
    channel_transport_worker_token: str | None = None

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    @field_validator(
        "meta_graph_api_version",
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
