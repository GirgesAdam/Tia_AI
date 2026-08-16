from __future__ import annotations

from datetime import date, datetime, timedelta, timezone
from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, Header, HTTPException, Query, status
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.api.dependencies.security import WorkspaceAccess, get_workspace_reader
from app.database.session import get_db
from app.models.appointment import Appointment
from app.models.appointment_status_history import AppointmentStatusHistory
from app.models.lead import Lead
from app.models.patient import Patient
from app.models.workspace_member import WORKSPACE_ROLE_ADMIN
from app.schemas.booking import (
    AppointmentCancel,
    AppointmentCreate,
    AppointmentOperationalStatusUpdate,
    AppointmentRead,
    AppointmentReschedule,
    AppointmentStatus,
    AppointmentStatusHistoryRead,
    AvailabilityResponse,
    AvailabilitySlot,
)
from app.services.booking import (
    BookingRuleError,
    SlotCandidate,
    calculate_availability,
    find_exact_slot,
    get_effective_booking_settings,
)

router = APIRouter()


def not_found(entity: str) -> HTTPException:
    return HTTPException(
        status_code=status.HTTP_404_NOT_FOUND,
        detail=f"{entity} not found.",
    )


def booking_conflict(detail: str) -> HTTPException:
    return HTTPException(
        status_code=status.HTTP_409_CONFLICT,
        detail=detail,
    )


def get_appointment_or_404(db: Session, workspace_id: UUID, appointment_id: UUID) -> Appointment:
    appointment = db.scalar(
        select(Appointment).where(
            Appointment.id == appointment_id,
            Appointment.workspace_id == workspace_id,
        )
    )
    if appointment is None:
        raise not_found("Appointment")
    return appointment


def get_patient_for_booking(db: Session, workspace_id: UUID, patient_id: UUID) -> Patient:
    patient = db.scalar(
        select(Patient).where(
            Patient.id == patient_id,
            Patient.workspace_id == workspace_id,
        )
    )
    if patient is None:
        raise not_found("Patient")
    if patient.status == "blocked":
        raise booking_conflict("Blocked patients cannot receive new appointments.")
    return patient


def validate_lead(
    db: Session,
    workspace_id: UUID,
    patient_id: UUID,
    service_id: UUID,
    lead_id: UUID | None,
) -> Lead | None:
    if lead_id is None:
        return None
    lead = db.scalar(
        select(Lead).where(
            Lead.id == lead_id,
            Lead.workspace_id == workspace_id,
        )
    )
    if lead is None:
        raise not_found("Lead")
    if lead.patient_id != patient_id:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="Lead does not belong to the selected patient.",
        )
    if lead.service_id is not None and lead.service_id != service_id:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="Lead belongs to a different service.",
        )
    return lead


def add_history(
    db: Session,
    appointment: Appointment,
    changed_by_user_id: UUID | None,
    from_status: str | None,
    to_status: str,
    reason: str | None = None,
    metadata: dict | None = None,
) -> None:
    db.add(
        AppointmentStatusHistory(
            workspace_id=appointment.workspace_id,
            appointment_id=appointment.id,
            changed_by_user_id=changed_by_user_id,
            from_status=from_status,
            to_status=to_status,
            reason=reason,
            metadata_json=metadata or {},
        )
    )


def slot_to_response(slot: SlotCandidate) -> AvailabilitySlot:
    return AvailabilitySlot(
        branch_id=slot.branch_id,
        doctor_id=slot.doctor_id,
        service_id=slot.service_id,
        start_at=slot.start_at,
        end_at=slot.end_at,
        price_minor=slot.price_minor,
        currency=slot.currency,
    )


def make_appointment(
    *,
    access: WorkspaceAccess,
    payload: AppointmentCreate,
    slot: SlotCandidate,
    initial_status: str,
    idempotency_key: str | None,
    rescheduled_from_appointment_id: UUID | None = None,
) -> Appointment:
    now = datetime.now(timezone.utc)
    return Appointment(
        workspace_id=access.workspace.id,
        patient_id=payload.patient_id,
        branch_id=payload.branch_id,
        doctor_id=payload.doctor_id,
        service_id=payload.service_id,
        lead_id=payload.lead_id,
        created_by_user_id=access.user.id,
        rescheduled_from_appointment_id=rescheduled_from_appointment_id,
        status=initial_status,
        source=payload.source,
        start_at=slot.start_at,
        end_at=slot.end_at,
        busy_start_at=slot.busy_start_at,
        busy_end_at=slot.busy_end_at,
        duration_minutes=slot.duration_minutes,
        price_minor=slot.price_minor,
        currency=slot.currency,
        customer_note=payload.customer_note,
        idempotency_key=idempotency_key,
        confirmed_at=now if initial_status == "confirmed" else None,
    )


