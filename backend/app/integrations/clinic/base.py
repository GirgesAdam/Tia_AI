from __future__ import annotations

from abc import ABC, abstractmethod
from collections.abc import Hashable
from dataclasses import dataclass
from datetime import date, datetime
from enum import Enum
from typing import Any


class ClinicCapability(str, Enum):
    """Canonical abilities a clinic source can expose to Tia.

    These capabilities describe what the connected clinic system can support,
    independently of how that system stores its data. A spreadsheet import may
    support catalog reads but not live availability; Tia's native database can
    support the complete booking lifecycle.
    """

    CATALOG_READ = "catalog.read"
    AVAILABILITY_READ = "availability.read"
    APPOINTMENTS_READ = "appointments.read"
    APPOINTMENTS_CREATE = "appointments.create"
    APPOINTMENTS_CONFIRM = "appointments.confirm"
    APPOINTMENTS_CANCEL = "appointments.cancel"
    APPOINTMENTS_RESCHEDULE = "appointments.reschedule"
    PATIENTS_READ = "patients.read"
    PAYMENTS_READ = "payments.read"


class ClinicCapabilityNotSupported(ValueError):
    """Raised when a clinic integration cannot safely perform an operation."""


class ClinicActionRequiresHuman(ValueError):
    """Raised when clinic policy requires staff approval before a write can continue."""

    def __init__(self, message: str, *, appointment_id: str | None = None) -> None:
        super().__init__(message)
        self.appointment_id = appointment_id


@dataclass(frozen=True)
class ClinicCapabilities:
    supported: frozenset[ClinicCapability]

    def supports(self, capability: ClinicCapability) -> bool:
        return capability in self.supported

    def require(self, capability: ClinicCapability) -> None:
        if not self.supports(capability):
            raise ClinicCapabilityNotSupported(
                f"Clinic integration does not support {capability.value}."
            )

    def as_dict(self) -> dict[str, bool]:
        return {capability.value: self.supports(capability) for capability in ClinicCapability}


@dataclass(frozen=True)
class AvailabilityRequest:
    """Canonical availability query passed across the clinic integration boundary.

    IDs are strings on purpose. Tia's native adapter converts UUID strings to its
    database keys, while future systems can use values such as ``DR-17`` or an
    imported spreadsheet key without changing the agent contract.
    """

    branch_id: str
    service_id: str
    booking_date: date
    doctor_id: str | None = None
    exclude_appointment_id: str | None = None
    now: datetime | None = None


@dataclass(frozen=True)
class AvailabilitySlot:
    branch_id: str
    branch_name: str | None
    doctor_id: str
    doctor_name: str | None
    service_id: str
    service_name: str | None
    start_at: datetime
    end_at: datetime
    duration_minutes: int
    price_minor: int
    currency: str


@dataclass(frozen=True)
class AvailabilityResult:
    timezone: str
    branch_id: str
    branch_name: str | None
    service_id: str
    service_name: str | None
    service_duration_minutes: int | None
    service_price_minor: int | None
    service_currency: str | None
    slots: tuple[AvailabilitySlot, ...]


@dataclass(frozen=True)
class PatientReadRequest:
    """Canonical request for one clinic patient by Tia canonical id."""

    patient_id: str


@dataclass(frozen=True)
class PatientRecord:
    patient_id: str
    first_name: str
    last_name: str | None = None
    phone: str | None = None
    gender: str | None = None
    birth_date: date | None = None
    status: str = "active"
    preferred_language: str = "ar"
    source: str = "other"
    source_created_at: datetime | None = None
    updated_at: datetime | None = None


@dataclass(frozen=True)
class PaymentReadRequest:
    """Canonical payment-ledger query scoped to a patient and optional appointment."""

    patient_id: str
    appointment_id: str | None = None
    limit: int = 100


@dataclass(frozen=True)
class PaymentAllocationRecord:
    appointment_id: str
    amount_minor: int


@dataclass(frozen=True)
class PaymentRecord:
    transaction_id: str
    patient_id: str
    appointment_id: str | None
    transaction_type: str
    amount_minor: int
    currency: str
    payment_method: str
    source: str
    created_at: datetime
    external_reference: str | None = None
    reference_transaction_id: str | None = None
    allocations: tuple[PaymentAllocationRecord, ...] = ()


@dataclass(frozen=True)
class PaymentReadResult:
    transactions: tuple[PaymentRecord, ...]


@dataclass(frozen=True)
class AppointmentReadRequest:
    """Canonical query for one patient's appointments.

    ``patient_id`` is source-agnostic for the same reason as the availability
    identifiers: native Tia uses UUID strings while an external clinic can use
    its own stable patient key.
    """

    patient_id: str
    include_past: bool = False
    limit: int = 30
    now: datetime | None = None


