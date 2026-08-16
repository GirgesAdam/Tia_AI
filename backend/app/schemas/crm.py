from __future__ import annotations

import re
from datetime import date, datetime
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

PatientStatus = Literal["active", "inactive", "blocked"]
PatientSource = Literal[
    "whatsapp",
    "instagram",
    "facebook",
    "website",
    "referral",
    "walk_in",
    "campaign",
    "phone",
    "email",
    "other",
]
PatientNoteType = Literal["general", "preference", "customer_service", "follow_up"]
LeadStatus = Literal["new", "contacted", "qualified", "booked", "won", "lost", "spam"]
ConversationChannel = Literal[
    "whatsapp",
    "instagram",
    "facebook",
    "web",
    "email",
    "sms",
    "phone",
    "other",
]
ConversationStatus = Literal["open", "pending", "closed"]
MessageSenderType = Literal["patient", "ai", "staff", "system"]
MessageDirection = Literal["inbound", "outbound", "internal"]
MessageDeliveryStatus = Literal["received", "queued", "sent", "delivered", "read", "failed"]


def normalize_email(value: str | None) -> str | None:
    if value is None:
        return None
    normalized = value.strip().lower()
    if not normalized:
        return None
    if len(normalized) > 320 or "@" not in normalized:
        raise ValueError("A valid email address is required.")
    return normalized


def normalize_phone(value: str | None) -> tuple[str | None, str | None]:
    if value is None:
        return None, None
    display = value.strip()
    if not display:
        return None, None
    if len(display) > 40:
        raise ValueError("Phone number is too long.")
    compact = re.sub(r"[\s().-]", "", display)
    if compact.startswith("+"):
        digits = compact[1:]
        normalized = f"+{digits}"
    else:
        digits = compact
        normalized = digits
    if not digits.isdigit() or not 7 <= len(digits) <= 15:
        raise ValueError("Phone must contain 7 to 15 digits, optionally starting with +.")
    return display, normalized


def normalize_required_text(value: str) -> str:
    normalized = value.strip()
    if not normalized:
        raise ValueError("Value cannot be empty.")
    return normalized


class PatientCreate(BaseModel):
    first_name: str = Field(max_length=120)
    last_name: str | None = Field(default=None, max_length=120)
    phone: str | None = Field(default=None, max_length=40)
    email: str | None = Field(default=None, max_length=320)
    gender: str | None = Field(default=None, max_length=32)
    birth_date: date | None = None
    preferred_language: str = Field(default="ar", min_length=2, max_length=10)
    preferred_branch_id: UUID | None = None
    source: PatientSource = "other"
    source_detail: str | None = Field(default=None, max_length=200)
    status: PatientStatus = "active"
    marketing_consent: bool = False

    @field_validator("first_name")
    @classmethod
    def validate_first_name(cls, value: str) -> str:
        return normalize_required_text(value)

    @field_validator("last_name", "gender", "source_detail", mode="before")
    @classmethod
    def strip_optional_text(cls, value: object) -> object:
        if isinstance(value, str):
            stripped = value.strip()
            return stripped or None
        return value

    @field_validator("email", mode="before")
    @classmethod
    def validate_email(cls, value: object) -> object:
        if value is None or isinstance(value, str):
            return normalize_email(value)
        return value

    @field_validator("phone", mode="before")
    @classmethod
    def validate_phone(cls, value: object) -> object:
        if value is None or isinstance(value, str):
            display, _ = normalize_phone(value)
            return display
        return value


class PatientUpdate(BaseModel):
    first_name: str | None = Field(default=None, max_length=120)
    last_name: str | None = Field(default=None, max_length=120)
    phone: str | None = Field(default=None, max_length=40)
    email: str | None = Field(default=None, max_length=320)
    gender: str | None = Field(default=None, max_length=32)
    birth_date: date | None = None
    preferred_language: str | None = Field(default=None, min_length=2, max_length=10)
    preferred_branch_id: UUID | None = None
    source: PatientSource | None = None
    source_detail: str | None = Field(default=None, max_length=200)
    status: PatientStatus | None = None
    marketing_consent: bool | None = None

    @field_validator("first_name")
    @classmethod
    def validate_first_name(cls, value: str | None) -> str | None:
        if value is None:
            return None
        return normalize_required_text(value)

    @field_validator("last_name", "gender", "source_detail", mode="before")
    @classmethod
    def strip_optional_text(cls, value: object) -> object:
        if isinstance(value, str):
            stripped = value.strip()
            return stripped or None
        return value

    @field_validator("email", mode="before")
    @classmethod
    def validate_email(cls, value: object) -> object:
        if value is None or isinstance(value, str):
            return normalize_email(value)
        return value

    @field_validator("phone", mode="before")
    @classmethod
    def validate_phone(cls, value: object) -> object:
        if value is None or isinstance(value, str):
            display, _ = normalize_phone(value)
            return display
        return value


class PatientRead(BaseModel):
    id: UUID
    workspace_id: UUID
    first_name: str
    last_name: str | None
    phone: str | None
    email: str | None
    gender: str | None
    birth_date: date | None
    preferred_language: str
    preferred_branch_id: UUID | None
    source: PatientSource
    source_detail: str | None
    status: PatientStatus
    marketing_consent: bool
    marketing_consent_at: datetime | None
    last_contact_at: datetime | None
    created_at: datetime
    updated_at: datetime

    model_config = ConfigDict(from_attributes=True)


