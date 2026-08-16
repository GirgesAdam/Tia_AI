from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Response, status
from sqlalchemy import delete, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.api.dependencies.security import get_current_workspace, get_manageable_workspace
from app.database.session import get_db
from app.models.booking_settings import BookingSettings
from app.models.branch import Branch
from app.models.doctor import Doctor
from app.models.doctor_branch import DoctorBranch
from app.models.doctor_service import DoctorService
from app.models.service import Service
from app.models.staff import Staff
from app.models.working_hours import BranchWorkingHour, DoctorWorkingHour
from app.models.workspace import Workspace
from app.schemas.clinic import (
    BookingSettingsRead,
    BookingSettingsUpsert,
    BranchCreate,
    BranchRead,
    BranchUpdate,
    BranchWorkingHourRead,
    DoctorBranchAssignment,
    DoctorBranchRead,
    DoctorCreate,
    DoctorRead,
    DoctorServiceAssignment,
    DoctorServiceRead,
    DoctorUpdate,
    DoctorWorkingHourRead,
    ServiceCreate,
    ServiceRead,
    ServiceUpdate,
    StaffCreate,
    StaffRead,
    StaffUpdate,
    WorkingHoursReplace,
)

router = APIRouter()


def not_found(entity: str) -> HTTPException:
    return HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"{entity} not found.")


def commit_or_conflict(db: Session, detail: str) -> None:
    try:
        db.commit()
    except IntegrityError as exc:
        db.rollback()
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=detail) from exc


@router.post("/branches", response_model=BranchRead, status_code=status.HTTP_201_CREATED)
def create_branch(
    payload: BranchCreate,
    workspace: Workspace = Depends(get_manageable_workspace),
    db: Session = Depends(get_db),
) -> Branch:
    branch = Branch(workspace_id=workspace.id, **payload.model_dump())
    db.add(branch)
    commit_or_conflict(db, "Branch code already exists in this workspace.")
    db.refresh(branch)
    return branch


@router.get("/branches", response_model=list[BranchRead])
def list_branches(
    workspace: Workspace = Depends(get_current_workspace),
    db: Session = Depends(get_db),
) -> list[Branch]:
    return list(db.scalars(select(Branch).where(Branch.workspace_id == workspace.id).order_by(Branch.name)))


@router.patch("/branches/{branch_id}", response_model=BranchRead)
def update_branch(
    branch_id: UUID,
    payload: BranchUpdate,
    workspace: Workspace = Depends(get_manageable_workspace),
    db: Session = Depends(get_db),
) -> Branch:
    branch = db.scalar(select(Branch).where(Branch.id == branch_id, Branch.workspace_id == workspace.id))
    if branch is None:
        raise not_found("Branch")
    for key, value in payload.model_dump(exclude_unset=True).items():
        setattr(branch, key, value)
    commit_or_conflict(db, "Could not update branch.")
    db.refresh(branch)
    return branch


@router.post("/staff", response_model=StaffRead, status_code=status.HTTP_201_CREATED)
def create_staff(
    payload: StaffCreate,
    workspace: Workspace = Depends(get_manageable_workspace),
    db: Session = Depends(get_db),
) -> Staff:
    staff = Staff(workspace_id=workspace.id, **payload.model_dump())
    db.add(staff)
    commit_or_conflict(db, "Staff email is already used in this workspace or user reference is invalid.")
    db.refresh(staff)
    return staff


@router.get("/staff", response_model=list[StaffRead])
def list_staff(
    workspace: Workspace = Depends(get_current_workspace),
    db: Session = Depends(get_db),
) -> list[Staff]:
    return list(db.scalars(select(Staff).where(Staff.workspace_id == workspace.id).order_by(Staff.first_name, Staff.last_name)))


@router.patch("/staff/{staff_id}", response_model=StaffRead)
def update_staff(
    staff_id: UUID,
    payload: StaffUpdate,
    workspace: Workspace = Depends(get_manageable_workspace),
    db: Session = Depends(get_db),
) -> Staff:
    staff = db.scalar(select(Staff).where(Staff.id == staff_id, Staff.workspace_id == workspace.id))
    if staff is None:
        raise not_found("Staff member")
    for key, value in payload.model_dump(exclude_unset=True).items():
        setattr(staff, key, value)
    commit_or_conflict(db, "Could not update staff member.")
    db.refresh(staff)
    return staff


