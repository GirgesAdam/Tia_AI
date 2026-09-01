from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, date, datetime, time, timedelta
from uuid import UUID
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.appointment import ACTIVE_APPOINTMENT_STATUSES, Appointment
from app.models.booking_settings import BookingSettings
from app.models.branch import Branch
from app.models.doctor import Doctor
from app.models.doctor_branch import DoctorBranch
from app.models.doctor_service import DoctorService
from app.models.service import Service
from app.models.working_hours import BranchWorkingHour, DoctorAvailabilityWindow, DoctorWorkingHour
from app.models.workspace import Workspace


class BookingRuleError(ValueError):
    pass


@dataclass(frozen=True)
class EffectiveBookingSettings:
    slot_interval_minutes: int = 15
    minimum_notice_minutes: int = 60
    booking_horizon_days: int = 90
    cancellation_notice_minutes: int = 720
    allow_same_day_booking: bool = True
    require_confirmation: bool = True
    default_currency: str = "EGP"


@dataclass(frozen=True)
class SlotCandidate:
    branch_id: UUID
    doctor_id: UUID
    service_id: UUID
    start_at: datetime
    end_at: datetime
    busy_start_at: datetime
    busy_end_at: datetime
    duration_minutes: int
    price_minor: int
    currency: str


def get_effective_booking_settings(db: Session, workspace_id: UUID) -> EffectiveBookingSettings:
    row = db.scalar(select(BookingSettings).where(BookingSettings.workspace_id == workspace_id))
    if row is None:
        return EffectiveBookingSettings()
    return EffectiveBookingSettings(
        slot_interval_minutes=row.slot_interval_minutes,
        minimum_notice_minutes=row.minimum_notice_minutes,
        booking_horizon_days=row.booking_horizon_days,
        cancellation_notice_minutes=row.cancellation_notice_minutes,
        allow_same_day_booking=row.allow_same_day_booking,
        require_confirmation=row.require_confirmation,
        default_currency=row.default_currency,
    )


def resolve_timezone(workspace: Workspace, branch: Branch) -> ZoneInfo:
    timezone_name = branch.timezone or workspace.timezone
    try:
        return ZoneInfo(timezone_name)
    except ZoneInfoNotFoundError as exc:
        raise BookingRuleError(f"Invalid clinic timezone: {timezone_name}") from exc