@dataclass(frozen=True)
class AppointmentRecord:
    appointment_id: str
    patient_id: str
    status: str
    service_id: str
    service_name: str | None
    branch_id: str
    branch_name: str | None
    doctor_id: str
    doctor_name: str | None
    start_at: datetime
    end_at: datetime
    timezone: str
    price_minor: int
    currency: str
    payment_status: str = "unknown"
    amount_paid_minor: int | None = None
    payment_method: str = "unknown"
    billing_context: str = "standard"
    package_external_id: str | None = None
    patient_package_id: str | None = None


@dataclass(frozen=True)
class AppointmentReadResult:
    appointments: tuple[AppointmentRecord, ...]


@dataclass(frozen=True)
class CreateAppointmentRequest:
    patient_id: str
    branch_id: str
    service_id: str
    doctor_id: str
    start_at: datetime
    operation_id: str
    customer_note: str = ""
    patient_package_id: str | None = None


@dataclass(frozen=True)
class ConfirmAppointmentRequest:
    patient_id: str
    appointment_id: str
    operation_id: str


@dataclass(frozen=True)
class CancelAppointmentRequest:
    patient_id: str
    appointment_id: str
    operation_id: str
    reason: str = "customer_requested"
    now: datetime | None = None


@dataclass(frozen=True)
class RescheduleAppointmentRequest:
    patient_id: str
    appointment_id: str
    start_at: datetime
    operation_id: str
    branch_id: str | None = None
    doctor_id: str | None = None
    reason: str = ""


@dataclass(frozen=True)
class AppointmentMutationResult:
    appointment: AppointmentRecord
    previous_appointment_id: str | None = None


class ClinicAdapter(ABC):
    """Canonical boundary between Tia's agent and a clinic's source system.

    The agent should depend on this interface rather than SQLAlchemy models or a
    vendor-specific API. Phase 2 migrates one business capability at a time so
    existing booking behavior can stay stable while the storage boundary moves.
    """

    @property
    def cache_namespace(self) -> str:
        """Stable adapter identity used by callers for observability/caching."""
        return self.__class__.__name__

    @property
    @abstractmethod
    def capabilities(self) -> ClinicCapabilities:
        """Return the operations the connected clinic system can safely support."""
        raise NotImplementedError

    def require_capability(self, capability: ClinicCapability) -> None:
        self.capabilities.require(capability)

    def catalog_revision(self) -> Hashable | None:
        """Return a freshness token for the current catalog, if available.

        ``None`` means the source system cannot provide a cheap revision token;
        callers should rebuild rather than reuse a cached catalog blindly.
        """
        return None

    @abstractmethod
    def build_catalog(self) -> dict[str, Any]:
        """Return the canonical services/branches/doctors catalog for the agent."""
        raise NotImplementedError

    @abstractmethod
    def get_availability(self, request: AvailabilityRequest) -> AvailabilityResult:
        """Return verified availability using the clinic system's own source of truth."""
        raise NotImplementedError

    @abstractmethod
    def get_patient_appointments(
        self, request: AppointmentReadRequest
    ) -> AppointmentReadResult:
        """Return verified appointments belonging to one clinic patient."""
        raise NotImplementedError

    def get_patient(self, request: PatientReadRequest) -> PatientRecord:
        """Return one verified patient through the source-system boundary."""
        self.require_capability(ClinicCapability.PATIENTS_READ)
        raise NotImplementedError

    def get_patient_payments(self, request: PaymentReadRequest) -> PaymentReadResult:
        """Return canonical payment/refund facts owned by the clinic source."""
        self.require_capability(ClinicCapability.PAYMENTS_READ)
        raise NotImplementedError

    def create_appointment(
        self, request: CreateAppointmentRequest
    ) -> AppointmentMutationResult:
        """Create an appointment after revalidating the selected slot."""
        self.require_capability(ClinicCapability.APPOINTMENTS_CREATE)
        raise NotImplementedError

    def confirm_appointment(
        self, request: ConfirmAppointmentRequest
    ) -> AppointmentMutationResult:
        """Confirm one patient-owned appointment according to clinic policy."""
        self.require_capability(ClinicCapability.APPOINTMENTS_CONFIRM)
        raise NotImplementedError

    def cancel_appointment(
        self, request: CancelAppointmentRequest
    ) -> AppointmentMutationResult:
        """Cancel one patient-owned appointment according to clinic policy."""
        self.require_capability(ClinicCapability.APPOINTMENTS_CANCEL)
        raise NotImplementedError

    def reschedule_appointment(
        self, request: RescheduleAppointmentRequest
    ) -> AppointmentMutationResult:
        """Move one patient-owned appointment to an exact verified slot."""
        self.require_capability(ClinicCapability.APPOINTMENTS_RESCHEDULE)
        raise NotImplementedError
