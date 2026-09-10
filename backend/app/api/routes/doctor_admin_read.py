from __future__ import annotations

from collections import defaultdict
from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.dependencies.security import WorkspaceAccess, get_workspace_admin
from app.database.session import get_db
from app.models.doctor import Doctor
from app.models.doctor_branch import DoctorBranch
from app.models.doctor_service import DoctorService
from app.models.service import Service
from app.models.staff import Staff
from app.models.working_hours import DoctorWorkingHour

router = APIRouter()


class DoctorAdminNamedLink(BaseModel):
    id: UUID
    name: str


class DoctorAdminHour(BaseModel):
    weekday: int
    start_time: str
    end_time: str


class DoctorAdminListItem(BaseModel):
    id: UUID
    staff_id: UUID
    name: str
    first_name: str
    last_name: str
    specialization: str | None
    phone: str | None
    email: str | None
    booking_enabled: bool
    is_active: bool
    services: list[DoctorAdminNamedLink]
    working_hours: list[DoctorAdminHour] = Field(default_factory=list)

    model_config = ConfigDict(from_attributes=True)


@router.get("/doctor-admin", response_model=list[DoctorAdminListItem])
def list_doctors_for_admin(
    access: Annotated[WorkspaceAccess, Depends(get_workspace_admin)],
    db: Annotated[Session, Depends(get_db)],
) -> list[DoctorAdminListItem]:
    workspace_id = access.workspace.id
    rows = list(
        db.execute(
            select(Doctor, Staff)
            .join(
                Staff,
                (Staff.workspace_id == Doctor.workspace_id) & (Staff.id == Doctor.staff_id),
            )
            .where(
                Doctor.workspace_id == workspace_id,
                Doctor.is_active.is_(True),
            )
            .order_by(Staff.first_name, Staff.last_name)
        )
    )
    doctor_ids = [doctor.id for doctor, _staff in rows]
    if not doctor_ids:
        return []

    service_rows = list(
        db.execute(
            select(DoctorService, Service)
            .join(
                Service,
                (Service.workspace_id == DoctorService.workspace_id)
                & (Service.id == DoctorService.service_id),
            )
            .where(
                DoctorService.workspace_id == workspace_id,
                DoctorService.doctor_id.in_(doctor_ids),
                DoctorService.is_active.is_(True),
                Service.is_active.is_(True),
            )
        )
    )
    assignments = list(
        db.scalars(
            select(DoctorBranch)
            .where(
                DoctorBranch.workspace_id == workspace_id,
                DoctorBranch.doctor_id.in_(doctor_ids),
                DoctorBranch.is_active.is_(True),
            )
            .order_by(
                DoctorBranch.doctor_id,
                DoctorBranch.is_primary.desc(),
                DoctorBranch.created_at,
            )
        )
    )
    primary_branch_by_doctor: dict[UUID, UUID] = {}
    for assignment in assignments:
        primary_branch_by_doctor.setdefault(assignment.doctor_id, assignment.branch_id)

    selected_pairs = [
        (doctor_id, branch_id)
        for doctor_id, branch_id in primary_branch_by_doctor.items()
    ]
    hour_rows: list[DoctorWorkingHour] = []
    if selected_pairs:
        candidate_hours = list(
            db.scalars(
                select(DoctorWorkingHour)
                .where(
                    DoctorWorkingHour.workspace_id == workspace_id,
                    DoctorWorkingHour.doctor_id.in_(doctor_ids),
                )
                .order_by(
                    DoctorWorkingHour.doctor_id,
                    DoctorWorkingHour.weekday,
                    DoctorWorkingHour.start_time,
                )
            )
        )
        hour_rows = [
            row
            for row in candidate_hours
            if primary_branch_by_doctor.get(row.doctor_id) == row.branch_id
        ]

    services_by_doctor: dict[UUID, list[DoctorAdminNamedLink]] = defaultdict(list)
    for assignment, service in service_rows:
        services_by_doctor[assignment.doctor_id].append(
            DoctorAdminNamedLink(id=service.id, name=service.name)
        )

    hours_by_doctor: dict[UUID, list[DoctorAdminHour]] = defaultdict(list)
    for hour in hour_rows:
        hours_by_doctor[hour.doctor_id].append(
            DoctorAdminHour(
                weekday=hour.weekday,
                start_time=hour.start_time.strftime("%H:%M"),
                end_time=hour.end_time.strftime("%H:%M"),
            )
        )

    return [
        DoctorAdminListItem(
            id=doctor.id,
            staff_id=doctor.staff_id,
            name=f"{staff.first_name} {staff.last_name}".strip() or "دكتور",
            first_name=staff.first_name,
            last_name=staff.last_name,
            specialization=doctor.specialization,
            phone=staff.phone,
            email=staff.email,
            booking_enabled=doctor.booking_enabled,
            is_active=doctor.is_active,
            services=sorted(services_by_doctor.get(doctor.id, []), key=lambda item: item.name),
            working_hours=hours_by_doctor.get(doctor.id, []),
        )
        for doctor, staff in rows
    ]
