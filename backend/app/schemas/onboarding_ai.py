from __future__ import annotations

from datetime import datetime, time
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, model_validator

OnboardingCapability = Literal[
    "branch_configuration",
    "service_configuration",
    "doctor_configuration",
    "schedule_configuration",
    "booking_settings_configuration",
]


class OnboardingWorkingHour(BaseModel):
    model_config = ConfigDict(extra="forbid")

    weekday: int = Field(ge=0, le=6)
    start_time: time
    end_time: time

    @model_validator(mode="after")
    def validate_range(self):
        if self.end_time <= self.start_time:
            raise ValueError("Working-hour end_time must be after start_time.")
        return self


def _reject_overlaps(intervals: list[OnboardingWorkingHour]) -> None:
    by_weekday: dict[int, list[OnboardingWorkingHour]] = {}
    for interval in intervals:
        by_weekday.setdefault(interval.weekday, []).append(interval)
    for rows in by_weekday.values():
        ordered = sorted(rows, key=lambda row: row.start_time)
        for previous, current in zip(ordered, ordered[1:], strict=False):
            if current.start_time < previous.end_time:
                raise ValueError("Working-hour intervals cannot overlap on the same weekday.")


class OnboardingBranchPlan(BaseModel):
    model_config = ConfigDict(extra="forbid")

    key: str = Field(min_length=1, max_length=80)
    name: str = Field(min_length=1, max_length=200)
    code: str = Field(
        min_length=1,
        max_length=50,
        pattern=r"^[a-z0-9]+(?:-[a-z0-9]+)*$",
    )
    city: str | None = Field(default=None, max_length=120)
    phone: str | None = Field(default=None, max_length=40)
    email: str | None = Field(default=None, max_length=320)
    address_line1: str | None = Field(default=None, max_length=300)
    country_code: str = Field(default="EG", min_length=2, max_length=2)
    timezone: str = Field(default="Africa/Cairo", max_length=64)
    apply_working_hours: bool = False
    working_hours: list[OnboardingWorkingHour] = Field(
        default_factory=list,
        max_length=100,
    )

    @model_validator(mode="after")
    def validate_working_hours(self):
        if self.apply_working_hours and not self.working_hours:
            raise ValueError(
                "Branch working hours cannot be empty when apply_working_hours is true."
            )
        _reject_overlaps(self.working_hours)
        return self


class OnboardingServicePlan(BaseModel):
    model_config = ConfigDict(extra="forbid")

    key: str = Field(min_length=1, max_length=80)
    name: str = Field(min_length=1, max_length=200)
    slug: str = Field(
        min_length=1,
        max_length=160,
        pattern=r"^[a-z0-9]+(?:-[a-z0-9]+)*$",
    )
    category: str | None = Field(default=None, max_length=120)
    description: str | None = Field(default=None, max_length=2000)
    duration_minutes: int = Field(gt=0, le=1440)
    buffer_before_minutes: int = Field(default=0, ge=0, le=1440)
    buffer_after_minutes: int = Field(default=0, ge=0, le=1440)
    price_minor: int = Field(default=0, ge=0)
    currency: str = Field(default="EGP", min_length=3, max_length=3)
    requires_medical_review: bool = False


class OnboardingDoctorWorkingHours(BaseModel):
    model_config = ConfigDict(extra="forbid")

    branch_key: str = Field(min_length=1, max_length=80)
    intervals: list[OnboardingWorkingHour] = Field(
        default_factory=list,
        max_length=100,
    )

    @model_validator(mode="after")
    def validate_intervals(self):
        if not self.intervals:
            raise ValueError("Doctor working-hour intervals cannot be empty.")
        _reject_overlaps(self.intervals)
        return self


class OnboardingDoctorPlan(BaseModel):
    model_config = ConfigDict(extra="forbid")

    key: str = Field(min_length=1, max_length=80)
    first_name: str = Field(min_length=1, max_length=120)
    last_name: str = Field(min_length=1, max_length=120)
    specialization: str | None = Field(default=None, max_length=200)
    license_number: str | None = Field(default=None, max_length=120)
    phone: str | None = Field(default=None, max_length=40)
    email: str | None = Field(default=None, max_length=320)
    branch_keys: list[str] = Field(default_factory=list, max_length=50)
    primary_branch_key: str | None = Field(default=None, max_length=80)
    service_keys: list[str] = Field(default_factory=list, max_length=100)
    apply_working_hours: bool = False
    working_hours: list[OnboardingDoctorWorkingHours] = Field(
        default_factory=list,
        max_length=50,
    )

    @model_validator(mode="after")
    def validate_working_hours_application(self):
        if self.apply_working_hours and not self.working_hours:
            raise ValueError(
                "Doctor working hours cannot be empty when apply_working_hours is true."
            )
        return self


class OnboardingBookingSettingsPlan(BaseModel):
    model_config = ConfigDict(extra="forbid")

    apply: bool = False
    slot_interval_minutes: int = Field(default=15, gt=0, le=240)
    minimum_notice_minutes: int = Field(default=60, ge=0)
    booking_horizon_days: int = Field(default=90, gt=0, le=730)
    cancellation_notice_minutes: int = Field(default=720, ge=0)
    allow_same_day_booking: bool = True
    require_confirmation: bool = True
    default_currency: str = Field(default="EGP", min_length=3, max_length=3)


class OnboardingPlan(BaseModel):
    model_config = ConfigDict(extra="forbid")

    branches: list[OnboardingBranchPlan] = Field(default_factory=list, max_length=50)
    services: list[OnboardingServicePlan] = Field(default_factory=list, max_length=200)
    doctors: list[OnboardingDoctorPlan] = Field(default_factory=list, max_length=100)
    booking_settings: OnboardingBookingSettingsPlan = Field(
        default_factory=OnboardingBookingSettingsPlan
    )


class OnboardingTurnDecision(BaseModel):
    model_config = ConfigDict(extra="forbid")

    action: Literal["propose", "revise", "confirm", "cancel", "clarify"]
    capabilities: list[OnboardingCapability]
    plan: OnboardingPlan
    missing_information: list[str]
    assistant_message: str = Field(min_length=1, max_length=2500)
    confidence: float = Field(ge=0.0, le=1.0)


class OnboardingAIChatRequest(BaseModel):
    message: str = Field(min_length=1, max_length=6000)
    session_id: UUID | None = None
    expected_version: int | None = Field(default=None, ge=1)


class OnboardingAICommandRequest(BaseModel):
    expected_version: int = Field(ge=1)


class OnboardingAIResponse(BaseModel):
    session_id: UUID
    status: str
    version: int
    assistant_message: str
    capabilities: list[OnboardingCapability]
    missing_information: list[str]
    plan: OnboardingPlan | None
    plan_summary: dict
    execution_result: dict
    requires_confirmation: bool
    readiness_refresh_required: bool


class OnboardingAISessionRead(BaseModel):
    session_id: UUID
    status: str
    version: int
    plan: OnboardingPlan | None
    plan_summary: dict
    missing_information: list[str]
    execution_result: dict
    expires_at: datetime
