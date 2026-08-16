from __future__ import annotations

from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError, ProgrammingError
from sqlalchemy.orm import Session

from app.api.dependencies.security import (
    WorkspaceAccess,
    get_current_user,
    get_workspace_admin,
    get_workspace_reader,
)
from app.database.session import get_db
from app.agents.llm_runtime import LLMProviderError
from app.agents.model_provider import LLMConfigurationError
from app.agents.structured_output import StructuredOutputError
from app.models.booking_settings import BookingSettings
from app.models.branch import Branch
from app.models.doctor import Doctor
from app.models.doctor_branch import DoctorBranch
from app.models.doctor_service import DoctorService
from app.models.service import Service
from app.models.staff import Staff
from app.models.user import User
from app.models.working_hours import BranchWorkingHour, DoctorWorkingHour
from app.models.workspace import Workspace
from app.models.workspace_member import WorkspaceMember
from app.models.onboarding_ai_session import OnboardingAISession
from app.schemas.clinic import DoctorRead
from app.schemas.onboarding import (
    ClinicSetupSnapshot,
    DoctorSetupRead,
    SetupReadiness,
    WorkspaceCreate,
    WorkspaceCreated,
)

from app.schemas.onboarding_ai import (
    OnboardingAIChatRequest,
    OnboardingAICommandRequest,
    OnboardingAIResponse,
    OnboardingAISessionRead,
    OnboardingPlan,
)
from app.services.ai_onboarding import (
    OnboardingExecutionError,
    OnboardingPlanValidationError,
    OnboardingSessionConflictError,
    cancel_session,
    execute_plan,
    process_onboarding_message,
)

router = APIRouter()


@router.post("/workspaces", response_model=WorkspaceCreated, status_code=status.HTTP_201_CREATED)
def create_workspace(
    payload: WorkspaceCreate,
    user: Annotated[User, Depends(get_current_user)],
    db: Annotated[Session, Depends(get_db)],
) -> WorkspaceCreated:
    if db.scalar(select(Workspace.id).where(Workspace.slug == payload.slug)) is not None:
        raise HTTPException(status_code=409, detail="Workspace slug is already in use.")

    workspace = Workspace(
        name=payload.name,
        slug=payload.slug,
        timezone=payload.timezone,
        is_active=True,
    )
    db.add(workspace)
    db.flush()
    membership = WorkspaceMember(
        workspace_id=workspace.id,
        user_id=user.id,
        role="admin",
        is_active=True,
    )
    db.add(membership)
    try:
        db.commit()
    except IntegrityError as exc:
        db.rollback()
        raise HTTPException(status_code=409, detail="Could not create workspace.") from exc

    return WorkspaceCreated(
        workspace_id=workspace.id,
        workspace_name=workspace.name,
        workspace_slug=workspace.slug,
        role="admin",
    )


def _readiness(
    *,
    branches: list[Branch],
    services: list[Service],
    doctors: list[Doctor],
    doctor_branches: list[DoctorBranch],
    doctor_services: list[DoctorService],
    branch_hours: list[BranchWorkingHour],
    doctor_hours: list[DoctorWorkingHour],
    booking_settings: BookingSettings | None,
) -> SetupReadiness:
    active_branch_ids = {b.id for b in branches if b.is_active}
    active_service_ids = {s.id for s in services if s.is_active}
    bookable_doctor_ids = {d.id for d in doctors if d.is_active and d.booking_enabled}

    checks = {
        "branch": bool(active_branch_ids),
        "branch_hours": any(h.branch_id in active_branch_ids for h in branch_hours),
        "service": bool(active_service_ids),
        "doctor": bool(bookable_doctor_ids),
        "doctor_branch": any(
            row.doctor_id in bookable_doctor_ids and row.branch_id in active_branch_ids and row.is_active
            for row in doctor_branches
        ),
        "doctor_service": any(
            row.doctor_id in bookable_doctor_ids and row.service_id in active_service_ids and row.is_active
            for row in doctor_services
        ),
        "doctor_hours": any(row.doctor_id in bookable_doctor_ids for row in doctor_hours),
        "booking_settings": booking_settings is not None,
    }
    labels = {
        "branch": "أضف فرع نشط",
        "branch_hours": "حدد مواعيد عمل الفرع",
        "service": "أضف خدمة نشطة",
        "doctor": "أضف دكتور متاح للحجز",
        "doctor_branch": "اربط الدكتور بفرع",
        "doctor_service": "اربط الدكتور بخدمة",
        "doctor_hours": "حدد مواعيد عمل الدكتور",
        "booking_settings": "احفظ إعدادات الحجز",
    }
    completed = sum(1 for value in checks.values() if value)
    total = len(checks)
    return SetupReadiness(
        ready=completed == total,
        progress_percent=round(completed / total * 100),
        completed_steps=completed,
        total_steps=total,
        checks=checks,
        missing=[labels[key] for key, value in checks.items() if not value],
    )


