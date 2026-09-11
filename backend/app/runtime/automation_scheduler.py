from __future__ import annotations

import logging
import os
import time
from datetime import UTC, datetime

from sqlalchemy import select

from app.database.session import SessionLocal
from app.models.automation_worker import AutomationWorker
from app.models.workspace import Workspace
from app.services.automations import (
    AutomationError,
    claim_due_jobs,
    execute_job,
    generate_worker_token,
    plan_automation_jobs,
)
from app.services.clinic_integration_sync_runtime import run_scheduled_sync_tick

logger = logging.getLogger("tia.automation_scheduler")

RUNTIME_WORKER_NAME = "Tia Railway Automation Scheduler"
DEFAULT_INTERVAL_SECONDS = 60
DEFAULT_JOB_LIMIT = 20
DEFAULT_PLANNING_HORIZON_DAYS = 14
DEFAULT_SYNC_PAGE_SIZE = 100
DEFAULT_SYNC_MAX_PAGES = 10


def _int_env(name: str, default: int, *, minimum: int, maximum: int) -> int:
    raw = os.getenv(name)
    if raw is None:
        return default
    try:
        value = int(raw)
    except ValueError:
        logger.warning("Ignoring invalid %s=%r; using %s", name, raw, default)
        return default
    return max(minimum, min(value, maximum))


def _heartbeat(db, workspace_id, *, now: datetime) -> None:
    worker = db.scalar(
        select(AutomationWorker).where(
            AutomationWorker.workspace_id == workspace_id,
            AutomationWorker.name == RUNTIME_WORKER_NAME,
        )
    )
    if worker is None:
        _, token_hash = generate_worker_token()
        worker = AutomationWorker(
            workspace_id=workspace_id,
            name=RUNTIME_WORKER_NAME,
            token_hash=token_hash,
            status="active",
            created_by_user_id=None,
        )
        db.add(worker)
    else:
        worker.status = "active"
    worker.last_seen_at = now
    db.commit()


def run_workspace_tick(
    workspace_id,
    *,
    job_limit: int = DEFAULT_JOB_LIMIT,
    planning_horizon_days: int = DEFAULT_PLANNING_HORIZON_DAYS,
    sync_page_size: int = DEFAULT_SYNC_PAGE_SIZE,
    sync_max_pages: int = DEFAULT_SYNC_MAX_PAGES,
) -> None:
    with SessionLocal() as db:
        workspace = db.get(Workspace, workspace_id)
        if workspace is None or not workspace.is_active:
            return

        now = datetime.now(UTC)
        _heartbeat(db, workspace.id, now=now)

        planning = plan_automation_jobs(
            db,
            workspace_id=workspace.id,
            planning_horizon_days=planning_horizon_days,
        )
        claimed = claim_due_jobs(
            db,
            workspace_id=workspace.id,
            limit=job_limit,
        )

        executed = 0
        failed = 0
        for claimed_job in claimed:
            try:
                execute_job(
                    db,
                    workspace_id=workspace.id,
                    job_id=claimed_job.job_id,
                )
                executed += 1
            except AutomationError as exc:
                db.rollback()
                failed += 1
                logger.warning(
                    "Automation job %s could not execute: %s",
                    claimed_job.job_id,
                    exc,
                )
            except Exception:
                db.rollback()
                failed += 1
                logger.exception(
                    "Unexpected automation execution failure for job %s",
                    claimed_job.job_id,
                )

        sync = run_scheduled_sync_tick(
            db,
            workspace=workspace,
            page_size=sync_page_size,
            max_pages_per_domain=sync_max_pages,
        )

        logger.info(
            "automation_tick workspace=%s planned=%s cancelled=%s claimed=%s executed=%s failed=%s sync_claimed=%s sync_reason=%s",
            workspace.id,
            planning.planned,
            planning.cancelled,
            len(claimed),
            executed,
            failed,
            sync.claimed,
            sync.reason,
        )


def run_once() -> None:
    job_limit = _int_env(
        "AUTOMATION_JOB_LIMIT",
        DEFAULT_JOB_LIMIT,
        minimum=1,
        maximum=100,
    )
    planning_horizon_days = _int_env(
        "AUTOMATION_PLANNING_HORIZON_DAYS",
        DEFAULT_PLANNING_HORIZON_DAYS,
        minimum=1,
        maximum=90,
    )
    sync_page_size = _int_env(
        "AUTOMATION_SYNC_PAGE_SIZE",
        DEFAULT_SYNC_PAGE_SIZE,
        minimum=1,
        maximum=500,
    )
    sync_max_pages = _int_env(
        "AUTOMATION_SYNC_MAX_PAGES",
        DEFAULT_SYNC_MAX_PAGES,
        minimum=1,
        maximum=100,
    )

    with SessionLocal() as db:
        workspace_ids = list(
            db.scalars(
                select(Workspace.id)
                .where(Workspace.is_active.is_(True))
                .order_by(Workspace.created_at)
            )
        )

    for workspace_id in workspace_ids:
        try:
            run_workspace_tick(
                workspace_id,
                job_limit=job_limit,
                planning_horizon_days=planning_horizon_days,
                sync_page_size=sync_page_size,
                sync_max_pages=sync_max_pages,
            )
        except Exception:
            logger.exception("Automation scheduler tick failed for workspace %s", workspace_id)


def main() -> None:
    logging.basicConfig(
        level=os.getenv("LOG_LEVEL", "INFO").upper(),
        format="%(asctime)s %(levelname)s %(name)s %(message)s",
    )
    interval_seconds = _int_env(
        "AUTOMATION_TICK_INTERVAL_SECONDS",
        DEFAULT_INTERVAL_SECONDS,
        minimum=15,
        maximum=3600,
    )
    logger.info("Starting native Tia automation scheduler interval=%ss", interval_seconds)

    while True:
        started = time.monotonic()
        run_once()
        elapsed = time.monotonic() - started
        time.sleep(max(1.0, interval_seconds - elapsed))


if __name__ == "__main__":
    main()
