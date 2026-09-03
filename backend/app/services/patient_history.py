from __future__ import annotations

from uuid import UUID

from sqlalchemy import case, func, select
from sqlalchemy.orm import Session

from app.models.appointment import Appointment
from app.models.branch import Branch
from app.models.doctor import Doctor
from app.models.patient import Patient
from app.models.payment_transaction import PaymentAllocation, PaymentTransaction
from app.models.service import Service
from app.models.staff import Staff
from app.schemas.patient_history import (
    HistoricalAnalyticsRead,
    HistoricalAnalyticsServiceRead,
    PatientHistoryAppointmentRead,
    PatientHistoryContextRead,
    PatientHistoryMoneyRead,
    PatientHistoryProfileRead,
    PatientServiceHistoryRead,
)


def _percent(numerator: int, denominator: int) -> float:
    if denominator <= 0:
        return 0.0
    return round((numerator / denominator) * 100.0, 1)


def _payment_money_rows(db: Session, *, workspace_id: UUID, patient_id: UUID | None = None) -> list[PatientHistoryMoneyRead]:
    stmt = select(
        PaymentTransaction.currency,
        func.coalesce(func.sum(case((PaymentTransaction.transaction_type == "payment", PaymentTransaction.amount_minor), else_=0)), 0).label("gross"),
        func.coalesce(func.sum(case((PaymentTransaction.transaction_type == "refund", PaymentTransaction.amount_minor), else_=0)), 0).label("refunds"),
    ).where(PaymentTransaction.workspace_id == workspace_id)
    if patient_id is not None:
        stmt = stmt.where(PaymentTransaction.patient_id == patient_id)
    rows = db.execute(stmt.group_by(PaymentTransaction.currency).order_by(PaymentTransaction.currency)).all()
    return [
        PatientHistoryMoneyRead(
            currency=row.currency,
            gross_paid_minor=int(row.gross or 0),
            refunded_minor=int(row.refunds or 0),
            net_paid_minor=max(int(row.gross or 0) - int(row.refunds or 0), 0),
        )
        for row in rows
    ]


def build_patient_history_context(
    db: Session,
    *,
    workspace_id: UUID,
    patient: Patient,
    recent_limit: int = 20,
) -> PatientHistoryContextRead:
    recent_limit = max(1, min(int(recent_limit), 50))
    effective_first_seen = patient.source_created_at or patient.created_at

    counts = db.execute(
        select(
            func.count(Appointment.id).label("total"),
            func.count(Appointment.id).filter(Appointment.status == "completed").label("completed"),
            func.count(Appointment.id).filter(Appointment.status == "cancelled").label("cancelled"),
            func.count(Appointment.id).filter(Appointment.status == "no_show").label("no_show"),
            func.min(Appointment.start_at).label("first_appointment"),
            func.max(Appointment.start_at).label("last_appointment"),
        ).where(
            Appointment.workspace_id == workspace_id,
            Appointment.patient_id == patient.id,
            Appointment.status != "rescheduled",
        )
    ).one()

    payment_bounds = db.execute(
        select(func.min(PaymentTransaction.created_at), func.max(PaymentTransaction.created_at)).where(
            PaymentTransaction.workspace_id == workspace_id,
            PaymentTransaction.patient_id == patient.id,
        )
    ).one()
    activity_values = [effective_first_seen, counts.first_appointment, payment_bounds[0]]
    first_activity = min((value for value in activity_values if value is not None), default=None)
    last_values = [effective_first_seen, counts.last_appointment, payment_bounds[1]]
    last_activity = max((value for value in last_values if value is not None), default=None)

    service_rows = db.execute(
        select(
            Service.id,
            Service.name,
            func.count(Appointment.id).label("completed_visits"),
            func.min(Appointment.start_at).label("first_completed_at"),
            func.max(Appointment.start_at).label("last_completed_at"),
        )
        .join(Appointment, (Appointment.workspace_id == Service.workspace_id) & (Appointment.service_id == Service.id))
        .where(
            Appointment.workspace_id == workspace_id,
            Appointment.patient_id == patient.id,
            Appointment.status == "completed",
        )
        .group_by(Service.id, Service.name)
        .order_by(func.max(Appointment.start_at).desc(), Service.name)
    ).all()

    recent_rows = db.execute(
        select(Appointment, Service.name, Branch.name, Staff.first_name, Staff.last_name)
        .join(Service, (Service.workspace_id == Appointment.workspace_id) & (Service.id == Appointment.service_id))
        .join(Branch, (Branch.workspace_id == Appointment.workspace_id) & (Branch.id == Appointment.branch_id))
        .join(Doctor, (Doctor.workspace_id == Appointment.workspace_id) & (Doctor.id == Appointment.doctor_id))
        .join(Staff, (Staff.workspace_id == Doctor.workspace_id) & (Staff.id == Doctor.staff_id))
        .where(
            Appointment.workspace_id == workspace_id,
            Appointment.patient_id == patient.id,
            Appointment.status != "rescheduled",
        )
        .order_by(Appointment.start_at.desc(), Appointment.id.desc())
        .limit(recent_limit)
    ).all()
    recent_ids = [row[0].id for row in recent_rows]
    net_by_appointment: dict[UUID, int] = {}
    if recent_ids:
        alloc_rows = db.execute(
            select(
                PaymentAllocation.appointment_id,
                func.coalesce(func.sum(case((PaymentTransaction.transaction_type == "payment", PaymentAllocation.amount_minor), else_=-PaymentAllocation.amount_minor)), 0).label("net"),
            )
            .join(PaymentTransaction, (PaymentTransaction.workspace_id == PaymentAllocation.workspace_id) & (PaymentTransaction.id == PaymentAllocation.transaction_id))
            .where(
                PaymentAllocation.workspace_id == workspace_id,
                PaymentAllocation.appointment_id.in_(recent_ids),
            )
            .group_by(PaymentAllocation.appointment_id)
        ).all()
        net_by_appointment = {row.appointment_id: max(int(row.net or 0), 0) for row in alloc_rows}

    return PatientHistoryContextRead(
        profile=PatientHistoryProfileRead(
            patient_id=patient.id,
            first_name=patient.first_name,
            last_name=patient.last_name,
            phone=patient.phone,
            gender=patient.gender,
            birth_date=patient.birth_date,
            source_created_at=patient.source_created_at,
            tia_created_at=patient.created_at,
            effective_first_seen_at=effective_first_seen,
        ),
        first_clinic_activity_at=first_activity,
        last_clinic_activity_at=last_activity,
        total_appointments=int(counts.total or 0),
        completed_appointments=int(counts.completed or 0),
        cancelled_appointments=int(counts.cancelled or 0),
        no_show_appointments=int(counts.no_show or 0),
        money=_payment_money_rows(db, workspace_id=workspace_id, patient_id=patient.id),
        services=[
            PatientServiceHistoryRead(
                service_id=row.id,
                service_name=row.name,
                completed_visits=int(row.completed_visits or 0),
                first_completed_at=row.first_completed_at,
                last_completed_at=row.last_completed_at,
            )
            for row in service_rows
        ],
        recent_appointments=[
            PatientHistoryAppointmentRead(
                appointment_id=appointment.id,
                status=appointment.status,
                start_at=appointment.start_at,
                end_at=appointment.end_at,
                service_name=service_name,
                branch_name=branch_name,
                doctor_name=" ".join(part for part in (doctor_first, doctor_last) if part).strip() or "Doctor",
                price_minor=appointment.price_minor,
                currency=appointment.currency,
                net_paid_minor=net_by_appointment.get(appointment.id, 0),
            )
            for appointment, service_name, branch_name, doctor_first, doctor_last in recent_rows
        ],
    )


