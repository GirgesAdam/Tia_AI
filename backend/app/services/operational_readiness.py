from __future__ import annotations

from datetime import datetime, timedelta, timezone
from uuid import UUID

from sqlalchemy import func, select, text
from sqlalchemy.orm import Session

from app.core.config import settings
from app.models.automation_job import AutomationJob
from app.models.automation_rule import AutomationRule
from app.models.automation_worker import AutomationWorker
from app.models.booking_settings import BookingSettings
from app.models.branch import Branch
from app.models.channel_connection import ChannelConnection
from app.models.conversation_flow_state import ConversationFlowState
from app.models.doctor import Doctor
from app.models.handoff_request import HandoffRequest
from app.models.message_dispatch import MessageDispatch
from app.models.onboarding_ai_session import OnboardingAISession
from app.models.service import Service
from app.models.workspace_member import WorkspaceMember
from app.schemas.operations import OperationalCheck, WorkspaceOperationalReadiness


EXPECTED_MIGRATION_HEAD = "0013_ai_onboarding_sessions"
STALE_LOCK_MINUTES = 15
AUTOMATION_WORKER_HEARTBEAT_MINUTES = 5
TEST_RULE_KEY_PREFIXES = ("staging_regression_", "final_gate_")
TEST_DEDUPE_PREFIXES = ("staging-regression:", "final-gate-")
TEST_WORKER_NAME_PREFIXES = ("Regression ", "Final Gate ")
TEST_PAYLOAD_MARKERS = frozenset(
    {
        "final-gate",
        "final-gate-stale",
        "staging-regression",
        "tia-full-staging-regression",
    }
)


def _count(db: Session, stmt) -> int:
    return int(db.scalar(stmt) or 0)


def _check(
    checks: list[OperationalCheck],
    *,
    key: str,
    severity: str,
    message: str,
    value=None,
    details: dict | None = None,
) -> None:
    checks.append(
        OperationalCheck(
            key=key,
            severity=severity,
            message=message,
            value=value,
            details=details or {},
        )
    )


def _is_explicit_test_rule(rule: AutomationRule) -> bool:
    return rule.key.startswith(TEST_RULE_KEY_PREFIXES)


def _is_explicit_test_worker(worker: AutomationWorker) -> bool:
    return worker.name.startswith(TEST_WORKER_NAME_PREFIXES)


def _is_explicit_test_job(job: AutomationJob) -> bool:
    marker = None
    if isinstance(job.payload_json, dict):
        marker = job.payload_json.get("marker")
    return bool(
        job.dedupe_key.startswith(TEST_DEDUPE_PREFIXES)
        or marker in TEST_PAYLOAD_MARKERS
    )


