from __future__ import annotations

from datetime import UTC, date, datetime, time, timedelta
from uuid import UUID
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from sqlalchemy import case, func, select
from sqlalchemy.orm import Session

from app.models.appointment import Appointment
from app.models.branch import Branch
from app.models.conversation import Conversation
from app.models.handoff_request import HandoffRequest
from app.models.patient import Patient
from app.models.payment_transaction import PaymentAllocation, PaymentTransaction
from app.models.service import Service
from app.schemas.analytics import (
    AnalyticsBreakdownRead,
    AnalyticsDailyRead,
    AnalyticsMoneyRead,
    AnalyticsOverviewRead,
)

ANALYTICS_ALLOWED_DAYS = (7, 30, 90)


def _workspace_timezone(name: str) -> ZoneInfo:
    try:
        return ZoneInfo(name)
    except ZoneInfoNotFoundError:
        return ZoneInfo("Africa/Cairo")


def analytics_period_bounds(
    *, timezone_name: str, days: int, now: datetime | None = None
) -> tuple[datetime, datetime, date, date]:
    if days not in ANALYTICS_ALLOWED_DAYS:
        raise ValueError(f"days must be one of {ANALYTICS_ALLOWED_DAYS}")
    tz = _workspace_timezone(timezone_name)
    current = now or datetime.now(UTC)
    if current.tzinfo is None:
        current = current.replace(tzinfo=UTC)
    local_today = current.astimezone(tz).date()
    start_date = local_today - timedelta(days=days - 1)
    end_date = local_today + timedelta(days=1)
    start_local = datetime.combine(start_date, time.min, tzinfo=tz)
    end_local = datetime.combine(end_date, time.min, tzinfo=tz)
    return start_local.astimezone(UTC), end_local.astimezone(UTC), start_date, local_today


def _percent(numerator: int, denominator: int) -> float:
    if denominator <= 0:
        return 0.0
    return round((numerator / denominator) * 100.0, 1)


def _appointment_scope(workspace_id: UUID, start_at: datetime, end_at: datetime):
    return (
        Appointment.workspace_id == workspace_id,
        Appointment.start_at >= start_at,
        Appointment.start_at < end_at,
        Appointment.status != "rescheduled",
    )


def _breakdown_rows(
    db: Session,
    *,
    workspace_id: UUID,
    start_at: datetime,
    end_at: datetime,
    entity,
    entity_id,
    appointment_entity_id,
    limit: int = 5,
) -> list[AnalyticsBreakdownRead]:
    completed_count = func.count(Appointment.id).filter(Appointment.status == "completed")
    rows = db.execute(
        select(
            entity_id.label("id"),
            entity.name.label("name"),
            func.count(Appointment.id).label("appointments"),
            completed_count.label("completed"),
            func.count(Appointment.id).filter(Appointment.status == "no_show").label("no_show"),
            func.count(Appointment.id)
            .filter(Appointment.status == "cancelled")
            .label("cancelled"),
        )
        .join(
            Appointment,
            (Appointment.workspace_id == entity.workspace_id)
            & (appointment_entity_id == entity_id),
        )
        .where(*_appointment_scope(workspace_id, start_at, end_at))
        .group_by(entity_id, entity.name)
        .order_by(completed_count.desc(), func.count(Appointment.id).desc(), entity.name)
        .limit(limit)
    ).all()
    return [
        AnalyticsBreakdownRead(
            id=row.id,
            name=row.name,
            appointments=int(row.appointments or 0),
            completed=int(row.completed or 0),
            no_show=int(row.no_show or 0),
            cancelled=int(row.cancelled or 0),
        )
        for row in rows
    ]