@router.post("/doctors", response_model=DoctorRead, status_code=status.HTTP_201_CREATED)
def create_doctor(
    payload: DoctorCreate,
    workspace: Workspace = Depends(get_manageable_workspace),
    db: Session = Depends(get_db),
) -> Doctor:
    staff = db.scalar(select(Staff).where(Staff.id == payload.staff_id, Staff.workspace_id == workspace.id))
    if staff is None:
        raise not_found("Staff member")
    doctor = Doctor(workspace_id=workspace.id, **payload.model_dump())
    db.add(doctor)
    commit_or_conflict(db, "This staff member already has a doctor profile.")
    db.refresh(doctor)
    return doctor


@router.get("/doctors", response_model=list[DoctorRead])
def list_doctors(
    workspace: Workspace = Depends(get_current_workspace),
    db: Session = Depends(get_db),
) -> list[Doctor]:
    return list(db.scalars(select(Doctor).where(Doctor.workspace_id == workspace.id).order_by(Doctor.created_at)))


@router.patch("/doctors/{doctor_id}", response_model=DoctorRead)
def update_doctor(
    doctor_id: UUID,
    payload: DoctorUpdate,
    workspace: Workspace = Depends(get_manageable_workspace),
    db: Session = Depends(get_db),
) -> Doctor:
    doctor = db.scalar(select(Doctor).where(Doctor.id == doctor_id, Doctor.workspace_id == workspace.id))
    if doctor is None:
        raise not_found("Doctor")
    for key, value in payload.model_dump(exclude_unset=True).items():
        setattr(doctor, key, value)
    db.commit()
    db.refresh(doctor)
    return doctor


@router.put("/doctors/{doctor_id}/branches/{branch_id}", response_model=DoctorBranchRead)
def assign_doctor_to_branch(
    doctor_id: UUID,
    branch_id: UUID,
    payload: DoctorBranchAssignment,
    workspace: Workspace = Depends(get_manageable_workspace),
    db: Session = Depends(get_db),
) -> DoctorBranch:
    doctor = db.scalar(select(Doctor).where(Doctor.id == doctor_id, Doctor.workspace_id == workspace.id))
    branch = db.scalar(select(Branch).where(Branch.id == branch_id, Branch.workspace_id == workspace.id))
    if doctor is None:
        raise not_found("Doctor")
    if branch is None:
        raise not_found("Branch")

    assignment = db.scalar(
        select(DoctorBranch).where(
            DoctorBranch.workspace_id == workspace.id,
            DoctorBranch.doctor_id == doctor_id,
            DoctorBranch.branch_id == branch_id,
        )
    )
    if assignment is None:
        assignment = DoctorBranch(
            workspace_id=workspace.id,
            doctor_id=doctor_id,
            branch_id=branch_id,
            **payload.model_dump(),
        )
        db.add(assignment)
    else:
        assignment.is_primary = payload.is_primary
        assignment.is_active = payload.is_active

    if payload.is_primary:
        other_primary = list(
            db.scalars(
                select(DoctorBranch).where(
                    DoctorBranch.workspace_id == workspace.id,
                    DoctorBranch.doctor_id == doctor_id,
                    DoctorBranch.branch_id != branch_id,
                    DoctorBranch.is_primary.is_(True),
                )
            )
        )
        for item in other_primary:
            item.is_primary = False

    db.commit()
    db.refresh(assignment)
    return assignment


@router.post("/services", response_model=ServiceRead, status_code=status.HTTP_201_CREATED)
def create_service(
    payload: ServiceCreate,
    workspace: Workspace = Depends(get_manageable_workspace),
    db: Session = Depends(get_db),
) -> Service:
    service = Service(workspace_id=workspace.id, **payload.model_dump())
    db.add(service)
    commit_or_conflict(db, "Service slug already exists in this workspace.")
    db.refresh(service)
    return service


@router.get("/services", response_model=list[ServiceRead])
def list_services(
    workspace: Workspace = Depends(get_current_workspace),
    db: Session = Depends(get_db),
) -> list[Service]:
    return list(db.scalars(select(Service).where(Service.workspace_id == workspace.id).order_by(Service.name)))


@router.patch("/services/{service_id}", response_model=ServiceRead)
def update_service(
    service_id: UUID,
    payload: ServiceUpdate,
    workspace: Workspace = Depends(get_manageable_workspace),
    db: Session = Depends(get_db),
) -> Service:
    service = db.scalar(select(Service).where(Service.id == service_id, Service.workspace_id == workspace.id))
    if service is None:
        raise not_found("Service")
    for key, value in payload.model_dump(exclude_unset=True).items():
        setattr(service, key, value)
    db.commit()
    db.refresh(service)
    return service