@router.get("/availability", response_model=AvailabilityResponse)
def get_availability(
    branch_id: UUID,
    service_id: UUID,
    booking_date: Annotated[date, Query(alias="date")],
    access: Annotated[WorkspaceAccess, Depends(get_workspace_reader)],
    db: Annotated[Session, Depends(get_db)],
    doctor_id: UUID | None = None,
) -> AvailabilityResponse:
    try:
        timezone_name, slots = calculate_availability(
            db=db,
            workspace=access.workspace,
            branch_id=branch_id,
            service_id=service_id,
            booking_date=booking_date,
            doctor_id=doctor_id,
        )
    except BookingRuleError as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=str(exc),
        ) from exc

    return AvailabilityResponse(
        date=booking_date,
        timezone=timezone_name,
        slots=[slot_to_response(slot) for slot in slots],
    )


@router.post(
    "/appointments",
    response_model=AppointmentRead,
    status_code=status.HTTP_201_CREATED,
)
def create_appointment(
    payload: AppointmentCreate,
    access: Annotated[WorkspaceAccess, Depends(get_workspace_reader)],
    db: Annotated[Session, Depends(get_db)],
    idempotency_key: Annotated[
        str | None,
        Header(alias="Idempotency-Key", max_length=128),
    ] = None,
) -> Appointment:
    if idempotency_key:
        existing = db.scalar(
            select(Appointment).where(
                Appointment.workspace_id == access.workspace.id,
                Appointment.idempotency_key == idempotency_key,
            )
        )
        if existing is not None:
            return existing

    get_patient_for_booking(db, access.workspace.id, payload.patient_id)
    lead = validate_lead(
        db,
        access.workspace.id,
        payload.patient_id,
        payload.service_id,
        payload.lead_id,
    )

    try:
        slot = find_exact_slot(
            db=db,
            workspace=access.workspace,
            branch_id=payload.branch_id,
            service_id=payload.service_id,
            doctor_id=payload.doctor_id,
            requested_start_at=payload.start_at,
        )
    except BookingRuleError as exc:
        raise booking_conflict(str(exc)) from exc

    settings = get_effective_booking_settings(db, access.workspace.id)
    initial_status = "pending" if settings.require_confirmation else "confirmed"
    appointment = make_appointment(
        access=access,
        payload=payload,
        slot=slot,
        initial_status=initial_status,
        idempotency_key=idempotency_key,
    )
    try:
        db.add(appointment)
        db.flush()
        add_history(
            db,
            appointment,
            changed_by_user_id=access.user.id,
            from_status=None,
            to_status=initial_status,
            reason="appointment_created",
        )
        if lead is not None and lead.status not in {"lost", "spam", "won"}:
            if lead.service_id is None:
                lead.service_id = payload.service_id
            lead.status = "booked"
        db.commit()
    except IntegrityError as exc:
        db.rollback()
        raise booking_conflict(
            "The requested slot was booked by another request. Refresh availability and try again."
        ) from exc
    db.refresh(appointment)
    return appointment


@router.get("/appointments", response_model=list[AppointmentRead])
def list_appointments(
    access: Annotated[WorkspaceAccess, Depends(get_workspace_reader)],
    db: Annotated[Session, Depends(get_db)],
    patient_id: UUID | None = None,
    doctor_id: UUID | None = None,
    branch_id: UUID | None = None,
    appointment_status: Annotated[AppointmentStatus | None, Query(alias="status")] = None,
    start_from: datetime | None = None,
    start_to: datetime | None = None,
    limit: Annotated[int, Query(ge=1, le=200)] = 100,
    offset: Annotated[int, Query(ge=0)] = 0,
) -> list[Appointment]:
    stmt = select(Appointment).where(Appointment.workspace_id == access.workspace.id)
    if patient_id:
        stmt = stmt.where(Appointment.patient_id == patient_id)
    if doctor_id:
        stmt = stmt.where(Appointment.doctor_id == doctor_id)
    if branch_id:
        stmt = stmt.where(Appointment.branch_id == branch_id)
    if appointment_status:
        stmt = stmt.where(Appointment.status == appointment_status)
    if start_from:
        if start_from.tzinfo is None or start_from.utcoffset() is None:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail="start_from must include a timezone offset.",
            )
        stmt = stmt.where(Appointment.start_at >= start_from.astimezone(timezone.utc))
    if start_to:
        if start_to.tzinfo is None or start_to.utcoffset() is None:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail="start_to must include a timezone offset.",
            )
        stmt = stmt.where(Appointment.start_at < start_to.astimezone(timezone.utc))
    stmt = stmt.order_by(Appointment.start_at.desc()).limit(limit).offset(offset)
    return list(db.scalars(stmt))


