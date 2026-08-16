from __future__ import annotations

from datetime import datetime
from typing import Any, Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

ChannelType = Literal[
    "whatsapp",
    "instagram",
    "facebook",
    "web",
    "email",
    "sms",
    "other",
]
ChannelConnectionStatus = Literal["active", "paused", "disconnected"]
InboundEventStatus = Literal["received", "processing", "processed", "failed"]
DispatchStatus = Literal["queued", "processing", "sent", "delivered", "read", "failed", "cancelled"]
DispatchResultStatus = Literal["sent", "delivered", "read", "failed"]
ProviderDeliveryStatus = Literal["sent", "delivered", "read", "failed"]

_SENSITIVE_CONFIG_MARKERS = (
    "token",
    "secret",
    "password",
    "passwd",
    "api_key",
    "apikey",
    "access_key",
    "private_key",
)


def _clean_required(value: str) -> str:
    value = value.strip()
    if not value:
        raise ValueError("Value cannot be empty.")
    return value


def _validate_non_secret_config(config: dict[str, Any]) -> dict[str, Any]:
    def walk(value: Any) -> None:
        if isinstance(value, dict):
            for key, nested in value.items():
                normalized = str(key).strip().lower()
                if any(marker in normalized for marker in _SENSITIVE_CONFIG_MARKERS):
                    raise ValueError(
                        "Channel config cannot contain credentials or secrets. "
                        "Keep provider credentials in a secret manager/environment configuration."
                    )
                walk(nested)
        elif isinstance(value, list):
            for item in value:
                walk(item)

    walk(config)
    return config


class ChannelConnectionCreate(BaseModel):
    channel: ChannelType
    provider: str = Field(min_length=1, max_length=40)
    display_name: str = Field(min_length=1, max_length=120)
    external_account_id: str | None = Field(default=None, max_length=255)
    status: ChannelConnectionStatus = "active"
    config: dict[str, Any] = Field(default_factory=dict)

    @field_validator("provider", "display_name")
    @classmethod
    def normalize_required_text(cls, value: str) -> str:
        return _clean_required(value)

    @field_validator("external_account_id")
    @classmethod
    def normalize_optional_text(cls, value: str | None) -> str | None:
        if value is None:
            return None
        value = value.strip()
        return value or None

    @field_validator("config")
    @classmethod
    def reject_secrets_in_config(cls, value: dict[str, Any]) -> dict[str, Any]:
        return _validate_non_secret_config(value)


class ChannelConnectionUpdate(BaseModel):
    display_name: str | None = Field(default=None, min_length=1, max_length=120)
    external_account_id: str | None = Field(default=None, max_length=255)
    status: ChannelConnectionStatus | None = None
    config: dict[str, Any] | None = None

    @field_validator("display_name")
    @classmethod
    def normalize_display_name(cls, value: str | None) -> str | None:
        if value is None:
            return None
        return _clean_required(value)

    @field_validator("external_account_id")
    @classmethod
    def normalize_external_account_id(cls, value: str | None) -> str | None:
        if value is None:
            return None
        value = value.strip()
        return value or None

    @field_validator("config")
    @classmethod
    def reject_secrets_in_config(cls, value: dict[str, Any] | None) -> dict[str, Any] | None:
        if value is None:
            return None
        return _validate_non_secret_config(value)


class ChannelConnectionRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    workspace_id: UUID
    channel: ChannelType
    provider: str
    display_name: str
    status: ChannelConnectionStatus
    external_account_id: str | None
    created_by_user_id: UUID | None
    config_json: dict[str, Any]
    created_at: datetime
    updated_at: datetime


class ChannelConnectionCreated(ChannelConnectionRead):
    adapter_token: str
    token_note: str = "Store this token securely. It is only returned on create/rotate."


class ChannelTokenRotated(BaseModel):
    connection_id: UUID
    adapter_token: str
    token_note: str = "The previous adapter token is now invalid. Store this token securely."