@router.put("/doctors/{doctor_id}/services/{service_id}", response_model=DoctorServiceRead)
def assign_service_to_doctor(
    doctor_id: UUID,
    service_id: UUID,
    payload: DoctorServiceAssignment,
    workspace: Workspace = Depends(get_manageable_workspace),
    db: Session = Depends(get_db),
) -> DoctorService:
    doctor = db.scalar(select(Doctor).where(Doctor.id == doctor_id, Doctor.workspace_id == workspace.id))
    service = db.scalar(select(Service).where(Service.id == service_id, Service.workspace_id == workspace.id))
    if doctor is None:
        raise not_found("Doctor")
    if service is None:
        raise not_found("Service")

    assignment = db.scalar(
        select(DoctorService).where(
            DoctorService.workspace_id == workspace.id,
            DoctorService.doctor_id == doctor_id,
            DoctorService.service_id == service_id,
        )
    )
    if assignment is None:
        assignment = DoctorService(
            workspace_id=workspace.id,
            doctor_id=doctor_id,
            service_id=service_id,
            **payload.model_dump(),
        )
        db.add(assignment)
    else:
        for key, value in payload.model_dump().items():
            setattr(assignment, key, value)

    db.commit()
    db.refresh(assignment)
    return assignment


@router.put("/branches/{branch_id}/working-hours", response_model=list[BranchWorkingHourRead])
def replace_branch_working_hours(
    branch_id: UUID,
    payload: WorkingHoursReplace,
    workspace: Workspace = Depends(get_manageable_workspace),
    db: Session = Depends(get_db),
) -> list[BranchWorkingHour]:
    branch = db.scalar(select(Branch).where(Branch.id == branch_id, Branch.workspace_id == workspace.id))
    if branch is None:
        raise not_found("Branch")

    db.execute(
        delete(BranchWorkingHour).where(
            BranchWorkingHour.workspace_id == workspace.id,
            BranchWorkingHour.branch_id == branch_id,
        )
    )
    rows = [
        BranchWorkingHour(workspace_id=workspace.id, branch_id=branch_id, **item.model_dump())
        for item in payload.intervals
    ]
    db.add_all(rows)
    commit_or_conflict(db, "Working-hour intervals must be unique and valid.")
    return rows


@router.put(
    "/doctors/{doctor_id}/branches/{branch_id}/working-hours",
    response_model=list[DoctorWorkingHourRead],
)
def replace_doctor_working_hours(
    doctor_id: UUID,
    branch_id: UUID,
    payload: WorkingHoursReplace,
    workspace: Workspace = Depends(get_manageable_workspace),
    db: Session = Depends(get_db),
) -> list[DoctorWorkingHour]:
    assignment = db.scalar(
        select(DoctorBranch).where(
            DoctorBranch.workspace_id == workspace.id,
            DoctorBranch.doctor_id == doctor_id,
            DoctorBranch.branch_id == branch_id,
            DoctorBranch.is_active.is_(True),
        )
    )
    if assignment is None:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Doctor must be actively assigned to the branch before setting working hours.",
        )

    db.execute(
        delete(DoctorWorkingHour).where(
            DoctorWorkingHour.workspace_id == workspace.id,
            DoctorWorkingHour.doctor_id == doctor_id,
            DoctorWorkingHour.branch_id == branch_id,
        )
    )
    rows = [
        DoctorWorkingHour(
            workspace_id=workspace.id,
            doctor_id=doctor_id,
            branch_id=branch_id,
            **item.model_dump(),
        )
        for item in payload.intervals
    ]
    db.add_all(rows)
    commit_or_conflict(db, "Doctor working-hour intervals must be unique and valid.")
    return rows


@router.get("/booking-settings", response_model=BookingSettingsRead)
def get_booking_settings(
    workspace: Workspace = Depends(get_current_workspace),
    db: Session = Depends(get_db),
) -> BookingSettings:
    settings = db.scalar(select(BookingSettings).where(BookingSettings.workspace_id == workspace.id))
    if settings is None:
        raise not_found("Booking settings")
    return settings


@router.put("/booking-settings", response_model=BookingSettingsRead)
def upsert_booking_settings(
    payload: BookingSettingsUpsert,
    workspace: Workspace = Depends(get_manageable_workspace),
    db: Session = Depends(get_db),
) -> BookingSettings:
    settings = db.scalar(select(BookingSettings).where(BookingSettings.workspace_id == workspace.id))
    if settings is None:
        settings = BookingSettings(workspace_id=workspace.id, **payload.model_dump())
        db.add(settings)
    else:
        for key, value in payload.model_dump().items():
            setattr(settings, key, value)
    db.commit()
    db.refresh(settings)
    return settings