def build_workspace_operational_readiness(
    db: Session,
    *,
    workspace_id: UUID,
) -> WorkspaceOperationalReadiness:
    now = datetime.now(timezone.utc)
    stale_before = now - timedelta(minutes=STALE_LOCK_MINUTES)
    worker_fresh_after = now - timedelta(
        minutes=AUTOMATION_WORKER_HEARTBEAT_MINUTES
    )
    recent_since = now - timedelta(hours=24)
    checks: list[OperationalCheck] = []

    migration_head = db.scalar(
        text("SELECT version_num FROM alembic_version LIMIT 1")
    )
    if migration_head == EXPECTED_MIGRATION_HEAD:
        _check(
            checks,
            key="database_migration",
            severity="pass",
            message="Database migration head is current.",
            value=migration_head,
        )
    else:
        _check(
            checks,
            key="database_migration",
            severity="fail",
            message=(
                f"Database migration head is {migration_head!s}; "
                f"expected {EXPECTED_MIGRATION_HEAD}."
            ),
            value=migration_head,
        )

    active_admins = _count(
        db,
        select(func.count())
        .select_from(WorkspaceMember)
        .where(
            WorkspaceMember.workspace_id == workspace_id,
            WorkspaceMember.role == "admin",
            WorkspaceMember.is_active.is_(True),
        ),
    )
    _check(
        checks,
        key="active_admins",
        severity="pass" if active_admins >= 1 else "fail",
        message=(
            f"Workspace has {active_admins} active admin(s)."
            if active_admins
            else "Workspace has no active admin."
        ),
        value=active_admins,
    )

    branches = _count(
        db,
        select(func.count())
        .select_from(Branch)
        .where(
            Branch.workspace_id == workspace_id,
            Branch.is_active.is_(True),
        ),
    )
    services = _count(
        db,
        select(func.count())
        .select_from(Service)
        .where(
            Service.workspace_id == workspace_id,
            Service.is_active.is_(True),
        ),
    )
    doctors = _count(
        db,
        select(func.count())
        .select_from(Doctor)
        .where(
            Doctor.workspace_id == workspace_id,
            Doctor.is_active.is_(True),
        ),
    )
    booking_settings = _count(
        db,
        select(func.count())
        .select_from(BookingSettings)
        .where(BookingSettings.workspace_id == workspace_id),
    )
    clinic_ready = (
        branches > 0
        and services > 0
        and doctors > 0
        and booking_settings > 0
    )
    _check(
        checks,
        key="clinic_configuration",
        severity="pass" if clinic_ready else "fail",
        message=(
            "Clinic has active branch/service/doctor configuration and "
            "booking settings."
            if clinic_ready
            else "Clinic configuration is incomplete."
        ),
        details={
            "branches": branches,
            "services": services,
            "doctors": doctors,
            "booking_settings": booking_settings,
        },
    )

    active_channel_rows = list(
        db.scalars(
            select(ChannelConnection).where(
                ChannelConnection.workspace_id == workspace_id,
                ChannelConnection.status == "active",
            )
        )
    )
    runtime_channels = [
        row
        for row in active_channel_rows
        if row.provider != "staging_mock"
        and not bool((row.config_json or {}).get("mock"))
        and not bool((row.config_json or {}).get("do_not_send"))
        and (row.config_json or {}).get("runtime_kind") == "real"
    ]
    test_channels = [row for row in active_channel_rows if row not in runtime_channels]
    _check(
        checks,
        key="active_channels",
        severity="pass" if runtime_channels else "warn",
        message=(
            f"{len(runtime_channels)} real external channel connection(s) active "
            f"({len(test_channels)} test/non-runtime connection(s) ignored)."
            if runtime_channels
            else "No real external channel connection is active; test/mock "
            "connections do not count as production runtime."
        ),
        value=len(runtime_channels),
        details={
            "real_runtime_channels": len(runtime_channels),
            "test_or_non_runtime_channels": len(test_channels),
            "runtime_providers": sorted({row.provider for row in runtime_channels}),
        },
    )

    enabled_rule_rows = list(
        db.scalars(
            select(AutomationRule).where(
                AutomationRule.workspace_id == workspace_id,
                AutomationRule.enabled.is_(True),
            )
        )
    )
    runtime_enabled_rules = [
        rule for rule in enabled_rule_rows if not _is_explicit_test_rule(rule)
    ]
    test_enabled_rules = [
        rule for rule in enabled_rule_rows if _is_explicit_test_rule(rule)
    ]

    if runtime_enabled_rules:
        automation_severity = "pass"
        automation_message = (
            f"{len(runtime_enabled_rules)} runtime automation rule(s) enabled "
            f"({len(test_enabled_rules)} explicit test rule(s) ignored)."
        )
    elif test_enabled_rules:
        automation_severity = "warn"
        automation_message = (
            "No runtime automation rule is enabled; "
            f"{len(test_enabled_rules)} explicit test rule(s) are enabled."
        )
    else:
        automation_severity = "warn"
        automation_message = "No automation rules are enabled."

    _check(
        checks,
        key="enabled_automations",
        severity=automation_severity,
        message=automation_message,
        value=len(runtime_enabled_rules),
        details={
            "runtime_enabled_rules": len(runtime_enabled_rules),
            "explicit_test_rules": len(test_enabled_rules),
        },
    )

    active_workers = list(
        db.scalars(
            select(AutomationWorker)
            .where(
                AutomationWorker.workspace_id == workspace_id,
                AutomationWorker.status == "active",
            )
            .order_by(AutomationWorker.last_seen_at.desc().nullslast())
        )
    )
    runtime_active_workers = [
        worker for worker in active_workers if not _is_explicit_test_worker(worker)
    ]
    test_active_workers = [
        worker for worker in active_workers if _is_explicit_test_worker(worker)
    ]
    fresh_runtime_workers = [
        worker
        for worker in runtime_active_workers
        if worker.last_seen_at is not None
        and worker.last_seen_at >= worker_fresh_after
    ]
    newest_runtime_seen = next(
        (
            worker.last_seen_at
            for worker in runtime_active_workers
            if worker.last_seen_at is not None
        ),
        None,
    )

    if not runtime_enabled_rules:
        worker_severity = "warn"
        worker_message = (
            "No runtime automation rule requires a production worker heartbeat. "
            f"Ignoring {len(test_active_workers)} explicit test worker(s)."
        )
    elif fresh_runtime_workers:
        worker_severity = "pass"
        worker_message = (
            f"{len(fresh_runtime_workers)} runtime automation worker(s) seen "
            f"within the last {AUTOMATION_WORKER_HEARTBEAT_MINUTES} minutes."
        )
    elif runtime_active_workers:
        worker_severity = "fail"
        worker_message = (
            "Runtime automation rules are enabled, but configured runtime "
            "worker(s) have no heartbeat within "
            f"{AUTOMATION_WORKER_HEARTBEAT_MINUTES} minutes. "
            "Verify the n8n automation scheduler is active."
        )
    else:
        worker_severity = "fail"
        worker_message = (
            "Runtime automation rules are enabled, but no active runtime "
            "automation worker is configured."
        )

    _check(
        checks,
        key="automation_worker_heartbeat",
        severity=worker_severity,
        message=worker_message,
        value=len(fresh_runtime_workers),
        details={
            "runtime_enabled_rules": len(runtime_enabled_rules),
            "explicit_test_rules": len(test_enabled_rules),
            "runtime_active_workers": len(runtime_active_workers),
            "explicit_test_workers": len(test_active_workers),
            "fresh_runtime_workers": len(fresh_runtime_workers),
            "fresh_within_minutes": AUTOMATION_WORKER_HEARTBEAT_MINUTES,
            "newest_runtime_last_seen_at": (
                newest_runtime_seen.isoformat()
                if newest_runtime_seen is not None
                else None
            ),
        },
    )

    stale_jobs = list(
        db.scalars(
            select(AutomationJob).where(
                AutomationJob.workspace_id == workspace_id,
                AutomationJob.status == "processing",
                AutomationJob.locked_at.is_not(None),
                AutomationJob.locked_at <= stale_before,
            )
        )
    )
    test_stale_jobs = [
        job for job in stale_jobs if _is_explicit_test_job(job)
    ]
    runtime_stale_jobs = [
        job for job in stale_jobs if not _is_explicit_test_job(job)
    ]

    if runtime_stale_jobs:
        stale_severity = "fail"
        stale_message = (
            f"{len(stale_jobs)} automation job(s) have stale processing locks "
            f"({len(runtime_stale_jobs)} runtime, "
            f"{len(test_stale_jobs)} explicit test artifact)."
        )
    elif test_stale_jobs:
        stale_severity = "warn"
        stale_message = (
            f"{len(test_stale_jobs)} stale automation job(s) are explicit "
            "staging/regression artifacts; no runtime stale job exists."
        )
    else:
        stale_severity = "pass"
        stale_message = "No stale automation processing locks."

    _check(
        checks,
        key="stuck_automation_jobs",
        severity=stale_severity,
        message=stale_message,
        value=len(runtime_stale_jobs),
        details={
            "stale_after_minutes": STALE_LOCK_MINUTES,
            "runtime_jobs": len(runtime_stale_jobs),
            "explicit_test_artifacts": len(test_stale_jobs),
            "automatic_reclaim_after_minutes": 10,
        },
    )

    failed_jobs = _count(
        db,
        select(func.count())
        .select_from(AutomationJob)
        .where(
            AutomationJob.workspace_id == workspace_id,
            AutomationJob.status == "failed",
            AutomationJob.updated_at >= recent_since,
        ),
    )
    _check(
        checks,
        key="failed_automation_jobs_24h",
        severity="warn" if failed_jobs else "pass",
        message=(
            f"{failed_jobs} failed automation job(s) in the last 24 hours."
        ),
        value=failed_jobs,
    )

    stuck_dispatches = _count(
        db,
        select(func.count())
        .select_from(MessageDispatch)
        .where(
            MessageDispatch.workspace_id == workspace_id,
            MessageDispatch.status == "processing",
            MessageDispatch.locked_at.is_not(None),
            MessageDispatch.locked_at <= stale_before,
        ),
    )
    _check(
        checks,
        key="stuck_message_dispatches",
        severity="fail" if stuck_dispatches else "pass",
        message=(
            f"{stuck_dispatches} message dispatch(es) have stale processing locks."
            if stuck_dispatches
            else "No stale message-dispatch processing locks."
        ),
        value=stuck_dispatches,
        details={"stale_after_minutes": STALE_LOCK_MINUTES},
    )

    failed_dispatches = _count(
        db,
        select(func.count())
        .select_from(MessageDispatch)
        .where(
            MessageDispatch.workspace_id == workspace_id,
            MessageDispatch.status == "failed",
            MessageDispatch.updated_at >= recent_since,
        ),
    )
    _check(
        checks,
        key="failed_dispatches_24h",
        severity="warn" if failed_dispatches else "pass",
        message=(
            f"{failed_dispatches} failed message dispatch(es) in the last 24 hours."
        ),
        value=failed_dispatches,
    )

    open_handoffs = _count(
        db,
        select(func.count())
        .select_from(HandoffRequest)
        .where(
            HandoffRequest.workspace_id == workspace_id,
            HandoffRequest.status.in_(("pending", "claimed")),
        ),
    )
    _check(
        checks,
        key="open_handoffs",
        severity="warn" if open_handoffs else "pass",
        message=f"{open_handoffs} open human handoff(s).",
        value=open_handoffs,
    )

    expired_active_flows = _count(
        db,
        select(func.count())
        .select_from(ConversationFlowState)
        .where(
            ConversationFlowState.workspace_id == workspace_id,
            ConversationFlowState.is_active.is_(True),
            ConversationFlowState.expires_at <= now,
        ),
    )
    _check(
        checks,
        key="expired_active_conversation_flows",
        severity="warn" if expired_active_flows else "pass",
        message=(
            f"{expired_active_flows} expired flow(s) are still marked active."
        ),
        value=expired_active_flows,
    )

    expired_onboarding = _count(
        db,
        select(func.count())
        .select_from(OnboardingAISession)
        .where(
            OnboardingAISession.workspace_id == workspace_id,
            OnboardingAISession.is_active.is_(True),
            OnboardingAISession.expires_at <= now,
        ),
    )
    failed_onboarding = _count(
        db,
        select(func.count())
        .select_from(OnboardingAISession)
        .where(
            OnboardingAISession.workspace_id == workspace_id,
            OnboardingAISession.status == "failed",
            OnboardingAISession.updated_at >= recent_since,
        ),
    )
    onboarding_issue = expired_onboarding + failed_onboarding
    _check(
        checks,
        key="ai_onboarding_runtime",
        severity="warn" if onboarding_issue else "pass",
        message=(
            f"{expired_onboarding} expired-active and {failed_onboarding} "
            "failed AI onboarding session(s) need review."
            if onboarding_issue
            else "AI onboarding session state is clean."
        ),
        details={
            "expired_active": expired_onboarding,
            "failed_24h": failed_onboarding,
        },
    )

    gemini_configured = bool(settings.gemini_api_key)
    _check(
        checks,
        key="gemini_configuration",
        severity="pass" if gemini_configured else "fail",
        message=(
            "Gemini API key is configured."
            if gemini_configured
            else "Gemini API key is not configured."
        ),
        value=gemini_configured,
    )

    fallback = settings.gemini_onboarding_fallback_model
    fallback_ok = bool(
        fallback
        and fallback != settings.gemini_onboarding_model
    )
    _check(
        checks,
        key="onboarding_provider_failover",
        severity="pass" if fallback_ok else "warn",
        message=(
            f"Onboarding failover configured: "
            f"{settings.gemini_onboarding_model} → {fallback}."
            if fallback_ok
            else "AI onboarding has no distinct fallback model configured."
        ),
        value=fallback_ok,
    )

    pass_count = sum(c.severity == "pass" for c in checks)
    warn_count = sum(c.severity == "warn" for c in checks)
    fail_count = sum(c.severity == "fail" for c in checks)

    status = (
        "not_ready"
        if fail_count
        else ("degraded" if warn_count else "ready")
    )

    return WorkspaceOperationalReadiness(
        status=status,
        workspace_id=str(workspace_id),
        checks=checks,
        pass_count=pass_count,
        warn_count=warn_count,
        fail_count=fail_count,
        provider={
            "provider": settings.llm_provider,
            "agent_model": settings.gemini_agent_model,
            "router_model": settings.gemini_router_model,
            "flow_model": settings.gemini_flow_model,
            "onboarding_primary_model": settings.gemini_onboarding_model,
            "onboarding_fallback_model": fallback,
            "onboarding_max_output_tokens": (
                settings.gemini_onboarding_max_output_tokens
            ),
        },
    )
