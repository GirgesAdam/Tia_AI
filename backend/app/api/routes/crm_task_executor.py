from __future__ import annotations

from datetime import UTC, datetime
from typing import Annotated, Literal
from uuid import UUID
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.dependencies.security import WorkspaceAccess, get_workspace_admin, get_workspace_reader
from app.database.session import get_db
from app.models.automation_job import AutomationJob
from app.models.crm_task import CRMTask
from app.services.activity import record_activity_event
from app.services.crm_tasks import CRMTaskError, create_crm_task, validate_assignee

router = APIRouter()


class CRMFollowUpCreate(BaseModel):
    patient_id: UUID
    conversation_id: UUID | None = None
    assigned_user_id: UUID | None = None
    execution_mode: Literal["ai", "human"] = "ai"
    title: str = Field(min_length=1, max_length=200)
    description: str | None = Field(default=None, max_length=5000)
    due_at_local: str = Field(min_length=1, max_length=64)


class CRMFollowUpCreated(BaseModel):
    task_id: UUID
    due_at: datetime
    execution_mode: Literal["ai", "human"]


class CRMTaskExecutorUpdate(BaseModel):
    executor: Literal["tia", "staff", "unassigned"]
    assigned_user_id: UUID | None = None


class CRMTaskExecutorRead(BaseModel):
    task_id: UUID
    execution_mode: Literal["ai", "human"]
    assigned_user_id: UUID | None


def _workspace_timezone(access: WorkspaceAccess) -> ZoneInfo:
    try:
        return ZoneInfo((access.workspace.timezone or "Africa/Cairo").strip())
    except ZoneInfoNotFoundError:
        return ZoneInfo("Africa/Cairo")


def _parse_local_due_at(value: str, access: WorkspaceAccess) -> datetime:
    try:
        parsed = datetime.fromisoformat(value.strip())
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="Invalid follow-up date/time.",
        ) from exc
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        parsed = parsed.replace(tzinfo=_workspace_timezone(access))
    due_at = parsed.astimezone(UTC)
    if due_at <= datetime.now(UTC):
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="Follow-up time must be in the future.",
        )
    return due_at


def _follow_up_job(db: Session, *, workspace_id: UUID, task_id: UUID) -> AutomationJob | None:
    return db.scalar(
        select(AutomationJob)
        .where(
            AutomationJob.workspace_id == workspace_id,
            AutomationJob.crm_task_id == task_id,
            AutomationJob.job_kind == "crm_follow_up",
        )
        .with_for_update()
    )


def _cancel_pending_ai_job(job: AutomationJob | None, *, reason: str) -> None:
    if job is None:
        return
    job.status = "cancelled"
    job.locked_at = None
    job.next_attempt_at = None
    job.completed_at = datetime.now(UTC)
    job.result_json = {**(job.result_json or {}), "reason": reason}


def _queue_ai_job(db: Session, *, task: CRMTask, job: AutomationJob | None) -> None:
    if job is not None:
        job.status = "queued"
        job.scheduled_for = task.due_at
        job.locked_at = None
        job.next_attempt_at = None
        job.completed_at = None
        job.last_error = None
        job.message_id = None
        job.dispatch_id = None
        job.result_json = {}
        return

    db.add(
        AutomationJob(
            workspace_id=task.workspace_id,
            rule_id=None,
            appointment_id=None,
            crm_task_id=task.id,
            patient_id=task.patient_id,
            job_kind="crm_follow_up",
            status="queued",
            scheduled_for=task.due_at,
            dedupe_key=f"crm-followup:{task.id}",
            attempts=0,
            payload_json={"crm_task_id": str(task.id)},
            result_json={},
        )
    )


@router.post("/followups", response_model=CRMFollowUpCreated, status_code=status.HTTP_201_CREATED)
def create_follow_up(
    payload: CRMFollowUpCreate,
    access: Annotated[WorkspaceAccess, Depends(get_workspace_reader)],
    db: Annotated[Session, Depends(get_db)],
) -> CRMFollowUpCreated:
    due_at = _parse_local_due_at(payload.due_at_local, access)
    assigned_user_id = payload.assigned_user_id if payload.execution_mode == "human" else None
    try:
        task = create_crm_task(
            db,
            workspace_id=access.workspace.id,
            patient_id=payload.patient_id,
            conversation_id=payload.conversation_id,
            assigned_user_id=assigned_user_id,
            created_by_user_id=access.user.id,
            task_type="follow_up",
            execution_mode=payload.execution_mode,
            priority="normal",
            title=payload.title,
            description=payload.description,
            due_at=due_at,
            source="manual",
        )
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=str(exc),
        ) from exc
    return CRMFollowUpCreated(
        task_id=task.id,
        due_at=task.due_at,
        execution_mode=task.execution_mode,
    )


@router.patch("/tasks/{task_id}/executor", response_model=CRMTaskExecutorRead)
def update_task_executor(
    task_id: UUID,
    payload: CRMTaskExecutorUpdate,
    access: Annotated[WorkspaceAccess, Depends(get_workspace_admin)],
    db: Annotated[Session, Depends(get_db)],
) -> CRMTaskExecutorRead:
    task = db.scalar(
        select(CRMTask)
        .where(
            CRMTask.workspace_id == access.workspace.id,
            CRMTask.id == task_id,
        )
        .with_for_update()
    )
    if task is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Task not found.")
    if task.status not in {"pending", "in_progress"}:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Completed or cancelled follow-ups cannot be reassigned.",
        )
    if task.task_type != "follow_up" and payload.executor == "tia":
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="Only follow-up tasks can be executed by Tia.",
        )

    previous_mode = task.execution_mode
    previous_assignee = task.assigned_user_id
    job = _follow_up_job(db, workspace_id=task.workspace_id, task_id=task.id)
    if job is not None and job.status in {"processing", "dispatched"}:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="This follow-up is already being sent or was already dispatched, so its executor cannot be changed.",
        )

    if payload.executor == "tia":
        if task.status != "pending":
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="A follow-up can only be handed back to Tia before execution starts.",
            )
        task.execution_mode = "ai"
        task.assigned_user_id = None
        _queue_ai_job(db, task=task, job=job)
    elif payload.executor == "staff":
        if payload.assigned_user_id is None:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail="Select a team member before assigning this follow-up.",
            )
        try:
            validate_assignee(
                db,
                workspace_id=task.workspace_id,
                user_id=payload.assigned_user_id,
            )
        except CRMTaskError as exc:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail=str(exc),
            ) from exc
        task.execution_mode = "human"
        task.assigned_user_id = payload.assigned_user_id
        _cancel_pending_ai_job(job, reason="staff_assignment")
    else:
        task.execution_mode = "human"
        task.assigned_user_id = None
        _cancel_pending_ai_job(job, reason="unassigned_by_admin")

    record_activity_event(
        db,
        workspace_id=task.workspace_id,
        actor_type="staff",
        actor_user_id=access.user.id,
        action="crm_task.executor_changed",
        entity_type="crm_task",
        entity_id=task.id,
        summary="CRM follow-up executor changed",
        metadata={
            "previous_execution_mode": previous_mode,
            "execution_mode": task.execution_mode,
            "previous_assigned_user_id": previous_assignee,
            "assigned_user_id": task.assigned_user_id,
        },
    )
    db.commit()
    db.refresh(task)
    return CRMTaskExecutorRead(
        task_id=task.id,
        execution_mode=task.execution_mode,
        assigned_user_id=task.assigned_user_id,
    )
