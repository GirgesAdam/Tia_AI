from __future__ import annotations

import hashlib
from datetime import UTC, datetime, timedelta
from typing import Iterable
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.integrations.clinic.authority import (
    ClinicIntegrationAuthorityError,
    external_domain_write_enabled,
)
from app.integrations.clinic.prototype_external import PrototypeExternalConfigurationError
from app.integrations.clinic.registry import ClinicAdapterConfigurationError, get_clinic_adapter
from app.integrations.clinic.mapped_sync import ClinicMappedSyncError, MappedClinicSyncSource
from app.schemas.clinic_connector_mapping import ClinicSyncMapping
from app.integrations.clinic.sync_contract import (
    ClinicSyncDomain,
    ClinicSyncFetchRequest,
    ClinicSyncPage,
    ClinicRawSyncSource,
    ClinicSyncSource,
)
from app.models.clinic_integration import ClinicIntegration
from app.models.clinic_integration_sync import (
    ClinicIntegrationSyncCheckpoint,
    ClinicIntegrationSyncFailure,
    ClinicIntegrationSyncRun,
    ClinicIntegrationSyncSchedule,
)
from app.models.workspace import Workspace
from app.schemas.clinic_integration import (
    ClinicSyncCycleRead,
    ClinicSyncDomainCycleRead,
    ClinicSyncScheduleRead,
    ClinicSyncScheduleUpsert,
    ClinicSyncWorkerTickResponse,
)
from app.services.activity import record_activity_event
from app.services.clinic_integration_sync import (
    ClinicIntegrationSyncError,
    apply_external_sync_page,
)

SYNC_DOMAIN_ORDER = (
    ClinicSyncDomain.PATIENTS,
    ClinicSyncDomain.APPOINTMENTS,
    ClinicSyncDomain.PAYMENTS,
)
SYNC_LEASE_MINUTES = 10
MAX_SYNC_ERROR_LENGTH = 300


class ClinicSyncRuntimeError(ValueError):
    pass


def _utc(value: datetime | None = None) -> datetime:
    current = value or datetime.now(UTC)
    if current.tzinfo is None or current.utcoffset() is None:
        current = current.replace(tzinfo=UTC)
    return current.astimezone(UTC)


def _safe_error(exc: Exception) -> str:
    if isinstance(
        exc,
        (
            ClinicSyncRuntimeError,
            ClinicIntegrationSyncError,
            ClinicAdapterConfigurationError,
            PrototypeExternalConfigurationError,
            ClinicIntegrationAuthorityError,
            ClinicMappedSyncError,
        ),
    ):
        text = str(exc).strip()
        if text:
            return text[:MAX_SYNC_ERROR_LENGTH]
    return "External clinic connector failed while reading a sync page."


def _connector_failure_digest(domain: ClinicSyncDomain) -> str:
    return hashlib.sha256(f"connector:{domain.value}".encode("utf-8")).hexdigest()


def _schedule_locked(schedule: ClinicIntegrationSyncSchedule, *, now: datetime) -> bool:
    if schedule.locked_at is None:
        return False
    return _utc(schedule.locked_at) > now - timedelta(minutes=SYNC_LEASE_MINUTES)


def _get_or_create_schedule(
    db: Session,
    *,
    workspace_id: UUID,
) -> ClinicIntegrationSyncSchedule:
    schedule = db.get(ClinicIntegrationSyncSchedule, workspace_id)
    if schedule is None:
        schedule = ClinicIntegrationSyncSchedule(workspace_id=workspace_id)
        db.add(schedule)
        db.flush()
    return schedule


def read_sync_schedule(
    db: Session,
    *,
    workspace_id: UUID,
    now: datetime | None = None,
) -> ClinicSyncScheduleRead:
    current = _utc(now)
    schedule = db.get(ClinicIntegrationSyncSchedule, workspace_id)
    if schedule is None:
        return ClinicSyncScheduleRead(enabled=False, interval_minutes=15)
    return ClinicSyncScheduleRead(
        enabled=bool(schedule.enabled),
        interval_minutes=int(schedule.interval_minutes),
        next_run_at=schedule.next_run_at,
        locked=_schedule_locked(schedule, now=current),
        locked_at=schedule.locked_at,
        attempts=int(schedule.attempts),
        last_error=schedule.last_error,
        last_completed_at=schedule.last_completed_at,
    )