def historical_analytics(db: Session, *, workspace_id: UUID, top_services_limit: int = 10) -> HistoricalAnalyticsRead:
    total_patients = int(db.scalar(select(func.count(Patient.id)).where(Patient.workspace_id == workspace_id)) or 0)
    appointment_counts = db.execute(
        select(
            func.count(Appointment.id).label("total"),
            func.count(Appointment.id).filter(Appointment.status == "completed").label("completed"),
            func.min(Appointment.start_at).label("first_at"),
            func.max(Appointment.start_at).label("last_at"),
        ).where(Appointment.workspace_id == workspace_id, Appointment.status != "rescheduled")
    ).one()

    completed_by_patient = (
        select(Appointment.patient_id.label("patient_id"), func.count(Appointment.id).label("completed_count"))
        .where(Appointment.workspace_id == workspace_id, Appointment.status == "completed")
        .group_by(Appointment.patient_id)
        .subquery()
    )
    repeat_patients = int(db.scalar(select(func.count()).select_from(completed_by_patient).where(completed_by_patient.c.completed_count >= 2)) or 0)

    patient_bounds = db.execute(
        select(
            func.min(func.coalesce(Patient.source_created_at, Patient.created_at)),
            func.max(func.coalesce(Patient.source_created_at, Patient.created_at)),
        ).where(Patient.workspace_id == workspace_id)
    ).one()
    patient_first, patient_last = patient_bounds
    payment_bounds = db.execute(
        select(func.min(PaymentTransaction.created_at), func.max(PaymentTransaction.created_at)).where(PaymentTransaction.workspace_id == workspace_id)
    ).one()
    start_values = [patient_first, appointment_counts.first_at, payment_bounds[0]]
    end_values = [patient_last, appointment_counts.last_at, payment_bounds[1]]
    data_start = min((value for value in start_values if value is not None), default=None)
    data_end = max((value for value in end_values if value is not None), default=data_start)

    service_rows = db.execute(
        select(
            Service.id,
            Service.name,
            func.count(Appointment.id).label("completed"),
            func.count(func.distinct(Appointment.patient_id)).label("patients"),
        )
        .join(Appointment, (Appointment.workspace_id == Service.workspace_id) & (Appointment.service_id == Service.id))
        .where(Appointment.workspace_id == workspace_id, Appointment.status == "completed")
        .group_by(Service.id, Service.name)
        .order_by(func.count(Appointment.id).desc(), Service.name)
        .limit(max(1, min(int(top_services_limit), 25)))
    ).all()

    return HistoricalAnalyticsRead(
        data_start_at=data_start,
        data_end_at=data_end,
        total_patients=total_patients,
        repeat_patients=repeat_patients,
        repeat_patient_rate_percent=_percent(repeat_patients, total_patients),
        total_appointments=int(appointment_counts.total or 0),
        completed_appointments=int(appointment_counts.completed or 0),
        money=_payment_money_rows(db, workspace_id=workspace_id),
        top_services=[
            HistoricalAnalyticsServiceRead(
                service_id=row.id,
                service_name=row.name,
                completed_appointments=int(row.completed or 0),
                unique_patients=int(row.patients or 0),
            )
            for row in service_rows
        ],
    )