def ceil_to_interval(value: datetime, interval_minutes: int) -> datetime:
    midnight = value.replace(hour=0, minute=0, second=0, microsecond=0)
    elapsed_minutes = int((value - midnight).total_seconds() // 60)
    remainder = elapsed_minutes % interval_minutes
    if remainder == 0 and value.second == 0 and value.microsecond == 0:
        return value
    add_minutes = interval_minutes - remainder
    rounded = value + timedelta(minutes=add_minutes)
    return rounded.replace(second=0, microsecond=0)


def _combine(local_date: date, local_time: time, tz: ZoneInfo) -> datetime:
    return datetime.combine(local_date, local_time, tzinfo=tz)


def _interval_intersections(
    branch_hours: list[BranchWorkingHour],
    doctor_hours: list[DoctorWorkingHour],
    local_date: date,
    tz: ZoneInfo,
) -> list[tuple[datetime, datetime]]:
    intersections: list[tuple[datetime, datetime]] = []
    for branch_hour in branch_hours:
        branch_start = _combine(local_date, branch_hour.start_time, tz)
        branch_end = _combine(local_date, branch_hour.end_time, tz)
        for doctor_hour in doctor_hours:
            doctor_start = _combine(local_date, doctor_hour.start_time, tz)
            doctor_end = _combine(local_date, doctor_hour.end_time, tz)
            start = max(branch_start, doctor_start)
            end = min(branch_end, doctor_end)
            if end > start:
                intersections.append((start, end))
    return intersections


def _window_intersections(
    branch_hours: list[BranchWorkingHour],
    windows: list[DoctorAvailabilityWindow],
    local_date: date,
    tz: ZoneInfo,
) -> list[tuple[datetime, datetime]]:
    intersections: list[tuple[datetime, datetime]] = []
    for branch_hour in branch_hours:
        branch_start = _combine(local_date, branch_hour.start_time, tz)
        branch_end = _combine(local_date, branch_hour.end_time, tz)
        for window in windows:
            doctor_start = window.start_at.astimezone(tz)
            doctor_end = window.end_at.astimezone(tz)
            start = max(branch_start, doctor_start)
            end = min(branch_end, doctor_end)
            if end > start:
                intersections.append((start, end))
    return intersections


def service_duration_minutes(service: Service) -> int:
    """Return the clinic-wide duration for a service.

    Duration is intentionally service-owned. Doctor-service assignments may
    control eligibility and price, but every doctor blocks the same amount of
    time for the same service.
    """
    return int(service.duration_minutes)


def _overlaps_existing(
    busy_start_at: datetime,
    busy_end_at: datetime,
    appointments: list[Appointment],
) -> bool:
    return any(
        appointment.busy_start_at < busy_end_at and appointment.busy_end_at > busy_start_at
        for appointment in appointments
    )


def calculate_availability(
    db: Session,
    workspace: Workspace,
    branch_id: UUID,
    service_id: UUID,
    booking_date: date,
    doctor_id: UUID | None = None,
    exclude_appointment_id: UUID | None = None,
    now: datetime | None = None,
    preloaded_branch: Branch | None = None,
    preloaded_service: Service | None = None,
) -> tuple[str, list[SlotCandidate]]:
    # Composite booking reads already resolve active branch/service rows before
    # availability calculation. Reuse those exact ORM rows when supplied instead
    # of re-reading them over a remote DB connection. Callers that do not have
    # verified rows retain the original lookup/validation path.
    if preloaded_branch is not None:
        if (
            preloaded_branch.id != branch_id
            or preloaded_branch.workspace_id != workspace.id
            or not preloaded_branch.is_active
        ):
            raise BookingRuleError("Branch not found or inactive.")
        branch = preloaded_branch
    else:
        branch = db.scalar(
            select(Branch).where(
                Branch.id == branch_id,
                Branch.workspace_id == workspace.id,
                Branch.is_active.is_(True),
            )
        )
        if branch is None:
            raise BookingRuleError("Branch not found or inactive.")

    if preloaded_service is not None:
        if (
            preloaded_service.id != service_id
            or preloaded_service.workspace_id != workspace.id
            or not preloaded_service.is_active
        ):
            raise BookingRuleError("Service not found or inactive.")
        service = preloaded_service
    else:
        service = db.scalar(
            select(Service).where(
                Service.id == service_id,
                Service.workspace_id == workspace.id,
                Service.is_active.is_(True),
            )
        )
        if service is None:
            raise BookingRuleError("Service not found or inactive.")

    tz = resolve_timezone(workspace, branch)
    settings = get_effective_booking_settings(db, workspace.id)
    now_utc = (now or datetime.now(UTC)).astimezone(UTC)
    local_today = now_utc.astimezone(tz).date()

    if booking_date < local_today:
        raise BookingRuleError("Cannot book a date in the past.")
    if booking_date > local_today + timedelta(days=settings.booking_horizon_days):
        raise BookingRuleError("Requested date is outside the booking horizon.")
    if booking_date == local_today and not settings.allow_same_day_booking:
        return tz.key, []

    weekday = booking_date.weekday()
    branch_hours = list(
        db.scalars(
            select(BranchWorkingHour).where(
                BranchWorkingHour.workspace_id == workspace.id,
                BranchWorkingHour.branch_id == branch.id,
                BranchWorkingHour.weekday == weekday,
            )
        )
    )
    if not branch_hours:
        return tz.key, []

    assignment_stmt = (
        select(DoctorBranch, DoctorService, Doctor)
        .join(
            DoctorService,
            (DoctorService.workspace_id == DoctorBranch.workspace_id)
            & (DoctorService.doctor_id == DoctorBranch.doctor_id),
        )
        .join(
            Doctor,
            (Doctor.workspace_id == DoctorBranch.workspace_id)
            & (Doctor.id == DoctorBranch.doctor_id),
        )
        .where(
            DoctorBranch.workspace_id == workspace.id,
            DoctorBranch.branch_id == branch.id,
            DoctorBranch.is_active.is_(True),
            DoctorService.service_id == service.id,
            DoctorService.is_active.is_(True),
            Doctor.is_active.is_(True),
            Doctor.booking_enabled.is_(True),
        )
    )
    if doctor_id is not None:
        assignment_stmt = assignment_stmt.where(DoctorBranch.doctor_id == doctor_id)

    assignments = list(db.execute(assignment_stmt).all())
    if doctor_id is not None and not assignments:
        raise BookingRuleError("Doctor is not available for this service at this branch.")
    if not assignments:
        return tz.key, []

    doctor_ids = [doctor.id for _, _, doctor in assignments]
    day_start_local = datetime.combine(booking_date, time.min, tzinfo=tz)
    day_end_local = day_start_local + timedelta(days=1)
    day_start_utc = day_start_local.astimezone(UTC)
    day_end_utc = day_end_local.astimezone(UTC)

    appointment_stmt = select(Appointment).where(
        Appointment.workspace_id == workspace.id,
        Appointment.doctor_id.in_(doctor_ids),
        Appointment.status.in_(ACTIVE_APPOINTMENT_STATUSES),
        Appointment.busy_start_at < day_end_utc,
        Appointment.busy_end_at > day_start_utc,
    )
    if exclude_appointment_id is not None:
        appointment_stmt = appointment_stmt.where(Appointment.id != exclude_appointment_id)
    existing = list(db.scalars(appointment_stmt))
    by_doctor: dict[UUID, list[Appointment]] = {doctor: [] for doctor in doctor_ids}
    for appointment in existing:
        by_doctor.setdefault(appointment.doctor_id, []).append(appointment)

    minimum_start_utc = now_utc + timedelta(minutes=settings.minimum_notice_minutes)
    slots: list[SlotCandidate] = []

    # Load all relevant doctor schedules in one query. This preserves the exact
    # availability rules while avoiding one DB round trip per doctor when the
    # customer did not constrain the request to a single doctor.
    doctor_hour_rows = list(
        db.scalars(
            select(DoctorWorkingHour).where(
                DoctorWorkingHour.workspace_id == workspace.id,
                DoctorWorkingHour.doctor_id.in_(doctor_ids),
                DoctorWorkingHour.branch_id == branch.id,
                DoctorWorkingHour.weekday == weekday,
            )
        )
    )
    doctor_hours_by_doctor: dict[UUID, list[DoctorWorkingHour]] = {
        doctor_id_value: [] for doctor_id_value in doctor_ids
    }
    for doctor_hour in doctor_hour_rows:
        doctor_hours_by_doctor.setdefault(doctor_hour.doctor_id, []).append(doctor_hour)

    window_rows = list(
        db.scalars(
            select(DoctorAvailabilityWindow).where(
                DoctorAvailabilityWindow.workspace_id == workspace.id,
                DoctorAvailabilityWindow.doctor_id.in_(doctor_ids),
                DoctorAvailabilityWindow.branch_id == branch.id,
                DoctorAvailabilityWindow.start_at < day_end_utc,
                DoctorAvailabilityWindow.end_at > day_start_utc,
            )
        )
    )
    windows_by_doctor: dict[UUID, list[DoctorAvailabilityWindow]] = {
        doctor_id_value: [] for doctor_id_value in doctor_ids
    }
    for window in window_rows:
        windows_by_doctor.setdefault(window.doctor_id, []).append(window)

    for _, doctor_service, doctor in assignments:
        doctor_hours = doctor_hours_by_doctor.get(doctor.id, [])
        dated_windows = windows_by_doctor.get(doctor.id, [])
        if doctor.doctor_type == "visiting":
            availability_intervals = _window_intersections(
                branch_hours, dated_windows, booking_date, tz
            )
        else:
            availability_intervals = _interval_intersections(
                branch_hours, doctor_hours, booking_date, tz
            )
            if dated_windows:
                availability_intervals.extend(
                    _window_intersections(branch_hours, dated_windows, booking_date, tz)
                )
        if not availability_intervals:
            continue

        # Clinic rule: appointment duration belongs to the service, never to the doctor.
        # DoctorService can still override price/assignment metadata for backwards compatibility,
        # but it must not change how long the chair/doctor is blocked.
        duration_minutes = service_duration_minutes(service)
        price_minor = (
            doctor_service.custom_price_minor
            if doctor_service.custom_price_minor is not None
            else service.price_minor
        )
        currency = service.currency or settings.default_currency
        before = timedelta(minutes=service.buffer_before_minutes)
        duration = timedelta(minutes=duration_minutes)
        after = timedelta(minutes=service.buffer_after_minutes)

        for interval_start, interval_end in availability_intervals:
            candidate = ceil_to_interval(
                interval_start + before,
                settings.slot_interval_minutes,
            )
            while True:
                service_start = candidate
                service_end = service_start + duration
                busy_start = service_start - before
                busy_end = service_end + after
                if busy_end > interval_end:
                    break

                start_utc = service_start.astimezone(UTC)
                end_utc = service_end.astimezone(UTC)
                busy_start_utc = busy_start.astimezone(UTC)
                busy_end_utc = busy_end.astimezone(UTC)

                if start_utc >= minimum_start_utc and not _overlaps_existing(
                    busy_start_utc,
                    busy_end_utc,
                    by_doctor.get(doctor.id, []),
                ):
                    slots.append(
                        SlotCandidate(
                            branch_id=branch.id,
                            doctor_id=doctor.id,
                            service_id=service.id,
                            start_at=start_utc,
                            end_at=end_utc,
                            busy_start_at=busy_start_utc,
                            busy_end_at=busy_end_utc,
                            duration_minutes=duration_minutes,
                            price_minor=price_minor,
                            currency=currency,
                        )
                    )

                candidate += timedelta(minutes=settings.slot_interval_minutes)

    slots.sort(key=lambda slot: (slot.start_at, str(slot.doctor_id)))
    return tz.key, slots


def find_exact_slot(
    db: Session,
    workspace: Workspace,
    branch_id: UUID,
    service_id: UUID,
    doctor_id: UUID,
    requested_start_at: datetime,
    exclude_appointment_id: UUID | None = None,
) -> SlotCandidate:
    requested_utc = requested_start_at.astimezone(UTC)

    branch = db.scalar(
        select(Branch).where(
            Branch.id == branch_id,
            Branch.workspace_id == workspace.id,
            Branch.is_active.is_(True),
        )
    )
    if branch is None:
        raise BookingRuleError("Branch not found or inactive.")
    tz = resolve_timezone(workspace, branch)
    booking_date = requested_utc.astimezone(tz).date()

    _, slots = calculate_availability(
        db=db,
        workspace=workspace,
        branch_id=branch_id,
        service_id=service_id,
        booking_date=booking_date,
        doctor_id=doctor_id,
        exclude_appointment_id=exclude_appointment_id,
    )
    for slot in slots:
        if slot.start_at == requested_utc:
            return slot
    raise BookingRuleError("Requested appointment slot is no longer available.")