@router.get("/appointments/{appointment_id}", response_model=AppointmentRead)
def get_appointment(
    appointment_id: UUID,
    access: Annotated[WorkspaceAccess, Depends(get_workspace_reader)],
    db: Annotated[Session, Depends(get_db)],
) -> Appointment:
    return get_appointment_or_404(db, access.workspace.id, appointment_id)


@router.get(
    "/appointments/{appointment_id}/history",
    response_model=list[AppointmentStatusHistoryRead],
)
def get_appointment_history(
    appointment_id: UUID,
    access: Annotated[WorkspaceAccess, Depends(get_workspace_reader)],
    db: Annotated[Session, Depends(get_db)],
) -> list[AppointmentStatusHistory]:
    get_appointment_or_404(db, access.workspace.id, appointment_id)
    return list(
        db.scalars(
            select(AppointmentStatusHistory)
            .where(
                AppointmentStatusHistory.workspace_id == access.workspace.id,
                AppointmentStatusHistory.appointment_id == appointment_id,
            )
            .order_by(AppointmentStatusHistory.created_at)
        )
    )


@router.post("/appointments/{appointment_id}/confirm", response_model=AppointmentRead)
def confirm_appointment(
    appointment_id: UUID,
    access: Annotated[WorkspaceAccess, Depends(get_workspace_reader)],
    db: Annotated[Session, Depends(get_db)],
) -> Appointment:
    appointment = get_appointment_or_404(db, access.workspace.id, appointment_id)
    if appointment.status == "confirmed":
        return appointment
    if appointment.status != "pending":
        raise booking_conflict(f"Cannot confirm an appointment with status '{appointment.status}'.")

    old_status = appointment.status
    appointment.status = "confirmed"
    appointment.confirmed_at = datetime.now(timezone.utc)
    add_history(
        db,
        appointment,
        changed_by_user_id=access.user.id,
        from_status=old_status,
        to_status="confirmed",
        reason="appointment_confirmed",
    )
    db.commit()
    db.refresh(appointment)
    return appointment


@router.post("/appointments/{appointment_id}/cancel", response_model=AppointmentRead)
def cancel_appointment(
    appointment_id: UUID,
    payload: AppointmentCancel,
    access: Annotated[WorkspaceAccess, Depends(get_workspace_reader)],
    db: Annotated[Session, Depends(get_db)],
) -> Appointment:
    appointment = get_appointment_or_404(db, access.workspace.id, appointment_id)
    if appointment.status == "cancelled":
        return appointment
    if appointment.status in {"completed", "no_show", "rescheduled"}:
        raise booking_conflict(f"Cannot cancel an appointment with status '{appointment.status}'.")

    now = datetime.now(timezone.utc)
    settings = get_effective_booking_settings(db, access.workspace.id)
    inside_notice_window = appointment.start_at - now < timedelta(
        minutes=settings.cancellation_notice_minutes
    )
    if inside_notice_window:
        if not payload.override_policy:
            raise booking_conflict(
                "Cancellation is inside the configured notice window. An admin override is required."
            )
        if access.membership.role != WORKSPACE_ROLE_ADMIN:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Only an admin can override the cancellation notice policy.",
            )

    old_status = appointment.status
    appointment.status = "cancelled"
    appointment.cancelled_at = now
    appointment.cancellation_reason = payload.reason
    add_history(
        db,
        appointment,
        changed_by_user_id=access.user.id,
        from_status=old_status,
        to_status="cancelled",
        reason=payload.reason,
        metadata={"override_policy": payload.override_policy},
    )
    db.commit()
    db.refresh(appointment)
    return appointment