class NormalizedInboundMessage(BaseModel):
    external_event_id: str = Field(min_length=1, max_length=255)
    external_message_id: str = Field(min_length=1, max_length=255)
    external_user_id: str = Field(min_length=1, max_length=255)
    external_conversation_id: str | None = Field(default=None, max_length=255)
    display_name: str | None = Field(default=None, max_length=200)
    phone: str | None = Field(default=None, max_length=40)
    email: str | None = Field(default=None, max_length=320)
    message_type: Literal["text"] = "text"
    text: str = Field(min_length=1, max_length=10000)
    metadata: dict[str, Any] = Field(default_factory=dict)

    @field_validator(
        "external_event_id",
        "external_message_id",
        "external_user_id",
        "text",
    )
    @classmethod
    def normalize_required(cls, value: str) -> str:
        return _clean_required(value)

    @field_validator(
        "external_conversation_id",
        "display_name",
        "phone",
        "email",
    )
    @classmethod
    def normalize_optional(cls, value: str | None) -> str | None:
        if value is None:
            return None
        value = value.strip()
        return value or None


class InboundAcceptedResponse(BaseModel):
    event_id: UUID
    message_id: UUID
    patient_id: UUID
    conversation_id: UUID
    duplicate: bool
    processing_required: bool = True
    status: InboundEventStatus


class InboundProcessResponse(BaseModel):
    event_id: UUID
    status: InboundEventStatus
    conversation_id: UUID
    inbound_message_id: UUID
    outbound_message_id: UUID | None
    dispatch_id: UUID | None
    handoff_required: bool
    agent_paused: bool
    reply: str | None
    model: str | None


class DispatchClaimRequest(BaseModel):
    limit: int = Field(default=10, ge=1, le=50)


class DispatchClaimItem(BaseModel):
    dispatch_id: UUID
    message_id: UUID
    channel: ChannelType
    provider: str
    external_account_id: str | None
    external_user_id: str
    external_conversation_id: str
    message_type: str
    content: str | None
    metadata: dict[str, Any]
    attempt: int


class DispatchResultRequest(BaseModel):
    status: DispatchResultStatus
    provider_message_id: str | None = Field(default=None, max_length=255)
    error: str | None = Field(default=None, max_length=2000)
    retry_after_seconds: int | None = Field(default=None, ge=1, le=86400)
    metadata: dict[str, Any] = Field(default_factory=dict)

    @model_validator(mode="after")
    def validate_failed_result(self) -> "DispatchResultRequest":
        if self.status != "failed" and self.retry_after_seconds is not None:
            raise ValueError("retry_after_seconds can only be used when status is failed.")
        return self


class MessageDispatchRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    workspace_id: UUID
    channel_connection_id: UUID
    message_id: UUID
    status: DispatchStatus
    attempts: int
    provider_message_id: str | None
    last_error: str | None
    next_attempt_at: datetime | None
    locked_at: datetime | None
    sent_at: datetime | None
    delivered_at: datetime | None
    read_at: datetime | None
    metadata_json: dict[str, Any]
    created_at: datetime
    updated_at: datetime


class ProviderStatusRequest(BaseModel):
    external_event_id: str = Field(min_length=1, max_length=512)
    provider_message_id: str = Field(min_length=1, max_length=255)
    status: ProviderDeliveryStatus
    occurred_at: datetime | None = None
    error: str | None = Field(default=None, max_length=2000)
    metadata: dict[str, Any] = Field(default_factory=dict)

    @field_validator("external_event_id", "provider_message_id")
    @classmethod
    def normalize_provider_ids(cls, value: str) -> str:
        return _clean_required(value)

    @field_validator("error")
    @classmethod
    def normalize_optional_error(cls, value: str | None) -> str | None:
        if value is None:
            return None
        value = value.strip()
        return value or None


class ProviderStatusResponse(BaseModel):
    event_id: UUID
    duplicate: bool
    matched_dispatch: bool
    dispatch_id: UUID | None
    dispatch_status: DispatchStatus | None
