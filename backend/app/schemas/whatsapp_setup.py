from __future__ import annotations

from typing import Literal
from uuid import UUID

from pydantic import BaseModel, Field, field_validator


class WhatsAppEmbeddedSignupConfig(BaseModel):
    available: bool
    app_id: str | None = None
    config_id: str | None = None
    graph_api_version: str | None = None


class WhatsAppEmbeddedSignupComplete(BaseModel):
    code: str = Field(min_length=8, max_length=4096)
    waba_id: str = Field(min_length=1, max_length=64)
    phone_number_id: str = Field(min_length=1, max_length=64)
    business_id: str | None = Field(default=None, max_length=64)

    @field_validator("code", "waba_id", "phone_number_id", "business_id")
    @classmethod
    def clean_text(cls, value: str | None) -> str | None:
        if value is None:
            return None
        value = value.strip()
        return value or None

    @field_validator("waba_id", "phone_number_id", "business_id")
    @classmethod
    def validate_meta_id(cls, value: str | None) -> str | None:
        if value is None:
            return None
        if not value.isdigit():
            raise ValueError("Meta identifiers must contain digits only.")
        return value


class WhatsAppSetupState(BaseModel):
    connection_id: UUID | None = None
    connection_status: Literal["active", "paused", "disconnected"] | None = None
    connected: bool = False
    display_name: str | None = None
    display_phone_number: str | None = None
    verified_name: str | None = None
    provider_health_state: str | None = None
    provider_error_code: str | None = None
    provider_error: str | None = None
    embedded_signup_available: bool = False
    provider_credentials_ready: bool = False
    transport_ready: bool = False
    templates_ready: bool = False
    ready_for_automations: bool = False
    admin_action: Literal[
        "connect_meta",
        "resolve_meta_restriction",
        "wait_for_template_review",
        "none",
    ] = "none"
    admin_message: str | None = None
    system_message: str | None = None


class WhatsAppEmbeddedSignupResult(BaseModel):
    state: WhatsAppSetupState
