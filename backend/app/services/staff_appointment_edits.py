from __future__ import annotations

from datetime import UTC, timedelta
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.appointment import Appointment
from app.models.branch import Branch
from app.models.patient_package import PatientPackage
from app.models.workspace import Workspace
from app.services.activity import ActivityActorType, record_activity_event
from app.services.booking import (
    BookingRuleError,
    SlotCandidate,
    calculate_availability,
    resolve_timezone,
)
from app.services.patient_packages import PackageOperationError, release_package_usage
from app.services.payments import refresh_appointment_payment_snapshots

_EDITABLE_STATUSES = frozenset({"pending", "confirmed", "checked_in", "in_progress"})


class StaffAppointmentEditError(ValueError):
    pass


class StaffAppointmentEditNotFound(StaffAppointmentEditError):
    pass


def _locked_appointment(
    db: Session,
    *,
    workspace_id: UUID,
    appointment_id: UUID,
) -> Appointment:
    appointment = db.scalar(
        select(Appointment)
        .where(
            Appointment.workspace_id == workspace_id,
            Appointment.id == appointment_id,
        )
        .with_for_update()
    )
    if appointment is None:
        raise StaffAppointmentEditNotFound("Appointment not found.")
    return appointment


def _validated_slot_for_existing_appointment(
    db: Session,
    *,
    workspace: Workspace,
    appointment: Appointment,
    service_id: UUID,
    laser_device_key: str | None,
) -> SlotCandidate:
    """Validate the existing start time against the newly selected service.

    A receptionist editing an existing appointment is not creating a new booking,
    so minimum-notice/same-day policy must not block the correction. We validate
    availability as of the previous day while still enforcing the doctor/service
    assignment, working hours, duration, device price and doctor/device conflicts.
    """
    branch = db.scalar(
        select(Branch).where(
            Branch.workspace_id == workspace.id,
            Branch.id == appointment.branch_id,
            Branch.is_active.is_(True),
        )
    )
    if branch is None:
        raise StaffAppointmentEditError("Appointment branch is missing or inactive.")

    timezone = resolve_timezone(workspace, branch)
    booking_date = appointment.start_at.astimezone(timezone).date()
    validation_now = appointment.start_at.astimezone(UTC) - timedelta(days=1)
    try:
        _, slots = calculate_availability(
            db=db,
            workspace=workspace,
            branch_id=appointment.branch_id,
            service_id=service_id,
            booking_date=booking_date,
            doctor_id=appointment.doctor_id,
            exclude_appointment_id=appointment.id,
            now=validation_now,
            preloaded_branch=branch,
            laser_device_key=laser_device_key,
        )
    except BookingRuleError as exc:
        raise StaffAppointmentEditError(str(exc)) from exc

    requested_start = appointment.start_at.astimezone(UTC)
    for slot in slots:
        if slot.start_at == requested_start:
            return slot
    raise StaffAppointmentEditError(
        "The current appointment time is not available for the selected service/device with this doctor."
    )


def change_appointment_service(
    db: Session,
    *,
    workspace: Workspace,
    appointment_id: UUID,
    service_id: UUID,
    laser_device_key: str | None,
    changed_by_user_id: UUID | None,
    actor_type: ActivityActorType = "staff",
) -> Appointment:
    """Change a scheduled visit in place from the staff dashboard only.

    Payment allocations stay attached to the appointment and its payment snapshot is
    recalculated against the new service price. If the appointment was reserving a
    package that no longer matches the selected service/device, that reservation is
    released and the visit is converted to ordinary billing. No new package is
    auto-selected on a manual edit.
    """
    appointment = _locked_appointment(
        db,
        workspace_id=workspace.id,
        appointment_id=appointment_id,
    )
    if appointment.status not in _EDITABLE_STATUSES:
        raise StaffAppointmentEditError(
            "Only a pending, confirmed, checked-in or in-progress appointment can have its service changed."
        )

    normalized_device = (laser_device_key or "").strip() or None
    service_changed = service_id != appointment.service_id
    device_changed = normalized_device != (appointment.laser_device_key or None)
    if not service_changed and not device_changed:
        return appointment

    slot = _validated_slot_for_existing_appointment(
        db,
        workspace=workspace,
        appointment=appointment,
        service_id=service_id,
        laser_device_key=normalized_device,
    )

    old_service_id = appointment.service_id
    old_device_key = appointment.laser_device_key
    old_price_minor = int(appointment.price_minor)
    old_billing_context = appointment.billing_context
    old_package_id = appointment.patient_package_id
    package_released = False

    package_incompatible = service_changed
    if (
        not package_incompatible
        and device_changed
        and appointment.patient_package_id is not None
    ):
        package = db.scalar(
            select(PatientPackage).where(
                PatientPackage.workspace_id == workspace.id,
                PatientPackage.id == appointment.patient_package_id,
            )
        )
        if package is None:
            raise StaffAppointmentEditError("Appointment package is missing.")
        package_incompatible = bool(
            package.laser_device_key is not None
            and package.laser_device_key != slot.laser_device_key
        )

    if package_incompatible and (
        appointment.patient_package_id is not None
        or appointment.billing_context == "package_prepaid"
        or appointment.package_external_id
    ):
        if appointment.patient_package_id is not None:
            try:
                release_package_usage(
                    db,
                    appointment=appointment,
                    actor_type=actor_type,
                    actor_user_id=changed_by_user_id,
                    reason="staff_service_or_device_changed",
                )
            except PackageOperationError as exc:
                raise StaffAppointmentEditError(str(exc)) from exc
        appointment.patient_package_id = None
        appointment.billing_context = "standard"
        appointment.package_external_id = None
        package_released = True

    appointment.service_id = slot.service_id
    appointment.end_at = slot.end_at
    appointment.busy_start_at = slot.busy_start_at
    appointment.busy_end_at = slot.busy_end_at
    appointment.duration_minutes = slot.duration_minutes
    appointment.price_minor = slot.price_minor
    appointment.currency = slot.currency
    appointment.laser_device_key = slot.laser_device_key
    appointment.laser_device_name = slot.laser_device_name
    db.flush()

    refresh_appointment_payment_snapshots(
        db,
        workspace_id=workspace.id,
        appointment_ids={appointment.id},
    )
    record_activity_event(
        db,
        workspace_id=workspace.id,
        actor_type=actor_type,
        actor_user_id=changed_by_user_id,
        action="appointment.service_changed_by_staff",
        entity_type="appointment",
        entity_id=appointment.id,
        summary="Appointment service changed by staff",
        metadata={
            "old_service_id": old_service_id,
            "new_service_id": appointment.service_id,
            "old_device_key": old_device_key,
            "new_device_key": appointment.laser_device_key,
            "old_price_minor": old_price_minor,
            "new_price_minor": int(appointment.price_minor),
            "old_billing_context": old_billing_context,
            "new_billing_context": appointment.billing_context,
            "old_package_id": old_package_id,
            "package_reservation_released": package_released,
        },
    )
    db.flush()
    return appointment