def _source_for_workspace(db: Session, workspace: Workspace) -> ClinicSyncSource:
    try:
        adapter = get_clinic_adapter(db=db, workspace=workspace)
    except ClinicAdapterConfigurationError as exc:
        raise ClinicSyncRuntimeError(str(exc)) from exc
    integration = db.get(ClinicIntegration, workspace.id)
    config = dict(getattr(integration, "config_json", None) or {}) if integration is not None else {}
    approved_mapping = config.get("approved_sync_mapping")
    approved_fingerprint = str(config.get("approved_sync_schema_fingerprint") or "").strip()
    if approved_mapping is not None:
        if not isinstance(adapter, ClinicRawSyncSource):
            raise ClinicSyncRuntimeError(
                "Configured clinic adapter has an approved structural mapping but does not expose raw sync pages."
            )
        if not approved_fingerprint:
            raise ClinicSyncRuntimeError("Approved connector mapping is missing its schema fingerprint.")
        try:
            mapping = ClinicSyncMapping.model_validate(approved_mapping)
        except (TypeError, ValueError) as exc:
            raise ClinicSyncRuntimeError("Approved connector sync mapping is invalid.") from exc
        return MappedClinicSyncSource(
            source=adapter,
            mapping=mapping,
            schema_fingerprint_value=approved_fingerprint,
        )
    if not isinstance(adapter, ClinicSyncSource):
        raise ClinicSyncRuntimeError(
            "Configured clinic adapter does not expose the incremental sync source contract."
        )
    return adapter


def sync_source_domains(db: Session, workspace: Workspace) -> frozenset[ClinicSyncDomain]:
    try:
        source = _source_for_workspace(db, workspace)
    except ClinicSyncRuntimeError:
        return frozenset()
    return frozenset(source.sync_domains)


def _external_authority_domains(integration: ClinicIntegration) -> tuple[ClinicSyncDomain, ...]:
    return tuple(
        domain
        for domain in SYNC_DOMAIN_ORDER
        if external_domain_write_enabled(integration, domain.value)
    )


def _validate_connector_runtime(
    db: Session,
    *,
    workspace: Workspace,
    integration: ClinicIntegration,
) -> ClinicSyncSource:
    if integration.status != "active":
        raise ClinicSyncRuntimeError("Clinic integration must be active before connector sync can run.")
    if integration.mode not in {"external_api", "hybrid"}:
        raise ClinicSyncRuntimeError(
            "Connector sync requires external_api or hybrid integration mode."
        )
    return _source_for_workspace(db, workspace)


def _validate_sync_enabled_configuration(
    db: Session,
    *,
    workspace: Workspace,
    integration: ClinicIntegration,
) -> ClinicSyncSource:
    source = _validate_connector_runtime(
        db,
        workspace=workspace,
        integration=integration,
    )
    authoritative = set(_external_authority_domains(integration))
    if not authoritative:
        raise ClinicSyncRuntimeError(
            "No clinic domain is currently external-owned, so scheduled sync has nothing to apply."
        )
    missing = sorted(domain.value for domain in authoritative if domain not in source.sync_domains)
    if missing:
        raise ClinicSyncRuntimeError(
            "Configured connector does not expose required external-owned sync domains: "
            + ", ".join(missing)
        )
    return source


def update_sync_schedule(
    db: Session,
    *,
    workspace: Workspace,
    payload: ClinicSyncScheduleUpsert,
    now: datetime | None = None,
) -> ClinicSyncScheduleRead:
    current = _utc(now)
    integration = db.get(ClinicIntegration, workspace.id)
    if integration is None:
        raise ClinicSyncRuntimeError("Clinic integration configuration is missing.")
    schedule = _get_or_create_schedule(db, workspace_id=workspace.id)
    previously_enabled = bool(schedule.enabled)

    if payload.enabled:
        _validate_sync_enabled_configuration(
            db,
            workspace=workspace,
            integration=integration,
        )
        schedule.enabled = True
        schedule.interval_minutes = int(payload.interval_minutes)
        if not previously_enabled or schedule.next_run_at is None:
            schedule.next_run_at = current
    else:
        schedule.enabled = False
        schedule.interval_minutes = int(payload.interval_minutes)
        schedule.next_run_at = None
        schedule.locked_at = None
        schedule.attempts = 0
        schedule.last_error = None

    db.flush()
    record_activity_event(
        db,
        workspace_id=workspace.id,
        actor_type="staff",
        action="integration.sync_schedule_updated",
        entity_type="clinic_integration",
        summary="Clinic integration sync schedule updated",
        metadata={
            "enabled": bool(schedule.enabled),
            "interval_minutes": int(schedule.interval_minutes),
        },
    )
    db.flush()
    return read_sync_schedule(db, workspace_id=workspace.id, now=current)


