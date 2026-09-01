from __future__ import annotations

from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError, ProgrammingError
from sqlalchemy.orm import Session

from app.agents.llm_runtime import LLMProviderError, provider_error_http_status
from app.agents.model_provider import LLMConfigurationError
from app.agents.structured_output import StructuredOutputError
from app.api.dependencies.security import WorkspaceAccess, get_current_user, get_workspace_admin
from app.database.session import get_db
from app.models.clinic_integration import ClinicIntegration
from app.models.onboarding_ai_session import OnboardingAISession
from app.models.user import User
from app.models.workspace import Workspace
from app.models.workspace_member import WorkspaceMember
from app.schemas.onboarding import WorkspaceCreate, WorkspaceCreated
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
    cancel_session as cancel_ai_session,
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
        timezone="Africa/Cairo",
        is_active=True,
    )
    db.add(workspace)
    db.flush()
    db.add(
        ClinicIntegration(
            workspace_id=workspace.id,
            mode="tia_native",
            adapter_key="tia_database",
            status="active",
            config_json={},
        )
    )
    db.add(
        WorkspaceMember(
            workspace_id=workspace.id,
            user_id=user.id,
            role="admin",
            is_active=True,
        )
    )
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
        raise HTTPException(status_code=422, detail={"message": str(exc), "errors": exc.errors}) from exc
    except OnboardingExecutionError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    except StructuredOutputError as exc:
        raise HTTPException(status_code=502, detail="AI onboarding planner returned an invalid structured result.") from exc
    except LLMProviderError as exc:
        raise HTTPException(status_code=provider_error_http_status(exc), detail="Gemini onboarding planner request failed.") from exc
    except LLMConfigurationError as exc:
        raise HTTPException(status_code=503, detail="Gemini onboarding model is not configured on the backend.") from exc
    except ProgrammingError as exc:
        db.rollback()
        message = str(exc).lower()
        if "onboarding_ai_sessions" in message or "onboarding_ai_events" in message:
            raise HTTPException(
                status_code=503,
                detail="AI onboarding database migration is missing. Run Alembic upgrade head.",
            ) from exc
        raise


@router.post("/ai/sessions/{session_id}/confirm", response_model=OnboardingAIResponse)
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
        return execute_plan(db, session=session, user=access.user, expected_version=payload.expected_version)
    except OnboardingSessionConflictError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    except OnboardingPlanValidationError as exc:
        raise HTTPException(status_code=422, detail={"message": str(exc), "errors": exc.errors}) from exc
    except OnboardingExecutionError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc


@router.post("/ai/sessions/{session_id}/cancel", response_model=OnboardingAIResponse)
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
        return cancel_ai_session(db, session=session, user=access.user, expected_version=payload.expected_version)
    except OnboardingSessionConflictError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc


@router.get("/ai/sessions/{session_id}", response_model=OnboardingAISessionRead)
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
        plan=(OnboardingPlan.model_validate(session.plan) if session.plan else None),
        plan_summary=dict(session.plan_summary or {}),
        missing_information=list(session.missing_information or []),
        execution_result=dict(session.execution_result or {}),
        expires_at=session.expires_at,
    )
