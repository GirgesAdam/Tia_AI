from __future__ import annotations

from datetime import datetime
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.appointment import Appointment
from app.models.workspace import Workspace
from app.services.appointment_operations import (
    AppointmentOperationError,
    cancel_appointment_operation,
    reschedule_appointment_operation,
)


def _visit_members(
    db: Session,
    *,
    workspace_id: UUID,
    patient_id: UUID,
    visit_group_id: UUID,
    appointment_ids: tuple[UUID, ...],
) -> list[Appointment]:
    if len(appointment_ids) < 2:
        raise AppointmentOperationError("A grouped visit must contain at least two appointments.")
    rows = list(
        db.scalars(
            select(Appointment)
            .where(
                Appointment.workspace_id == workspace_id,
                Appointment.patient_id == patient_id,
                Appointment.visit_group_id == visit_group_id,
                Appointment.id.in_(appointment_ids),
            )
            .order_by(Appointment.start_at, Appointment.id)
        )
    )
    if {row.id for row in rows} != set(appointment_ids):
        raise AppointmentOperationError(
            "The verified visit group no longer matches its appointments."
        )
    return rows


def cancel_visit_group_operation(
    db: Session,
    *,
    workspace: Workspace,
    patient_id: UUID,
    visit_group_id: UUID,
    appointment_ids: tuple[UUID, ...],
    now: datetime | None = None,
) -> list[Appointment]:
    members = _visit_members(
        db,
        workspace_id=workspace.id,
        patient_id=patient_id,
        visit_group_id=visit_group_id,
        appointment_ids=appointment_ids,
    )
    cancelled: list[Appointment] = []
    with db.begin_nested():
        for member in members:
            cancelled.append(
                cancel_appointment_operation(
                    db,
                    workspace=workspace,
                    appointment_id=member.id,
                    changed_by_user_id=None,
                    patient_id=patient_id,
                    reason="customer_requested_visit_cancellation",
                    override_policy=False,
                    actor_is_admin=False,
                    actor_type="ai",
                    now=now,
                )
            )
    return cancelled


def _uuid(value: object, field: str) -> UUID:
    try:
        return UUID(str(value))
    except (TypeError, ValueError) as exc:
        raise AppointmentOperationError(
            f"Invalid grouped reschedule {field}."
        ) from exc


def _aware_datetime(value: object) -> datetime:
    parsed = value if isinstance(value, datetime) else datetime.fromisoformat(str(value))
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise AppointmentOperationError(
            "Grouped reschedule start_at must include a timezone offset."
        )
    return parsed


def reschedule_visit_group_operation(
    db: Session,
    *,
    workspace: Workspace,
    patient_id: UUID,
    visit_group_id: UUID,
    appointment_ids: tuple[UUID, ...],
    components: list[dict[str, object]],
    idempotency_key: str | None = None,
    now: datetime | None = None,
) -> list[tuple[Appointment, Appointment]]:
    members = _visit_members(
        db,
        workspace_id=workspace.id,
        patient_id=patient_id,
        visit_group_id=visit_group_id,
        appointment_ids=appointment_ids,
    )
    targets = {str(item.get("appointment_id")): item for item in components}
    if set(targets) != {str(member.id) for member in members}:
        raise AppointmentOperationError(
            "Grouped reschedule targets do not match the verified visit."
        )

    moved: list[tuple[Appointment, Appointment]] = []
    excluded_appointment_ids = set(appointment_ids)
    with db.begin_nested():
        for member in members:
            target = targets[str(member.id)]
            replacement, previous = reschedule_appointment_operation(
                db,
                workspace=workspace,
                appointment_id=member.id,
                requested_start_at=_aware_datetime(target.get("start_at")),
                changed_by_user_id=None,
                branch_id=_uuid(target.get("branch_id"), "branch_id"),
                doctor_id=_uuid(target.get("doctor_id"), "doctor_id"),
                service_id=_uuid(target.get("service_id"), "service_id"),
                laser_device_key=(
                    str(target["device_key"]) if target.get("device_key") else None
                ),
                patient_id=patient_id,
                idempotency_key=(
                    f"{idempotency_key}:{member.id}" if idempotency_key else None
                ),
                actor_type="ai",
                now=now,
                exclude_appointment_ids=tuple(excluded_appointment_ids),
            )
            excluded_appointment_ids.add(replacement.id)
            moved.append((replacement, previous))
    return moved