def _record_connector_fetch_failure(
    db: Session,
    *,
    workspace_id: UUID,
    domain: ClinicSyncDomain,
    cursor: str | None,
    source_revision: str | None,
    exc: Exception,
    now: datetime,
) -> None:
    message = _safe_error(exc)
    run = ClinicIntegrationSyncRun(
        workspace_id=workspace_id,
        domain=domain.value,
        status="failed",
        cursor_before=cursor,
        cursor_after=cursor,
        source_revision=source_revision,
        processed_count=0,
        created_count=0,
        updated_count=0,
        skipped_count=0,
        failed_count=0,
        completed_at=now,
    )
    db.add(run)
    db.flush()
    db.add(
        ClinicIntegrationSyncFailure(
            workspace_id=workspace_id,
            run_id=run.id,
            domain=domain.value,
            external_id_digest=_connector_failure_digest(domain),
            error_code="connector_fetch_error",
            message=message,
            retryable=True,
        )
    )
    db.flush()


def _checkpoint_cursor(
    db: Session,
    *,
    workspace_id: UUID,
    domain: ClinicSyncDomain,
) -> tuple[str | None, str | None]:
    checkpoint = db.get(ClinicIntegrationSyncCheckpoint, (workspace_id, domain.value))
    if checkpoint is None:
        return None, None
    return checkpoint.cursor, checkpoint.source_revision


def _validate_fetched_page(
    *,
    request: ClinicSyncFetchRequest,
    page: ClinicSyncPage,
) -> None:
    if page.domain != request.domain:
        raise ClinicSyncRuntimeError("Connector returned a sync page for the wrong domain.")
    if page.cursor != request.cursor:
        raise ClinicSyncRuntimeError(
            "Connector returned a page cursor that does not match the requested durable cursor."
        )
    if page.has_more:
        if not page.next_cursor:
            raise ClinicSyncRuntimeError("Connector page says has_more=true but returned no next cursor.")
        if page.next_cursor == page.cursor:
            raise ClinicSyncRuntimeError("Connector next cursor did not advance.")
    elif page.next_cursor is not None:
        raise ClinicSyncRuntimeError(
            "Connector returned next_cursor for a terminal page. Set has_more=true instead."
        )


def _run_domain(
    db: Session,
    *,
    workspace: Workspace,
    source: ClinicSyncSource,
    domain: ClinicSyncDomain,
    page_size: int,
    max_pages: int,
    now: datetime,
) -> ClinicSyncDomainCycleRead:
    cursor, source_revision = _checkpoint_cursor(
        db,
        workspace_id=workspace.id,
        domain=domain,
    )
    totals = {
        "processed_count": 0,
        "created_count": 0,
        "updated_count": 0,
        "skipped_count": 0,
        "failed_count": 0,
    }
    pages = 0

    while pages < max_pages:
        request = ClinicSyncFetchRequest(domain=domain, cursor=cursor, limit=page_size)
        try:
            page = source.fetch_sync_page(request)
            _validate_fetched_page(request=request, page=page)
        except Exception as exc:
            _record_connector_fetch_failure(
                db,
                workspace_id=workspace.id,
                domain=domain,
                cursor=cursor,
                source_revision=source_revision,
                exc=exc,
                now=now,
            )
            db.commit()
            return ClinicSyncDomainCycleRead(
                domain=domain.value,
                status="failed",
                pages=pages,
                complete=False,
                error=_safe_error(exc),
                **totals,
            )

        try:
            result = apply_external_sync_page(
                db=db,
                workspace=workspace,
                page=page,
                now=now,
            )
            db.commit()
        except Exception as exc:
            db.rollback()
            return ClinicSyncDomainCycleRead(
                domain=domain.value,
                status="failed",
                pages=pages,
                complete=False,
                error=_safe_error(exc),
                **totals,
            )

        pages += 1
        totals["processed_count"] += result.processed_count
        totals["created_count"] += result.created_count
        totals["updated_count"] += result.updated_count
        totals["skipped_count"] += result.skipped_count
        totals["failed_count"] += result.failed_count

        if result.failed_count:
            return ClinicSyncDomainCycleRead(
                domain=domain.value,
                status="partial" if result.processed_count > result.failed_count else "failed",
                pages=pages,
                complete=False,
                error="One or more external records require retry or review.",
                **totals,
            )
        if not page.has_more:
            return ClinicSyncDomainCycleRead(
                domain=domain.value,
                status="succeeded",
                pages=pages,
                complete=True,
                **totals,
            )
        cursor = page.next_cursor
        source_revision = page.source_revision

    return ClinicSyncDomainCycleRead(
        domain=domain.value,
        status="succeeded",
        pages=pages,
        complete=False,
        **totals,
    )


