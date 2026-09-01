from __future__ import annotations

from uuid import UUID

from pydantic import BaseModel, Field, field_validator

from app.schemas.clinic import (
    BookingSettingsRead,
    BranchRead,
    BranchWorkingHourRead,
    DoctorBranchRead,
    DoctorRead,
    DoctorServiceRead,
    DoctorWorkingHourRead,
    ServiceRead,
    StaffRead,
)


class WorkspaceCreate(BaseModel):
    name: str = Field(min_length=2, max_length=200)
    slug: str = Field(min_length=2, max_length=120, pattern=r"^[a-z0-9]+(?:-[a-z0-9]+)*$")
    timezone: str = Field(default="Africa/Cairo", min_length=1, max_length=64)

    @field_validator("name", "slug", "timezone")
    @classmethod
    def clean_text(cls, value: str) -> str:
        return value.strip()


class WorkspaceCreated(BaseModel):
    workspace_id: UUID
    workspace_name: str
    workspace_slug: str
    role: str


class DoctorSetupRead(DoctorRead):
    staff_name: str


class SetupReadiness(BaseModel):
    ready: bool
    progress_percent: int
    completed_steps: int
    total_steps: int
    checks: dict[str, bool]
    missing: list[str]


class ClinicSetupSnapshot(BaseModel):
    workspace_id: UUID
    workspace_name: str
    workspace_slug: str
    workspace_timezone: str
    branches: list[BranchRead]
    services: list[ServiceRead]
    staff: list[StaffRead]
    doctors: list[DoctorSetupRead]
    doctor_branches: list[DoctorBranchRead]
    doctor_services: list[DoctorServiceRead]
    branch_working_hours: list[BranchWorkingHourRead]
    doctor_working_hours: list[DoctorWorkingHourRead]
    booking_settings: BookingSettingsRead | None
    readiness: SetupReadiness