@router.post("/appointments/{appointment_id}/reschedule", response_model=AppointmentRead)
def reschedule_appointment(
    appointment_id: UUID,
    payload: AppointmentReschedule,
    access: Annotated[WorkspaceAccess, Depends(get_workspace_reader)],
    db: Annotated[Session, Depends(get_db)],
    idempotency_key: Annotated[
        str | None,
        Header(alias="Idempotency-Key", max_length=128),
    ] = None,
) -> Appointment:
    if idempotency_key:
        existing = db.scalar(
            select(Appointment).where(
                Appointment.workspace_id == access.workspace.id,
                Appointment.idempotency_key == idempotency_key,
            )
        )
        if existing is not None:
            return existing

    current = get_appointment_or_404(db, access.workspace.id, appointment_id)
    if current.status not in {"pending", "confirmed"}:
        raise booking_conflict(
            f"Only pending or confirmed appointments can be rescheduled; current status is '{current.status}'."
        )

    branch_id = payload.branch_id or current.branch_id
    doctor_id = payload.doctor_id or current.doctor_id

    try:
        slot = find_exact_slot(
            db=db,
            workspace=access.workspace,
            branch_id=branch_id,
            service_id=current.service_id,
            doctor_id=doctor_id,
            requested_start_at=payload.start_at,
            exclude_appointment_id=current.id,
        )
    except BookingRuleError as exc:
        raise booking_conflict(str(exc)) from exc

    new_payload = AppointmentCreate(
        patient_id=current.patient_id,
        branch_id=branch_id,
        doctor_id=doctor_id,
        service_id=current.service_id,
        lead_id=current.lead_id,
        start_at=payload.start_at,
        source=current.source,
        customer_note=current.customer_note,
    )
    new_status = current.status
    old_start = current.start_at
    old_end = current.end_at
    old_status = current.status

    replacement = make_appointment(
        access=access,
        payload=new_payload,
        slot=slot,
        initial_status=new_status,
        idempotency_key=idempotency_key,
        rescheduled_from_appointment_id=current.id,
    )
    if new_status == "confirmed":
        replacement.confirmed_at = datetime.now(timezone.utc)

    try:
        current.status = "rescheduled"
        db.flush()
        db.add(replacement)
        db.flush()

        add_history(
            db,
            current,
            changed_by_user_id=access.user.id,
            from_status=old_status,
            to_status="rescheduled",
            reason=payload.reason or "appointment_rescheduled",
            metadata={
                "replacement_appointment_id": str(replacement.id),
                "old_start_at": old_start.isoformat(),
                "old_end_at": old_end.isoformat(),
                "new_start_at": replacement.start_at.isoformat(),
                "new_end_at": replacement.end_at.isoformat(),
            },
        )
        add_history(
            db,
            replacement,
            changed_by_user_id=access.user.id,
            from_status=None,
            to_status=new_status,
            reason="rescheduled_from_previous_appointment",
            metadata={"previous_appointment_id": str(current.id)},
        )
        db.commit()
    except IntegrityError as exc:
        db.rollback()
        raise booking_conflict(
            "The requested replacement slot was booked by another request. Refresh availability and try again."
        ) from exc
    db.refresh(replacement)
    return replacement


@router.post("/appointments/{appointment_id}/status", response_model=AppointmentRead)
def update_operational_status(
    appointment_id: UUID,
    payload: AppointmentOperationalStatusUpdate,
    access: Annotated[WorkspaceAccess, Depends(get_workspace_reader)],
    db: Annotated[Session, Depends(get_db)],
) -> Appointment:
    appointment = get_appointment_or_404(db, access.workspace.id, appointment_id)
    allowed_transitions: dict[str, set[str]] = {
        "confirmed": {"checked_in", "no_show"},
        "checked_in": {"in_progress"},
        "in_progress": {"completed"},
        "pending": {"no_show"},
    }
    if payload.status not in allowed_transitions.get(appointment.status, set()):
        raise booking_conflict(
            f"Cannot change appointment status from '{appointment.status}' to '{payload.status}'."
        )

    now = datetime.now(timezone.utc)
    if payload.status == "no_show" and now < appointment.start_at:
        raise booking_conflict("An appointment cannot be marked no-show before its start time.")

    old_status = appointment.status
    appointment.status = payload.status
    if payload.status == "completed":
        appointment.completed_at = now
    elif payload.status == "no_show":
        appointment.no_show_at = now

    add_history(
        db,
        appointment,
        changed_by_user_id=access.user.id,
        from_status=old_status,
        to_status=payload.status,
        reason=payload.reason,
    )
    db.commit()
    db.refresh(appointment)
    return appointment