def run_sync_cycle(
    db: Session,
    *,
    workspace: Workspace,
    domains: Iterable[str] | None = None,
    page_size: int = 100,
    max_pages_per_domain: int = 10,
    now: datetime | None = None,
) -> ClinicSyncCycleRead:
    started = _utc(now)
    integration = db.get(ClinicIntegration, workspace.id)
    if integration is None:
        raise ClinicSyncRuntimeError("Clinic integration configuration is missing.")
    source = _validate_connector_runtime(
        db,
        workspace=workspace,
        integration=integration,
    )

    requested = set(domains or ())
    known = {domain.value for domain in SYNC_DOMAIN_ORDER}
    unknown = requested - known
    if unknown:
        raise ClinicSyncRuntimeError("Unsupported sync domain requested.")

    authoritative = _external_authority_domains(integration)
    if requested:
        selected = tuple(domain for domain in SYNC_DOMAIN_ORDER if domain.value in requested)
        not_authoritative = [
            domain.value for domain in selected if not external_domain_write_enabled(integration, domain.value)
        ]
        if not_authoritative:
            raise ClinicSyncRuntimeError(
                "Requested sync domain is not external-owned: " + ", ".join(not_authoritative)
            )
    else:
        selected = authoritative

    missing = [domain.value for domain in selected if domain not in source.sync_domains]
    if missing:
        raise ClinicSyncRuntimeError(
            "Configured connector does not expose requested sync domains: " + ", ".join(missing)
        )

    domain_results: list[ClinicSyncDomainCycleRead] = []
    for domain in selected:
        result = _run_domain(
            db,
            workspace=workspace,
            source=source,
            domain=domain,
            page_size=max(1, min(int(page_size), 500)),
            max_pages=max(1, min(int(max_pages_per_domain), 100)),
            now=started,
        )
        domain_results.append(result)
        if result.status in {"failed", "partial"}:
            break

    completed = _utc()
    if not domain_results:
        status = "skipped"
        complete = True
    elif any(item.status == "failed" for item in domain_results):
        status = "failed"
        complete = False
    elif any(item.status == "partial" for item in domain_results):
        status = "partial"
        complete = False
    elif any(not item.complete for item in domain_results):
        status = "succeeded"
        complete = False
    else:
        status = "succeeded"
        complete = True

    return ClinicSyncCycleRead(
        status=status,
        domains=domain_results,
        complete=complete,
        started_at=started,
        completed_at=completed,
    )


def _claim_sync_lease(
    db: Session,
    *,
    workspace: Workspace,
    now: datetime,
    force: bool,
) -> tuple[ClinicIntegrationSyncSchedule | None, str | None]:
    schedule = db.scalar(
        select(ClinicIntegrationSyncSchedule)
        .where(ClinicIntegrationSyncSchedule.workspace_id == workspace.id)
        .with_for_update()
    )
    if schedule is None:
        schedule = ClinicIntegrationSyncSchedule(workspace_id=workspace.id)
        db.add(schedule)
        db.flush()

    if _schedule_locked(schedule, now=now):
        return None, "sync_locked"
    if not force:
        if not schedule.enabled:
            return None, "sync_disabled"
        if schedule.next_run_at is not None and _utc(schedule.next_run_at) > now:
            return None, "not_due"

    integration = db.get(ClinicIntegration, workspace.id)
    if integration is None:
        raise ClinicSyncRuntimeError("Clinic integration configuration is missing.")
    if force:
        _validate_connector_runtime(
            db,
            workspace=workspace,
            integration=integration,
        )
    else:
        _validate_sync_enabled_configuration(
            db,
            workspace=workspace,
            integration=integration,
        )

    schedule.locked_at = now
    schedule.attempts = int(schedule.attempts) + 1
    db.commit()
    return schedule, None


def _record_schedule_claim_failure(
    db: Session,
    *,
    workspace_id: UUID,
    error: str,
    now: datetime,
) -> None:
    """Persist scheduler configuration failures without leaving the worker endpoint noisy.

    A schedule can become invalid after it was enabled (connector removed, authority changed,
    integration disabled). Those are durable operational failures, not HTTP/worker failures.
    """
    schedule = db.scalar(
        select(ClinicIntegrationSyncSchedule)
        .where(ClinicIntegrationSyncSchedule.workspace_id == workspace_id)
        .with_for_update()
    )
    if schedule is None:
        schedule = ClinicIntegrationSyncSchedule(workspace_id=workspace_id)
        db.add(schedule)
        db.flush()

    schedule.locked_at = None
    schedule.attempts = int(schedule.attempts) + 1
    schedule.last_error = error[:MAX_SYNC_ERROR_LENGTH]
    if schedule.enabled:
        backoff_minutes = min(60, 2 ** min(max(int(schedule.attempts), 1), 6))
        schedule.next_run_at = now + timedelta(minutes=backoff_minutes)
    else:
        schedule.next_run_at = None
    db.commit()


