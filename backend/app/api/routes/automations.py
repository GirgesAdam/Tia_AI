from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, Header, HTTPException, Query, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.dependencies.security import WorkspaceAccess, get_workspace_admin, get_workspace_reader
from app.database.session import get_db
from app.models.automation_job import AutomationJob
from app.models.automation_rule import AutomationRule
from app.models.automation_worker import AutomationWorker
from app.schemas.automation import (
    AutomationExecuteResponse,
    AutomationJobRead,
    AutomationJobStatus,
    AutomationRuleRead,
    AutomationRuleUpdate,
    AutomationTickRequest,
    AutomationTickResponse,
    AutomationWorkerCreate,
    AutomationWorkerCreated,
    AutomationWorkerRead,
    AutomationWorkerStatusUpdate,
    AutomationWorkerTokenRotated,
)
from app.services.automations import (
    AutomationError,
    claim_due_jobs,
    ensure_default_rules,
    execute_job,
    generate_worker_token,
    get_worker_by_token,
    plan_automation_jobs,
)

router = APIRouter()


@dataclass(frozen=True)
class AutomationWorkerAccess:
    worker: AutomationWorker


def get_automation_worker_access(
    x_automation_token: Annotated[str, Header(alias="X-Automation-Token")],
    db: Annotated[Session, Depends(get_db)],
) -> AutomationWorkerAccess:
    worker = get_worker_by_token(db, x_automation_token)
    if worker is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid automation worker token.",
        )
    worker.last_seen_at = datetime.now(timezone.utc)
    db.commit()
    return AutomationWorkerAccess(worker=worker)


@router.get("/rules", response_model=list[AutomationRuleRead])
def list_rules(
    access: Annotated[WorkspaceAccess, Depends(get_workspace_reader)],
    db: Annotated[Session, Depends(get_db)],
) -> list[AutomationRule]:
    return ensure_default_rules(db, access.workspace.id)


@router.patch("/rules/{rule_id}", response_model=AutomationRuleRead)
def update_rule(
    rule_id: UUID,
    payload: AutomationRuleUpdate,
    access: Annotated[WorkspaceAccess, Depends(get_workspace_admin)],
    db: Annotated[Session, Depends(get_db)],
) -> AutomationRule:
    rule = db.scalar(
        select(AutomationRule).where(
            AutomationRule.workspace_id == access.workspace.id,
            AutomationRule.id == rule_id,
        )
    )
    if rule is None:
        raise HTTPException(status_code=404, detail="Automation rule not found.")

    changes = payload.model_dump(exclude_unset=True)
    if "config" in changes:
        rule.config_json = changes.pop("config") or {}
    for key, value in changes.items():
        setattr(rule, key, value)

    if payload.enabled is False:
        for job in db.scalars(
            select(AutomationJob).where(
                AutomationJob.workspace_id == access.workspace.id,
                AutomationJob.rule_id == rule.id,
                AutomationJob.status.in_(("queued", "failed")),
            )
        ):
            job.status = "cancelled"
            job.completed_at = datetime.now(timezone.utc)
            job.result_json = {"reason": "rule_disabled_by_admin"}

    db.commit()
    db.refresh(rule)
    return rule


@router.get("/jobs", response_model=list[AutomationJobRead])
def list_jobs(
    access: Annotated[WorkspaceAccess, Depends(get_workspace_reader)],
    db: Annotated[Session, Depends(get_db)],
    job_status: Annotated[AutomationJobStatus | None, Query(alias="status")] = None,
    limit: Annotated[int, Query(ge=1, le=200)] = 50,
) -> list[AutomationJob]:
    stmt = select(AutomationJob).where(
        AutomationJob.workspace_id == access.workspace.id
    )
    if job_status:
        stmt = stmt.where(AutomationJob.status == job_status)
    return list(
        db.scalars(
            stmt.order_by(AutomationJob.created_at.desc()).limit(limit)
        )
    )


