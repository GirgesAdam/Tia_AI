from __future__ import annotations

from typing import Literal
from uuid import UUID

from pydantic import BaseModel, Field, field_validator


class WhatsAppDirectConnect(BaseModel):
    app_id: str = Field(min_length=1, max_length=64)
    waba_id: str = Field(min_length=1, max_length=64)
    phone_number_id: str = Field(min_length=1, max_length=64)
    access_token: str = Field(min_length=16, max_length=8192)
    app_secret: str = Field(min_length=8, max_length=512)

    @field_validator("app_id", "waba_id", "phone_number_id")
    @classmethod
    def validate_meta_id(cls, value: str) -> str:
        clean = value.strip()
        if not clean.isdigit():
            raise ValueError("Meta identifiers must contain digits only.")
        return clean

    @field_validator("access_token", "app_secret")
    @classmethod
    def clean_secret(cls, value: str) -> str:
        clean = value.strip()
        if not clean:
            raise ValueError("Meta credential cannot be empty.")
        return clean


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
    direct_setup_available: bool = False
    provider_credentials_ready: bool = False
    transport_ready: bool = False
    templates_ready: bool = False
    ready_for_automations: bool = False
    meta_app_id: str | None = None
    webhook_callback_url: str | None = None
    webhook_verify_token: str | None = None
    webhook_verified: bool = False
    admin_action: Literal[
        "connect_meta_direct",
        "configure_webhook",
        "resolve_meta_restriction",
        "wait_for_template_review",
        "none",
    ] = "none"
    admin_message: str | None = None
    system_message: str | None = None


class WhatsAppDirectConnectResult(BaseModel):
    state: WhatsAppSetupState
