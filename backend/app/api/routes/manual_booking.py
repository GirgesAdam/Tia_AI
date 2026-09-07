from __future__ import annotations

from datetime import UTC, datetime
from typing import Annotated
from uuid import UUID
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field, field_validator, model_validator
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.api.dependencies.security import WorkspaceAccess, get_workspace_reader
from app.database.session import get_db
from app.integrations.clinic.authority import (
    ClinicIntegrationAuthorityError,
    require_tia_workspace_domain_write,
)
from app.models.appointment import Appointment
from app.models.appointment_status_history import AppointmentStatusHistory
from app.models.patient import Patient
from app.schemas.crm import normalize_patient_identity_phone, normalize_phone
from app.services.activity import record_activity_event
from app.services.booking import BookingRuleError, find_exact_slot, get_effective_booking_settings

router = APIRouter()


class ManualAppointmentCreate(BaseModel):
    patient_id: UUID | None = None
    first_name: str | None = Field(default=None, max_length=120)
    last_name: str | None = Field(default=None, max_length=120)
    phone: str | None = Field(default=None, max_length=40)
    branch_id: UUID
    doctor_id: UUID
    service_id: UUID
    start_at: datetime
    customer_note: str | None = Field(default=None, max_length=5000)

    @field_validator("first_name", "last_name", "phone", "customer_note", mode="before")
    @classmethod
    def strip_optional_text(cls, value: object) -> object:
        if isinstance(value, str):
            value = value.strip()
            return value or None
        return value

    @model_validator(mode="after")
    def validate_patient_target(self) -> ManualAppointmentCreate:
        if self.patient_id is None and (not self.first_name or not self.phone):
            raise ValueError("Choose an existing customer or enter the new customer's name and phone.")
        return self


class ManualAppointmentRead(BaseModel):
    appointment_id: UUID
    patient_id: UUID
    created_patient: bool
    status: str


def _workspace_timezone(name: str) -> ZoneInfo:
    try:
        return ZoneInfo(name or "Africa/Cairo")
    except ZoneInfoNotFoundError:
        return ZoneInfo("Africa/Cairo")


def _patient_phone_candidates(phone: str) -> tuple[str, str | None, set[str]]:
    display, normalized = normalize_phone(phone)
    identity_display, identity_normalized = normalize_patient_identity_phone(phone)
    display_value = display or identity_display or phone.strip()
    candidates = {value for value in (normalized, identity_normalized) if value}
    if identity_normalized and identity_normalized.startswith("+"):
        candidates.add(identity_normalized[1:])
    return display_value, identity_normalized or normalized, candidates


def _resolve_manual_patient(
    db: Session,
    *,
    access: WorkspaceAccess,
    payload: ManualAppointmentCreate,
) -> tuple[Patient, bool]:
    if payload.patient_id is not None:
        patient = db.scalar(
            select(Patient).where(
                Patient.workspace_id == access.workspace.id,
                Patient.id == payload.patient_id,
            )
        )
        if patient is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Customer not found.")
        if patient.status == "blocked":
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="Blocked customers cannot receive new appointments.",
            )
        return patient, False

    assert payload.first_name is not None and payload.phone is not None
    display_phone, normalized_phone, candidates = _patient_phone_candidates(payload.phone)
    patient = None
    if candidates:
        patient = db.scalar(
            select(Patient).where(
                Patient.workspace_id == access.workspace.id,
                Patient.phone_normalized.in_(tuple(candidates)),
            )
        )
    if patient is not None:
        if patient.status == "blocked":
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="Blocked customers cannot receive new appointments.",
            )
        return patient, False

    patient = Patient(
        workspace_id=access.workspace.id,
        first_name=payload.first_name,
        last_name=payload.last_name,
        phone=display_phone,
        phone_normalized=normalized_phone,
        preferred_language="ar",
        source="phone",
        source_detail="manual_appointment",
        status="active",
        marketing_consent=False,
    )
    db.add(patient)
    db.flush()
    return patient, True


@router.post(
    "/manual-appointments",
    response_model=ManualAppointmentRead,
    status_code=status.HTTP_201_CREATED,
)
def create_manual_appointment(
    payload: ManualAppointmentCreate,
    access: Annotated[WorkspaceAccess, Depends(get_workspace_reader)],
    db: Annotated[Session, Depends(get_db)],
) -> ManualAppointmentRead:
    try:
        require_tia_workspace_domain_write(
            db,
            workspace_id=access.workspace.id,
            domain="appointments",
        )
    except ClinicIntegrationAuthorityError as exc:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc)) from exc

    requested_start = payload.start_at
    if requested_start.tzinfo is None or requested_start.utcoffset() is None:
        requested_start = requested_start.replace(
            tzinfo=_workspace_timezone(access.workspace.timezone)
        )

    try:
        slot = find_exact_slot(
            db=db,
            workspace=access.workspace,
            branch_id=payload.branch_id,
            service_id=payload.service_id,
            doctor_id=payload.doctor_id,
            requested_start_at=requested_start,
        )
    except BookingRuleError as exc:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc)) from exc

    patient, created_patient = _resolve_manual_patient(db, access=access, payload=payload)
    settings = get_effective_booking_settings(db, access.workspace.id)
    initial_status = "pending" if settings.require_confirmation else "confirmed"
    now = datetime.now(UTC)
    appointment = Appointment(
        workspace_id=access.workspace.id,
        patient_id=patient.id,
        branch_id=payload.branch_id,
        doctor_id=payload.doctor_id,
        service_id=payload.service_id,
        patient_package_id=None,
        lead_id=None,
        created_by_user_id=access.user.id,
        rescheduled_from_appointment_id=None,
        status=initial_status,
        source="staff",
        start_at=slot.start_at,
        end_at=slot.end_at,
        busy_start_at=slot.busy_start_at,
        busy_end_at=slot.busy_end_at,
        duration_minutes=slot.duration_minutes,
        price_minor=slot.price_minor,
        currency=slot.currency,
        customer_note=payload.customer_note,
        confirmed_at=now if initial_status == "confirmed" else None,
    )
    db.add(appointment)
    try:
        db.flush()
        db.add(
            AppointmentStatusHistory(
                workspace_id=access.workspace.id,
                appointment_id=appointment.id,
                changed_by_user_id=access.user.id,
                from_status=None,
                to_status=initial_status,
                reason="manual_appointment_created",
                metadata_json={"created_patient": created_patient},
            )
        )
        record_activity_event(
            db,
            workspace_id=access.workspace.id,
            actor_type="staff",
            actor_user_id=access.user.id,
            action="appointment.created",
            entity_type="appointment",
            entity_id=appointment.id,
            summary="Manual appointment created",
            metadata={
                "status": initial_status,
                "source": "staff",
                "created_patient": created_patient,
            },
        )
        db.commit()
    except IntegrityError as exc:
        db.rollback()
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="The selected time is no longer available. Refresh and choose another time.",
        ) from exc

    return ManualAppointmentRead(
        appointment_id=appointment.id,
        patient_id=patient.id,
        created_patient=created_patient,
        status=appointment.status,
    )