def analytics_overview(
    db: Session,
    *,
    workspace_id: UUID,
    timezone_name: str,
    days: int,
    now: datetime | None = None,
) -> AnalyticsOverviewRead:
    resolved_timezone_name = _workspace_timezone(timezone_name).key
    start_at, end_at, start_date, local_today = analytics_period_bounds(
        timezone_name=resolved_timezone_name,
        days=days,
        now=now,
    )
    scope = _appointment_scope(workspace_id, start_at, end_at)

    appointment_counts = db.execute(
        select(
            func.count(Appointment.id).label("total"),
            func.count(Appointment.id)
            .filter(Appointment.status == "completed")
            .label("completed"),
            func.count(Appointment.id).filter(Appointment.status == "no_show").label("no_show"),
            func.count(Appointment.id)
            .filter(Appointment.status == "cancelled")
            .label("cancelled"),
            func.count(Appointment.id)
            .filter(Appointment.status.in_(("pending", "confirmed")))
            .label("pending_or_confirmed"),
        ).where(*scope)
    ).one()

    total = int(appointment_counts.total or 0)
    completed = int(appointment_counts.completed or 0)
    no_show = int(appointment_counts.no_show or 0)
    cancelled = int(appointment_counts.cancelled or 0)
    pending_or_confirmed = int(appointment_counts.pending_or_confirmed or 0)
    attendance_denominator = completed + no_show

    new_patients = int(
        db.scalar(
            select(func.count(Patient.id)).where(
                Patient.workspace_id == workspace_id,
                func.coalesce(Patient.source_created_at, Patient.created_at) >= start_at,
                func.coalesce(Patient.source_created_at, Patient.created_at) < end_at,
            )
        )
        or 0
    )
    conversations_started = int(
        db.scalar(
            select(func.count(Conversation.id)).where(
                Conversation.workspace_id == workspace_id,
                Conversation.started_at >= start_at,
                Conversation.started_at < end_at,
            )
        )
        or 0
    )
    handoffs_created = int(
        db.scalar(
            select(func.count(HandoffRequest.id)).where(
                HandoffRequest.workspace_id == workspace_id,
                HandoffRequest.created_at >= start_at,
                HandoffRequest.created_at < end_at,
            )
        )
        or 0
    )

    payment_agg = (
        select(
            PaymentAllocation.appointment_id.label("appointment_id"),
            func.coalesce(
                func.sum(
                    case(
                        (PaymentTransaction.transaction_type == "payment", PaymentAllocation.amount_minor),
                        else_=0,
                    )
                ),
                0,
            ).label("gross_paid_minor"),
            func.coalesce(
                func.sum(
                    case(
                        (PaymentTransaction.transaction_type == "refund", PaymentAllocation.amount_minor),
                        else_=0,
                    )
                ),
                0,
            ).label("refunded_minor"),
        )
        .join(
            PaymentTransaction,
            (PaymentTransaction.workspace_id == PaymentAllocation.workspace_id)
            & (PaymentTransaction.id == PaymentAllocation.transaction_id),
        )
        .where(PaymentAllocation.workspace_id == workspace_id)
        .group_by(PaymentAllocation.appointment_id)
        .subquery()
    )
    net_paid = func.greatest(
        func.coalesce(payment_agg.c.gross_paid_minor, 0)
        - func.coalesce(payment_agg.c.refunded_minor, 0),
        0,
    )
    money_rows = db.execute(
        select(
            Appointment.currency.label("currency"),
            func.coalesce(func.sum(Appointment.price_minor), 0).label("completed_value_minor"),
            func.coalesce(func.sum(func.coalesce(payment_agg.c.gross_paid_minor, 0)), 0).label("gross_paid_minor"),
            func.coalesce(func.sum(func.coalesce(payment_agg.c.refunded_minor, 0)), 0).label("refunded_minor"),
            func.coalesce(func.sum(net_paid), 0).label("recorded_paid_minor"),
            func.coalesce(
                func.sum(func.greatest(Appointment.price_minor - net_paid, 0)),
                0,
            ).label("outstanding_balance_minor"),
        )
        .outerjoin(payment_agg, payment_agg.c.appointment_id == Appointment.id)
        .where(*scope, Appointment.status == "completed")
        .group_by(Appointment.currency)
        .order_by(Appointment.currency)
    ).all()
    money = [
        AnalyticsMoneyRead(
            currency=row.currency,
            completed_value_minor=int(row.completed_value_minor or 0),
            gross_paid_minor=int(row.gross_paid_minor or 0),
            refunded_minor=int(row.refunded_minor or 0),
            recorded_paid_minor=int(row.recorded_paid_minor or 0),
            outstanding_balance_minor=int(row.outstanding_balance_minor or 0),
        )
        for row in money_rows
    ]

    top_services = _breakdown_rows(
        db,
        workspace_id=workspace_id,
        start_at=start_at,
        end_at=end_at,
        entity=Service,
        entity_id=Service.id,
        appointment_entity_id=Appointment.service_id,
    )
    top_branches = _breakdown_rows(
        db,
        workspace_id=workspace_id,
        start_at=start_at,
        end_at=end_at,
        entity=Branch,
        entity_id=Branch.id,
        appointment_entity_id=Appointment.branch_id,
    )

    # PostgreSQL timezone() keeps buckets aligned to the clinic's local calendar day.
    appointment_day = func.date(func.timezone(resolved_timezone_name, Appointment.start_at))
    appointment_daily_rows = db.execute(
        select(
            appointment_day.label("day"),
            func.count(Appointment.id).label("appointments"),
            func.count(Appointment.id)
            .filter(Appointment.status == "completed")
            .label("completed"),
            func.count(Appointment.id).filter(Appointment.status == "no_show").label("no_show"),
            func.count(Appointment.id)
            .filter(Appointment.status == "cancelled")
            .label("cancelled"),
        )
        .where(*scope)
        .group_by(appointment_day)
        .order_by(appointment_day)
    ).all()
    patient_day = func.date(func.timezone(resolved_timezone_name, Patient.created_at))
    patient_daily_rows = db.execute(
        select(patient_day.label("day"), func.count(Patient.id).label("new_patients"))
        .where(
            Patient.workspace_id == workspace_id,
            Patient.created_at >= start_at,
            Patient.created_at < end_at,
        )
        .group_by(patient_day)
        .order_by(patient_day)
    ).all()

    appointment_daily = {
        row.day: (
            int(row.appointments or 0),
            int(row.completed or 0),
            int(row.no_show or 0),
            int(row.cancelled or 0),
        )
        for row in appointment_daily_rows
    }
    patient_daily = {row.day: int(row.new_patients or 0) for row in patient_daily_rows}

    daily: list[AnalyticsDailyRead] = []
    current_day = start_date
    while current_day <= local_today:
        appts = appointment_daily.get(current_day, (0, 0, 0, 0))
        daily.append(
            AnalyticsDailyRead(
                date=current_day,
                appointments=appts[0],
                completed=appts[1],
                no_show=appts[2],
                cancelled=appts[3],
                new_patients=patient_daily.get(current_day, 0),
            )
        )
        current_day += timedelta(days=1)

    return AnalyticsOverviewRead(
        days=days,
        timezone=resolved_timezone_name,
        start_at=start_at,
        end_at=end_at,
        total_appointments=total,
        completed_appointments=completed,
        no_show_appointments=no_show,
        cancelled_appointments=cancelled,
        pending_or_confirmed_appointments=pending_or_confirmed,
        attendance_rate_percent=_percent(completed, attendance_denominator),
        no_show_rate_percent=_percent(no_show, attendance_denominator),
        cancellation_rate_percent=_percent(cancelled, total),
        new_patients=new_patients,
        conversations_started=conversations_started,
        handoffs_created=handoffs_created,
        money=money,
        top_services=top_services,
        top_branches=top_branches,
        daily=daily,
    )
