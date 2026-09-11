from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

from app.agents.v2.turn_contract import DateConstraint, PackageUsage, TimeConstraint

TaskStatus = Literal["collecting", "awaiting_choice", "ready", "executing"]
ChoicePurpose = Literal[
    "service",
    "doctor",
    "device",
    "appointment",
    "package",
    "booking_slot",
    "reschedule_slot",
]
WriteOperation = Literal["booking", "reschedule"]


class StrictStateModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


class WriteAuthorization(StrictStateModel):
    operation: WriteOperation
    authorized: bool = False
    source_turn_id: str | None = None
    granted_at: datetime | None = None

    @model_validator(mode="after")
    def validate_grant(self) -> "WriteAuthorization":
        if self.authorized and self.granted_at is None:
            raise ValueError("authorized write state requires granted_at.")
        return self


class CustomerConstraints(StrictStateModel):
    """Stable customer-selected constraints stored with canonical identifiers."""

    service_id: str | None = None
    doctor_id: str | None = None
    device_key: str | None = None
    date: DateConstraint | None = None
    time: TimeConstraint | None = None
    package_usage: PackageUsage = "unspecified"


class DerivedBookingState(StrictStateModel):
    """System-derived facts that must be invalidated when their dependencies change."""

    availability_snapshot_id: str | None = None
    selected_slot_ref: str | None = None
    selected_package_id: str | None = None
    package_validated: bool = False
    doctor_compatible: bool | None = None
    device_compatible: bool | None = None


class OptionChoice(StrictStateModel):
    ref: str
    label: str | None = None
    payload: dict[str, object] = Field(default_factory=dict)


class OptionSnapshot(StrictStateModel):
    snapshot_id: str
    purpose: ChoicePurpose
    task_version: int
    created_at: datetime
    expires_at: datetime
    options: list[OptionChoice] = Field(default_factory=list)

    @model_validator(mode="after")
    def validate_snapshot(self) -> "OptionSnapshot":
        if self.task_version < 1:
            raise ValueError("task_version must be positive.")
        if self.expires_at <= self.created_at:
            raise ValueError("option snapshot must expire after creation.")
        if not self.options:
            raise ValueError("option snapshot requires at least one option.")
        return self

    def is_current(self, *, task_version: int, now: datetime) -> bool:
        return self.task_version == task_version and now < self.expires_at


class BookingTaskState(StrictStateModel):
    task_type: Literal["booking"] = "booking"
    status: TaskStatus = "collecting"
    write_authorization: WriteAuthorization
    constraints: CustomerConstraints = Field(default_factory=CustomerConstraints)
    derived: DerivedBookingState = Field(default_factory=DerivedBookingState)
    option_snapshot: OptionSnapshot | None = None
    version: int = 1

    @model_validator(mode="after")
    def validate_version(self) -> "BookingTaskState":
        if self.version < 1:
            raise ValueError("task version must be positive.")
        if self.write_authorization.operation != "booking":
            raise ValueError("booking task requires booking write authorization type.")
        return self


class RescheduleTarget(StrictStateModel):
    appointment_id: str
    service_id: str | None = None
    doctor_id: str | None = None
    device_key: str | None = None
    start_local: str | None = None
    payment_context: dict[str, object] = Field(default_factory=dict)


class DerivedRescheduleState(StrictStateModel):
    availability_snapshot_id: str | None = None
    selected_slot_ref: str | None = None
    package_validated: bool = False
    doctor_compatible: bool | None = None
    device_compatible: bool | None = None


class RescheduleTaskState(StrictStateModel):
    task_type: Literal["reschedule"] = "reschedule"
    status: TaskStatus = "collecting"
    write_authorization: WriteAuthorization
    target: RescheduleTarget
    replacement: CustomerConstraints
    derived: DerivedRescheduleState = Field(default_factory=DerivedRescheduleState)
    option_snapshot: OptionSnapshot | None = None
    version: int = 1

    @model_validator(mode="after")
    def validate_version(self) -> "RescheduleTaskState":
        if self.version < 1:
            raise ValueError("task version must be positive.")
        if self.write_authorization.operation != "reschedule":
            raise ValueError("reschedule task requires reschedule write authorization type.")
        return self


ActiveTaskState = BookingTaskState | RescheduleTaskState
