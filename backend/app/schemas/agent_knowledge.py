from __future__ import annotations

from datetime import datetime, time
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, model_validator

from app.schemas.clinic import BookingSettingsRead


class KnowledgeHour(BaseModel):
    weekday: int = Field(ge=0, le=6)
    start_time: time
    end_time: time


class KnowledgeBranch(BaseModel):
    id: UUID
    name: str
    code: str
    city: str | None = None
    address_line1: str | None = None
    phone: str | None = None
    timezone: str | None = None
    is_active: bool
    working_hours: list[KnowledgeHour] = Field(default_factory=list)


class KnowledgeService(BaseModel):
    id: UUID
    name: str
    slug: str
    category: str | None = None
    description: str | None = None
    duration_minutes: int
    price_minor: int
    currency: str
    requires_medical_review: bool
    is_active: bool


class KnowledgeNamedLink(BaseModel):
    id: UUID
    name: str
    is_primary: bool = False


class KnowledgeDoctorSchedule(BaseModel):
    branch_id: UUID
    branch_name: str
    working_hours: list[KnowledgeHour] = Field(default_factory=list)


class KnowledgeDoctor(BaseModel):
    id: UUID
    staff_id: UUID
    name: str
    first_name: str
    last_name: str
    specialization: str | None = None
    phone: str | None = None
    email: str | None = None
    booking_enabled: bool
    is_active: bool
    branches: list[KnowledgeNamedLink] = Field(default_factory=list)
    services: list[KnowledgeNamedLink] = Field(default_factory=list)
    schedules: list[KnowledgeDoctorSchedule] = Field(default_factory=list)


class KnowledgePatient(BaseModel):
    id: UUID
    name: str
    phone: str | None = None
    status: str
    source: str


class KnowledgeAppointment(BaseModel):
    id: UUID
    patient_name: str
    patient_phone: str | None = None
    service_name: str
    branch_name: str
    doctor_name: str
    start_at: datetime
    end_at: datetime
    status: str
    payment_status: str
    amount_paid_minor: int | None = None
    payment_method: str
    price_minor: int
    currency: str


class AgentKnowledgeSnapshot(BaseModel):
    workspace_id: UUID
    workspace_name: str
    workspace_timezone: str
    branches: list[KnowledgeBranch]
    services: list[KnowledgeService]
    doctors: list[KnowledgeDoctor]
    booking_settings: BookingSettingsRead | None = None
    patients: list[KnowledgePatient]
    appointments: list[KnowledgeAppointment]
    patient_count: int
    appointment_count: int


KnowledgeEditKind = Literal[
    "update_service",
    "update_branch",
    "update_doctor",
    "set_branch_hours",
    "set_doctor_hours",
    "set_doctor_services",
    "set_doctor_branches",
    "update_booking_settings",
]

KnowledgeEditField = Literal[
    "name",
    "category",
    "description",
    "duration_minutes",
    "price_egp",
    "requires_medical_review",
    "is_active",
    "city",
    "address_line1",
    "phone",
    "timezone",
    "first_name",
    "last_name",
    "email",
    "specialization",
    "booking_enabled",
    "slot_interval_minutes",
    "minimum_notice_minutes",
    "booking_horizon_days",
    "cancellation_notice_minutes",
    "allow_same_day_booking",
    "require_confirmation",
]


class KnowledgeFieldChange(BaseModel):
    model_config = ConfigDict(extra="forbid")

    field: KnowledgeEditField
    text_value: str | None = Field(default=None, max_length=2000)
    number_value: float | None = None
    bool_value: bool | None = None

    @model_validator(mode="after")
    def exactly_one_value(self):
        values = [self.text_value is not None, self.number_value is not None, self.bool_value is not None]
        if sum(values) != 1:
            raise ValueError("Exactly one change value must be supplied.")
        return self


class KnowledgeScheduleInterval(BaseModel):
    model_config = ConfigDict(extra="forbid")

    weekday: int = Field(ge=0, le=6)
    start_time: str
    end_time: str

    @model_validator(mode="after")
    def valid_interval(self):
        try:
            start = time.fromisoformat(self.start_time)
            end = time.fromisoformat(self.end_time)
        except ValueError as exc:
            raise ValueError("Schedule times must use HH:MM or HH:MM:SS.") from exc
        if end <= start:
            raise ValueError("end_time must be after start_time")
        return self


class KnowledgeEditAction(BaseModel):
    model_config = ConfigDict(extra="forbid")

    kind: KnowledgeEditKind
    entity_id: str | None = Field(default=None, max_length=80)
    branch_id: str | None = Field(default=None, max_length=80)
    related_ids: list[str] = Field(default_factory=list, max_length=100)
    primary_branch_id: str | None = Field(default=None, max_length=80)
    changes: list[KnowledgeFieldChange] = Field(default_factory=list, max_length=30)
    schedule: list[KnowledgeScheduleInterval] = Field(default_factory=list, max_length=100)


class KnowledgeEditDecision(BaseModel):
    model_config = ConfigDict(extra="forbid")

    understood: bool
    needs_clarification: bool
    clarification_question: str | None = Field(default=None, max_length=800)
    assistant_message: str = Field(min_length=1, max_length=1500)
    actions: list[KnowledgeEditAction] = Field(default_factory=list, max_length=12)


class KnowledgeEditProposeRequest(BaseModel):
    message: str = Field(min_length=1, max_length=5000)


class KnowledgeEditProposal(BaseModel):
    base_fingerprint: str
    assistant_message: str
    preview_lines: list[str]
    actions: list[KnowledgeEditAction]
    requires_confirmation: bool
    clarification_question: str | None = None


class KnowledgeEditApplyRequest(BaseModel):
    base_fingerprint: str = Field(min_length=20, max_length=128)
    actions: list[KnowledgeEditAction] = Field(min_length=1, max_length=12)


class KnowledgeEditApplyResponse(BaseModel):
    assistant_message: str
    applied_actions: int
    knowledge_refresh_required: bool = True