class PatientTagCreate(BaseModel):
    name: str = Field(min_length=1, max_length=100)
    color: str | None = Field(default=None, max_length=20)

    @field_validator("name")
    @classmethod
    def validate_name(cls, value: str) -> str:
        return normalize_required_text(value)


class PatientTagRead(BaseModel):
    id: UUID
    workspace_id: UUID
    name: str
    color: str | None
    is_active: bool

    model_config = ConfigDict(from_attributes=True)


class PatientNoteCreate(BaseModel):
    note_type: PatientNoteType = "general"
    content: str = Field(min_length=1, max_length=10000)
    is_pinned: bool = False

    @field_validator("content")
    @classmethod
    def validate_content(cls, value: str) -> str:
        return normalize_required_text(value)


class PatientNoteRead(BaseModel):
    id: UUID
    workspace_id: UUID
    patient_id: UUID
    author_user_id: UUID | None
    note_type: PatientNoteType
    content: str
    is_pinned: bool
    created_at: datetime
    updated_at: datetime

    model_config = ConfigDict(from_attributes=True)


class LeadCreate(BaseModel):
    patient_id: UUID
    service_id: UUID | None = None
    assigned_user_id: UUID | None = None
    source: PatientSource | None = None
    status: LeadStatus = "new"
    estimated_value_minor: int | None = Field(default=None, ge=0)
    currency: str = Field(default="EGP", min_length=3, max_length=3)
    lost_reason: str | None = Field(default=None, max_length=2000)
    next_follow_up_at: datetime | None = None

    @field_validator("currency")
    @classmethod
    def normalize_currency(cls, value: str) -> str:
        return value.strip().upper()

    @model_validator(mode="after")
    def validate_lost_reason(self) -> "LeadCreate":
        if self.lost_reason and self.status != "lost":
            raise ValueError("lost_reason can only be set when status is lost.")
        return self


class LeadUpdate(BaseModel):
    service_id: UUID | None = None
    assigned_user_id: UUID | None = None
    source: PatientSource | None = None
    status: LeadStatus | None = None
    estimated_value_minor: int | None = Field(default=None, ge=0)
    currency: str | None = Field(default=None, min_length=3, max_length=3)
    lost_reason: str | None = Field(default=None, max_length=2000)
    next_follow_up_at: datetime | None = None
    last_contact_at: datetime | None = None

    @field_validator("currency")
    @classmethod
    def normalize_currency(cls, value: str | None) -> str | None:
        return value.strip().upper() if value else value


class LeadRead(BaseModel):
    id: UUID
    workspace_id: UUID
    patient_id: UUID
    service_id: UUID | None
    assigned_user_id: UUID | None
    source: str
    status: LeadStatus
    estimated_value_minor: int | None
    currency: str
    lost_reason: str | None
    next_follow_up_at: datetime | None
    last_contact_at: datetime | None
    created_at: datetime
    updated_at: datetime

    model_config = ConfigDict(from_attributes=True)


class ConversationCreate(BaseModel):
    patient_id: UUID
    channel: ConversationChannel
    status: ConversationStatus = "open"
    external_conversation_id: str | None = Field(default=None, max_length=255)
    assigned_user_id: UUID | None = None
    subject: str | None = Field(default=None, max_length=250)


class ConversationUpdate(BaseModel):
    status: ConversationStatus | None = None
    assigned_user_id: UUID | None = None
    subject: str | None = Field(default=None, max_length=250)


class ConversationRead(BaseModel):
    id: UUID
    workspace_id: UUID
    patient_id: UUID
    channel: ConversationChannel
    status: ConversationStatus
    external_conversation_id: str | None
    assigned_user_id: UUID | None
    subject: str | None
    started_at: datetime
    last_message_at: datetime | None
    closed_at: datetime | None
    created_at: datetime
    updated_at: datetime

    model_config = ConfigDict(from_attributes=True)


class MessageCreate(BaseModel):
    sender_type: MessageSenderType = "staff"
    direction: MessageDirection = "outbound"
    message_type: str = Field(default="text", min_length=1, max_length=32)
    content: str | None = Field(default=None, max_length=50000)
    external_message_id: str | None = Field(default=None, max_length=255)
    delivery_status: MessageDeliveryStatus | None = None
    metadata: dict = Field(default_factory=dict)

    @model_validator(mode="after")
    def validate_message(self) -> "MessageCreate":
        if self.message_type == "text" and not (self.content and self.content.strip()):
            raise ValueError("Text messages require non-empty content.")
        if self.sender_type == "patient" and self.direction != "inbound":
            raise ValueError("Patient messages must be inbound.")
        if self.sender_type in {"staff", "ai"} and self.direction == "inbound":
            raise ValueError("Staff and AI messages cannot be inbound.")
        return self


class MessageRead(BaseModel):
    id: UUID
    workspace_id: UUID
    conversation_id: UUID
    sender_type: MessageSenderType
    direction: MessageDirection
    message_type: str
    content: str | None
    external_message_id: str | None
    delivery_status: MessageDeliveryStatus
    sent_by_user_id: UUID | None
    metadata: dict = Field(validation_alias="metadata_json")
    created_at: datetime
    updated_at: datetime

    model_config = ConfigDict(from_attributes=True, populate_by_name=True)