def _finish_sync_lease(
    db: Session,
    *,
    workspace_id: UUID,
    cycle: ClinicSyncCycleRead | None,
    error: str | None,
    now: datetime,
) -> None:
    schedule = db.scalar(
        select(ClinicIntegrationSyncSchedule)
        .where(ClinicIntegrationSyncSchedule.workspace_id == workspace_id)
        .with_for_update()
    )
    if schedule is None:
        return
    schedule.locked_at = None

    if error is None and cycle is not None and cycle.status in {"succeeded", "skipped"}:
        schedule.last_error = None
        schedule.attempts = 0
        schedule.last_completed_at = cycle.completed_at
        if schedule.enabled:
            if cycle.complete:
                schedule.next_run_at = now + timedelta(minutes=int(schedule.interval_minutes))
            else:
                # The page budget ended cleanly. Continue from the advanced checkpoint
                # on the next scheduler tick without treating it as a failure.
                schedule.next_run_at = now
        else:
            schedule.next_run_at = None
    else:
        message = (error or "External clinic sync requires retry or review.")[:MAX_SYNC_ERROR_LENGTH]
        schedule.last_error = message
        if schedule.enabled:
            backoff_minutes = min(60, 2 ** min(max(int(schedule.attempts), 1), 6))
            schedule.next_run_at = now + timedelta(minutes=backoff_minutes)
        else:
            schedule.next_run_at = None
    db.commit()


def run_manual_sync(
    db: Session,
    *,
    workspace: Workspace,
    domains: Iterable[str] | None = None,
    page_size: int = 100,
    max_pages_per_domain: int = 10,
    now: datetime | None = None,
) -> ClinicSyncCycleRead:
    current = _utc(now)
    _, reason = _claim_sync_lease(db, workspace=workspace, now=current, force=True)
    if reason:
        raise ClinicSyncRuntimeError("Clinic sync is already running for this workspace.")
    try:
        cycle = run_sync_cycle(
            db,
            workspace=workspace,
            domains=domains,
            page_size=page_size,
            max_pages_per_domain=max_pages_per_domain,
            now=current,
        )
    except Exception as exc:
        db.rollback()
        _finish_sync_lease(
            db,
            workspace_id=workspace.id,
            cycle=None,
            error=_safe_error(exc),
            now=current,
        )
        raise
    _finish_sync_lease(
        db,
        workspace_id=workspace.id,
        cycle=cycle,
        error=(None if cycle.status in {"succeeded", "skipped"} else "External clinic sync requires retry or review."),
        now=current,
    )
    return cycle


def run_scheduled_sync_tick(
    db: Session,
    *,
    workspace: Workspace,
    page_size: int = 100,
    max_pages_per_domain: int = 10,
    now: datetime | None = None,
) -> ClinicSyncWorkerTickResponse:
    current = _utc(now)
    try:
        _, reason = _claim_sync_lease(db, workspace=workspace, now=current, force=False)
    except Exception as exc:
        db.rollback()
        message = _safe_error(exc)
        _record_schedule_claim_failure(
            db,
            workspace_id=workspace.id,
            error=message,
            now=current,
        )
        return ClinicSyncWorkerTickResponse(claimed=False, reason=message)
    if reason:
        db.rollback()
        return ClinicSyncWorkerTickResponse(claimed=False, reason=reason)

    try:
        cycle = run_sync_cycle(
            db,
            workspace=workspace,
            page_size=page_size,
            max_pages_per_domain=max_pages_per_domain,
            now=current,
        )
    except Exception as exc:
        db.rollback()
        message = _safe_error(exc)
        _finish_sync_lease(
            db,
            workspace_id=workspace.id,
            cycle=None,
            error=message,
            now=current,
        )
        return ClinicSyncWorkerTickResponse(claimed=True, reason=message)

    _finish_sync_lease(
        db,
        workspace_id=workspace.id,
        cycle=cycle,
        error=(None if cycle.status in {"succeeded", "skipped"} else "External clinic sync requires retry or review."),
        now=current,
    )
    return ClinicSyncWorkerTickResponse(claimed=True, cycle=cycle)