@router.get("/setup", response_model=ClinicSetupSnapshot)
def clinic_setup_snapshot(
    access: Annotated[WorkspaceAccess, Depends(get_workspace_reader)],
    db: Annotated[Session, Depends(get_db)],
) -> ClinicSetupSnapshot:
    wid = access.workspace.id
    branches = list(db.scalars(select(Branch).where(Branch.workspace_id == wid).order_by(Branch.name)))
    services = list(db.scalars(select(Service).where(Service.workspace_id == wid).order_by(Service.name)))
    staff = list(db.scalars(select(Staff).where(Staff.workspace_id == wid).order_by(Staff.first_name, Staff.last_name)))
    doctors = list(db.scalars(select(Doctor).where(Doctor.workspace_id == wid).order_by(Doctor.created_at)))
    doctor_branches = list(db.scalars(select(DoctorBranch).where(DoctorBranch.workspace_id == wid)))
    doctor_services = list(db.scalars(select(DoctorService).where(DoctorService.workspace_id == wid)))
    branch_hours = list(db.scalars(select(BranchWorkingHour).where(BranchWorkingHour.workspace_id == wid).order_by(BranchWorkingHour.weekday, BranchWorkingHour.start_time)))
    doctor_hours = list(db.scalars(select(DoctorWorkingHour).where(DoctorWorkingHour.workspace_id == wid).order_by(DoctorWorkingHour.weekday, DoctorWorkingHour.start_time)))
    settings = db.scalar(select(BookingSettings).where(BookingSettings.workspace_id == wid))

    staff_by_id = {row.id: row for row in staff}
    doctor_rows = []
    for doctor in doctors:
        member = staff_by_id.get(doctor.staff_id)
        doctor_rows.append(
            DoctorSetupRead(
                **DoctorRead.model_validate(doctor).model_dump(),
                staff_name=(
                    f"{member.first_name} {member.last_name}".strip()
                    if member else "دكتور"
                ),
            )
        )

    return ClinicSetupSnapshot(
        workspace_id=wid,
        workspace_name=access.workspace.name,
        workspace_slug=access.workspace.slug,
        workspace_timezone=access.workspace.timezone,
        branches=branches,
        services=services,
        staff=staff,
        doctors=doctor_rows,
        doctor_branches=doctor_branches,
        doctor_services=doctor_services,
        branch_working_hours=branch_hours,
        doctor_working_hours=doctor_hours,
        booking_settings=settings,
        readiness=_readiness(
            branches=branches,
            services=services,
            doctors=doctors,
            doctor_branches=doctor_branches,
            doctor_services=doctor_services,
            branch_hours=branch_hours,
            doctor_hours=doctor_hours,
            booking_settings=settings,
        ),
    )



def _ai_session_or_404(
    db: Session,
    *,
    workspace_id: UUID,
    user_id: UUID,
    session_id: UUID,
) -> OnboardingAISession:
    session = db.scalar(
        select(OnboardingAISession).where(
            OnboardingAISession.id == session_id,
            OnboardingAISession.workspace_id == workspace_id,
            OnboardingAISession.created_by_user_id == user_id,
        )
    )
    if session is None:
        raise HTTPException(status_code=404, detail="Onboarding AI session not found.")
    return session