@router.post("/workers", response_model=AutomationWorkerCreated, status_code=201)
def create_worker(
    payload: AutomationWorkerCreate,
    access: Annotated[WorkspaceAccess, Depends(get_workspace_admin)],
    db: Annotated[Session, Depends(get_db)],
) -> AutomationWorkerCreated:
    raw, token_hash = generate_worker_token()
    worker = AutomationWorker(
        workspace_id=access.workspace.id,
        name=payload.name,
        token_hash=token_hash,
        status="active",
        created_by_user_id=access.user.id,
    )
    db.add(worker)
    db.commit()
    db.refresh(worker)
    return AutomationWorkerCreated(
        **AutomationWorkerRead.model_validate(worker).model_dump(),
        worker_token=raw,
    )


@router.get("/workers", response_model=list[AutomationWorkerRead])
def list_workers(
    access: Annotated[WorkspaceAccess, Depends(get_workspace_admin)],
    db: Annotated[Session, Depends(get_db)],
) -> list[AutomationWorker]:
    return list(
        db.scalars(
            select(AutomationWorker)
            .where(AutomationWorker.workspace_id == access.workspace.id)
            .order_by(AutomationWorker.created_at)
        )
    )


@router.patch("/workers/{worker_id}", response_model=AutomationWorkerRead)
def update_worker_status(
    worker_id: UUID,
    payload: AutomationWorkerStatusUpdate,
    access: Annotated[WorkspaceAccess, Depends(get_workspace_admin)],
    db: Annotated[Session, Depends(get_db)],
) -> AutomationWorker:
    worker = db.scalar(
        select(AutomationWorker).where(
            AutomationWorker.workspace_id == access.workspace.id,
            AutomationWorker.id == worker_id,
        )
    )
    if worker is None:
        raise HTTPException(status_code=404, detail="Automation worker not found.")
    worker.status = payload.status
    db.commit()
    db.refresh(worker)
    return worker


@router.post("/workers/{worker_id}/rotate-token", response_model=AutomationWorkerTokenRotated)
def rotate_worker_token(
    worker_id: UUID,
    access: Annotated[WorkspaceAccess, Depends(get_workspace_admin)],
    db: Annotated[Session, Depends(get_db)],
) -> AutomationWorkerTokenRotated:
    worker = db.scalar(
        select(AutomationWorker).where(
            AutomationWorker.workspace_id == access.workspace.id,
            AutomationWorker.id == worker_id,
        )
    )
    if worker is None:
        raise HTTPException(status_code=404, detail="Automation worker not found.")
    raw, token_hash = generate_worker_token()
    worker.token_hash = token_hash
    worker.status = "active"
    db.commit()
    return AutomationWorkerTokenRotated(worker_id=worker.id, worker_token=raw)


@router.post("/adapter/tick", response_model=AutomationTickResponse)
def automation_tick(
    payload: AutomationTickRequest,
    worker_access: Annotated[AutomationWorkerAccess, Depends(get_automation_worker_access)],
    db: Annotated[Session, Depends(get_db)],
) -> AutomationTickResponse:
    workspace_id = worker_access.worker.workspace_id
    planning = plan_automation_jobs(
        db,
        workspace_id=workspace_id,
        planning_horizon_days=payload.planning_horizon_days,
    )
    claimed = claim_due_jobs(
        db,
        workspace_id=workspace_id,
        limit=payload.limit,
    )
    return AutomationTickResponse(
        planned=planning.planned,
        cancelled=planning.cancelled,
        claimed=claimed,
    )


@router.post("/adapter/jobs/{job_id}/execute", response_model=AutomationExecuteResponse)
def execute_automation_job(
    job_id: UUID,
    worker_access: Annotated[AutomationWorkerAccess, Depends(get_automation_worker_access)],
    db: Annotated[Session, Depends(get_db)],
) -> AutomationExecuteResponse:
    try:
        result = execute_job(
            db,
            workspace_id=worker_access.worker.workspace_id,
            job_id=job_id,
        )
    except AutomationError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc

    job = result.job
    return AutomationExecuteResponse(
        job_id=job.id,
        status=job.status,
        message_id=job.message_id,
        dispatch_id=job.dispatch_id,
        reason=result.reason,
    )
