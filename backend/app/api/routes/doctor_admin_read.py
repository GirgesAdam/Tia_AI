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
from app.models.branch import Branch
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
    is_primary: bool = False


class DoctorAdminHour(BaseModel):
    weekday: int
    start_time: str
    end_time: str


class DoctorAdminSchedule(BaseModel):
    branch_id: UUID
    branch_name: str
    working_hours: list[DoctorAdminHour] = Field(default_factory=list)


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
    branches: list[DoctorAdminNamedLink]
    services: list[DoctorAdminNamedLink]
    schedules: list[DoctorAdminSchedule]

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

    branch_rows = list(
        db.execute(
            select(DoctorBranch, Branch)
            .join(
                Branch,
                (Branch.workspace_id == DoctorBranch.workspace_id)
                & (Branch.id == DoctorBranch.branch_id),
            )
            .where(
                DoctorBranch.workspace_id == workspace_id,
                DoctorBranch.doctor_id.in_(doctor_ids),
                DoctorBranch.is_active.is_(True),
                Branch.is_active.is_(True),
            )
        )
    )
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
    hour_rows = list(
        db.scalars(
            select(DoctorWorkingHour)
            .where(
                DoctorWorkingHour.workspace_id == workspace_id,
                DoctorWorkingHour.doctor_id.in_(doctor_ids),
            )
            .order_by(
                DoctorWorkingHour.doctor_id,
                DoctorWorkingHour.branch_id,
                DoctorWorkingHour.weekday,
                DoctorWorkingHour.start_time,
            )
        )
    )

    branches_by_doctor: dict[UUID, list[DoctorAdminNamedLink]] = defaultdict(list)
    branch_name_by_id: dict[UUID, str] = {}
    for assignment, branch in branch_rows:
        branch_name_by_id[branch.id] = branch.name
        branches_by_doctor[assignment.doctor_id].append(
            DoctorAdminNamedLink(
                id=branch.id,
                name=branch.name,
                is_primary=assignment.is_primary,
            )
        )

    services_by_doctor: dict[UUID, list[DoctorAdminNamedLink]] = defaultdict(list)
    for assignment, service in service_rows:
        services_by_doctor[assignment.doctor_id].append(
            DoctorAdminNamedLink(id=service.id, name=service.name)
        )

    hours_by_pair: dict[tuple[UUID, UUID], list[DoctorAdminHour]] = defaultdict(list)
    for hour in hour_rows:
        hours_by_pair[(hour.doctor_id, hour.branch_id)].append(
            DoctorAdminHour(
                weekday=hour.weekday,
                start_time=hour.start_time.strftime("%H:%M"),
                end_time=hour.end_time.strftime("%H:%M"),
            )
        )

    result: list[DoctorAdminListItem] = []
    for doctor, staff in rows:
        branches = sorted(
            branches_by_doctor.get(doctor.id, []),
            key=lambda item: (not item.is_primary, item.name),
        )
        schedules = [
            DoctorAdminSchedule(
                branch_id=branch.id,
                branch_name=branch.name,
                working_hours=hours_by_pair.get((doctor.id, branch.id), []),
            )
            for branch in branches
        ]
        result.append(
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
                branches=branches,
                services=sorted(services_by_doctor.get(doctor.id, []), key=lambda item: item.name),
                schedules=schedules,
            )
        )
    return result