@router.post("/ai/chat", response_model=OnboardingAIResponse)
def ai_onboarding_chat(
    payload: OnboardingAIChatRequest,
    access: Annotated[WorkspaceAccess, Depends(get_workspace_admin)],
    db: Annotated[Session, Depends(get_db)],
) -> OnboardingAIResponse:
    try:
        return process_onboarding_message(
            db,
            workspace=access.workspace,
            user=access.user,
            message=payload.message,
            session_id=payload.session_id,
            expected_version=payload.expected_version,
        )
    except OnboardingSessionConflictError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    except OnboardingPlanValidationError as exc:
        raise HTTPException(
            status_code=422,
            detail={"message": str(exc), "errors": exc.errors},
        ) from exc
    except OnboardingExecutionError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    except StructuredOutputError as exc:
        raise HTTPException(
            status_code=502,
            detail="AI onboarding planner returned an invalid structured result.",
        ) from exc
    except LLMProviderError as exc:
        code = 503 if exc.retryable else 502
        raise HTTPException(
            status_code=code,
            detail="Gemini onboarding planner request failed.",
        ) from exc
    except LLMConfigurationError as exc:
        raise HTTPException(
            status_code=503,
            detail="Gemini onboarding model is not configured on the backend.",
        ) from exc
    except ProgrammingError as exc:
        db.rollback()
        message = str(exc).lower()
        if "onboarding_ai_sessions" in message or "onboarding_ai_events" in message:
            raise HTTPException(
                status_code=503,
                detail=(
                    "AI onboarding database migration is missing. "
                    "Run Alembic upgrade head and verify head "
                    "0013_ai_onboarding_sessions."
                ),
            ) from exc
        raise


@router.post(
    "/ai/sessions/{session_id}/confirm",
    response_model=OnboardingAIResponse,
)
def confirm_ai_onboarding_plan(
    session_id: UUID,
    payload: OnboardingAICommandRequest,
    access: Annotated[WorkspaceAccess, Depends(get_workspace_admin)],
    db: Annotated[Session, Depends(get_db)],
) -> OnboardingAIResponse:
    session = _ai_session_or_404(
        db,
        workspace_id=access.workspace.id,
        user_id=access.user.id,
        session_id=session_id,
    )
    try:
        return execute_plan(
            db,
            session=session,
            user=access.user,
            expected_version=payload.expected_version,
        )
    except OnboardingSessionConflictError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    except OnboardingPlanValidationError as exc:
        raise HTTPException(
            status_code=422,
            detail={"message": str(exc), "errors": exc.errors},
        ) from exc
    except OnboardingExecutionError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc


@router.post(
    "/ai/sessions/{session_id}/cancel",
    response_model=OnboardingAIResponse,
)
def cancel_ai_onboarding_plan(
    session_id: UUID,
    payload: OnboardingAICommandRequest,
    access: Annotated[WorkspaceAccess, Depends(get_workspace_admin)],
    db: Annotated[Session, Depends(get_db)],
) -> OnboardingAIResponse:
    session = _ai_session_or_404(
        db,
        workspace_id=access.workspace.id,
        user_id=access.user.id,
        session_id=session_id,
    )
    try:
        return cancel_session(
            db,
            session=session,
            user=access.user,
            expected_version=payload.expected_version,
        )
    except OnboardingSessionConflictError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc


@router.get(
    "/ai/sessions/{session_id}",
    response_model=OnboardingAISessionRead,
)
def read_ai_onboarding_session(
    session_id: UUID,
    access: Annotated[WorkspaceAccess, Depends(get_workspace_admin)],
    db: Annotated[Session, Depends(get_db)],
) -> OnboardingAISessionRead:
    session = _ai_session_or_404(
        db,
        workspace_id=access.workspace.id,
        user_id=access.user.id,
        session_id=session_id,
    )
    return OnboardingAISessionRead(
        session_id=session.id,
        status=session.status,
        version=session.version,
        plan=(
            OnboardingPlan.model_validate(session.plan)
            if session.plan
            else None
        ),
        plan_summary=dict(session.plan_summary or {}),
        missing_information=list(session.missing_information or []),
        execution_result=dict(session.execution_result or {}),
        expires_at=session.expires_at,
    )
