from __future__ import annotations

from datetime import date, datetime
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, field_validator

AppointmentStatus = Literal[
    "pending",
    "confirmed",
    "checked_in",
    "in_progress",
    "completed",
    "cancelled",
    "no_show",
    "rescheduled",
]
AppointmentSource = Literal[
    "ai",
    "staff",
    "whatsapp",
    "instagram",
    "website",
    "phone",
    "walk_in",
    "facebook",
    "email",
    "other",
]
OperationalAppointmentStatus = Literal["checked_in", "in_progress", "completed", "no_show"]


def require_timezone_aware(value: datetime) -> datetime:
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError("Datetime must include a timezone offset.")
    return value


class AvailabilitySlot(BaseModel):
    branch_id: UUID
    doctor_id: UUID
    service_id: UUID
    start_at: datetime
    end_at: datetime
    price_minor: int
    currency: str


class AvailabilityResponse(BaseModel):
    date: date
    timezone: str
    slots: list[AvailabilitySlot]


class AppointmentCreate(BaseModel):
    patient_id: UUID
    branch_id: UUID
    doctor_id: UUID
    service_id: UUID
    lead_id: UUID | None = None
    start_at: datetime
    source: AppointmentSource = "staff"
    customer_note: str | None = Field(default=None, max_length=5000)

    @field_validator("start_at")
    @classmethod
    def validate_start_at(cls, value: datetime) -> datetime:
        return require_timezone_aware(value)

    @field_validator("customer_note", mode="before")
    @classmethod
    def normalize_note(cls, value: object) -> object:
        if isinstance(value, str):
            value = value.strip()
            return value or None
        return value


class AppointmentCancel(BaseModel):
    reason: str = Field(min_length=1, max_length=2000)
    override_policy: bool = False

    @field_validator("reason")
    @classmethod
    def normalize_reason(cls, value: str) -> str:
        value = value.strip()
        if not value:
            raise ValueError("Cancellation reason cannot be empty.")
        return value


class AppointmentReschedule(BaseModel):
    start_at: datetime
    branch_id: UUID | None = None
    doctor_id: UUID | None = None
    reason: str | None = Field(default=None, max_length=2000)

    @field_validator("start_at")
    @classmethod
    def validate_start_at(cls, value: datetime) -> datetime:
        return require_timezone_aware(value)

    @field_validator("reason", mode="before")
    @classmethod
    def normalize_reason(cls, value: object) -> object:
        if isinstance(value, str):
            value = value.strip()
            return value or None
        return value


class AppointmentOperationalStatusUpdate(BaseModel):
    status: OperationalAppointmentStatus
    reason: str | None = Field(default=None, max_length=2000)


class AppointmentRead(BaseModel):
    id: UUID
    workspace_id: UUID
    patient_id: UUID
    branch_id: UUID
    doctor_id: UUID
    service_id: UUID
    lead_id: UUID | None
    created_by_user_id: UUID | None
    rescheduled_from_appointment_id: UUID | None
    status: AppointmentStatus
    source: AppointmentSource
    start_at: datetime
    end_at: datetime
    busy_start_at: datetime
    busy_end_at: datetime
    duration_minutes: int
    price_minor: int
    currency: str
    customer_note: str | None
    cancellation_reason: str | None
    confirmed_at: datetime | None
    cancelled_at: datetime | None
    completed_at: datetime | None
    no_show_at: datetime | None
    created_at: datetime
    updated_at: datetime

    model_config = ConfigDict(from_attributes=True)


class AppointmentStatusHistoryRead(BaseModel):
    id: UUID
    workspace_id: UUID
    appointment_id: UUID
    changed_by_user_id: UUID | None
    from_status: AppointmentStatus | None
    to_status: AppointmentStatus
    reason: str | None
    metadata: dict = Field(validation_alias="metadata_json")
    created_at: datetime

    model_config = ConfigDict(from_attributes=True, populate_by_name=True)
