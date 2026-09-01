from __future__ import annotations

import hashlib
import json
from collections import defaultdict
from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.models.appointment import Appointment
from app.models.booking_settings import BookingSettings
from app.models.branch import Branch
from app.models.doctor import Doctor
from app.models.doctor_branch import DoctorBranch
from app.models.doctor_service import DoctorService
from app.models.patient import Patient
from app.models.service import Service
from app.models.staff import Staff
from app.models.working_hours import BranchWorkingHour, DoctorWorkingHour
from app.models.workspace import Workspace
from app.schemas.agent_knowledge import (
    AgentKnowledgeSnapshot,
    KnowledgeAppointment,
    KnowledgeBranch,
    KnowledgeDoctor,
    KnowledgeDoctorSchedule,
    KnowledgeHour,
    KnowledgeNamedLink,
    KnowledgePatient,
    KnowledgeService,
)


def build_agent_knowledge_snapshot(db: Session, workspace: Workspace) -> AgentKnowledgeSnapshot:
    wid = workspace.id
    branches = list(db.scalars(select(Branch).where(Branch.workspace_id == wid).order_by(Branch.name)))
    services = list(db.scalars(select(Service).where(Service.workspace_id == wid).order_by(Service.name)))
    staff = list(db.scalars(select(Staff).where(Staff.workspace_id == wid)))
    doctors = list(db.scalars(select(Doctor).where(Doctor.workspace_id == wid).order_by(Doctor.created_at)))
    doctor_branches = list(db.scalars(select(DoctorBranch).where(DoctorBranch.workspace_id == wid)))
    doctor_services = list(db.scalars(select(DoctorService).where(DoctorService.workspace_id == wid)))
    branch_hours = list(db.scalars(select(BranchWorkingHour).where(BranchWorkingHour.workspace_id == wid)))
    doctor_hours = list(db.scalars(select(DoctorWorkingHour).where(DoctorWorkingHour.workspace_id == wid)))
    settings = db.scalar(select(BookingSettings).where(BookingSettings.workspace_id == wid))
    patients = list(db.scalars(select(Patient).where(Patient.workspace_id == wid).order_by(Patient.created_at)))

    branch_by_id = {row.id: row for row in branches}
    service_by_id = {row.id: row for row in services}
    staff_by_id = {row.id: row for row in staff}
    doctor_by_id = {row.id: row for row in doctors}

    branch_hours_by_id: dict[UUID, list[KnowledgeHour]] = defaultdict(list)
    for row in branch_hours:
        branch_hours_by_id[row.branch_id].append(KnowledgeHour(weekday=row.weekday, start_time=row.start_time, end_time=row.end_time))
    for values in branch_hours_by_id.values():
        values.sort(key=lambda item: (item.weekday, item.start_time))

    branch_links_by_doctor: dict[UUID, list[KnowledgeNamedLink]] = defaultdict(list)
    for row in doctor_branches:
        if not row.is_active or row.branch_id not in branch_by_id:
            continue
        branch_links_by_doctor[row.doctor_id].append(
            KnowledgeNamedLink(id=row.branch_id, name=branch_by_id[row.branch_id].name, is_primary=row.is_primary)
        )

    service_links_by_doctor: dict[UUID, list[KnowledgeNamedLink]] = defaultdict(list)
    for row in doctor_services:
        if not row.is_active or row.service_id not in service_by_id:
            continue
        service_links_by_doctor[row.doctor_id].append(
            KnowledgeNamedLink(id=row.service_id, name=service_by_id[row.service_id].name)
        )

    doctor_hours_by_pair: dict[tuple[UUID, UUID], list[KnowledgeHour]] = defaultdict(list)
    for row in doctor_hours:
        doctor_hours_by_pair[(row.doctor_id, row.branch_id)].append(
            KnowledgeHour(weekday=row.weekday, start_time=row.start_time, end_time=row.end_time)
        )
    for values in doctor_hours_by_pair.values():
        values.sort(key=lambda item: (item.weekday, item.start_time))

    doctor_rows: list[KnowledgeDoctor] = []
    for doctor in doctors:
        member = staff_by_id.get(doctor.staff_id)
        first = member.first_name if member else ""
        last = member.last_name if member else ""
        links = sorted(branch_links_by_doctor[doctor.id], key=lambda item: (not item.is_primary, item.name))
        schedules = [
            KnowledgeDoctorSchedule(
                branch_id=link.id,
                branch_name=link.name,
                working_hours=doctor_hours_by_pair.get((doctor.id, link.id), []),
            )
            for link in links
        ]
        doctor_rows.append(
            KnowledgeDoctor(
                id=doctor.id,
                staff_id=doctor.staff_id,
                name=f"{first} {last}".strip() or "دكتور",
                first_name=first,
                last_name=last,
                specialization=doctor.specialization,
                phone=member.phone if member else None,
                email=member.email if member else None,
                booking_enabled=doctor.booking_enabled,
                is_active=doctor.is_active,
                branches=links,
                services=sorted(service_links_by_doctor[doctor.id], key=lambda item: item.name),
                schedules=schedules,
            )
        )

    appointment_stmt = (
        select(Appointment)
        .where(Appointment.workspace_id == wid)
        .order_by(Appointment.start_at.desc())
    )
    appointments = list(db.scalars(appointment_stmt))
    patient_by_id = {row.id: row for row in patients}

    appointment_rows: list[KnowledgeAppointment] = []
    for row in appointments:
        patient = patient_by_id.get(row.patient_id)
        branch = branch_by_id.get(row.branch_id)
        service = service_by_id.get(row.service_id)
        doctor = doctor_by_id.get(row.doctor_id)
        member = staff_by_id.get(doctor.staff_id) if doctor else None
        appointment_rows.append(
            KnowledgeAppointment(
                id=row.id,
                patient_name=(f"{patient.first_name} {patient.last_name or ''}".strip() if patient else "—"),
                patient_phone=patient.phone if patient else None,
                service_name=service.name if service else "—",
                branch_name=branch.name if branch else "—",
                doctor_name=(f"{member.first_name} {member.last_name}".strip() if member else "—"),
                start_at=row.start_at,
                end_at=row.end_at,
                status=row.status,
                payment_status=getattr(row, "payment_status", "unknown"),
                amount_paid_minor=getattr(row, "amount_paid_minor", None),
                payment_method=getattr(row, "payment_method", "unknown"),
                price_minor=row.price_minor,
                currency=row.currency,
            )
        )

    return AgentKnowledgeSnapshot(
        workspace_id=wid,
        workspace_name=workspace.name,
        workspace_timezone=workspace.timezone,
        branches=[
            KnowledgeBranch(
                id=row.id,
                name=row.name,
                code=row.code,
                city=row.city,
                address_line1=row.address_line1,
                phone=row.phone,
                timezone=row.timezone,
                is_active=row.is_active,
                working_hours=branch_hours_by_id.get(row.id, []),
            )
            for row in branches
        ],
        services=[
            KnowledgeService(
                id=row.id,
                name=row.name,
                slug=row.slug,
                category=row.category,
                description=row.description,
                duration_minutes=row.duration_minutes,
                price_minor=row.price_minor,
                currency=row.currency,
                requires_medical_review=row.requires_medical_review,
                is_active=row.is_active,
            )
            for row in services
        ],
        doctors=doctor_rows,
        booking_settings=settings,
        patients=[
            KnowledgePatient(
                id=row.id,
                name=f"{row.first_name} {row.last_name or ''}".strip(),
                phone=row.phone,
                status=row.status,
                source=row.source,
            )
            for row in patients
        ],
        appointments=appointment_rows,
        patient_count=len(patients),
        appointment_count=len(appointments),
    )


def agent_knowledge_configuration_fingerprint(snapshot: AgentKnowledgeSnapshot) -> str:
    data = snapshot.model_dump(mode="json", exclude={"patients", "appointments", "patient_count", "appointment_count"})
    payload = json.dumps(data, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()
