from __future__ import annotations

import hashlib

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.integrations.clinic.authority import (
    ClinicIntegrationAuthorityError,
    domain_authority_owner,
    integration_authority_policy,
)
from app.integrations.clinic.mapped_sync import MappedClinicSyncSource
from app.integrations.clinic.registry import (
    ClinicAdapterConfigurationError,
    get_clinic_adapter,
    registered_clinic_adapter_keys,
)
from app.integrations.clinic.sync_contract import (
    ClinicRawSyncSource,
    ClinicSyncDomain,
    ClinicSyncSource,
)
from app.models.clinic_integration import ClinicIntegration, ClinicIntegrationEntityLink
from app.models.clinic_integration_sync import (
    ClinicIntegrationSyncCheckpoint,
    ClinicIntegrationSyncFailure,
    ClinicIntegrationSyncRun,
    ClinicIntegrationSyncSchedule,
)
from app.models.workspace import Workspace
from app.schemas.clinic_connector_mapping import ClinicSyncMapping
from app.schemas.clinic_integration import (
    ClinicIntegrationAuthorityRead,
    ClinicIntegrationRuntimeRead,
    ClinicSyncRuntimeDomainRead,
    ClinicSyncScheduleRead,
)


class ClinicIntegrationRuntimeError(RuntimeError):
    pass


def _cursor_digest(cursor: str | None) -> str | None:
    if not cursor:
        return None
    return hashlib.sha256(cursor.encode("utf-8")).hexdigest()[:16]


def _sync_domain_runtime(
    db: Session,
    *,
    integration: ClinicIntegration,
    domain: str,
) -> ClinicSyncRuntimeDomainRead:
    checkpoint = db.scalar(
        select(ClinicIntegrationSyncCheckpoint).where(
            ClinicIntegrationSyncCheckpoint.workspace_id == integration.workspace_id,
            ClinicIntegrationSyncCheckpoint.domain == domain,
        )
    )
    latest_run = db.scalar(
        select(ClinicIntegrationSyncRun)
        .where(
            ClinicIntegrationSyncRun.workspace_id == integration.workspace_id,
            ClinicIntegrationSyncRun.domain == domain,
        )
        .order_by(
            ClinicIntegrationSyncRun.completed_at.desc(),
            ClinicIntegrationSyncRun.started_at.desc(),
            ClinicIntegrationSyncRun.id.desc(),
        )
        .limit(1)
    )
    latest_failure = db.scalar(
        select(ClinicIntegrationSyncFailure)
        .where(
            ClinicIntegrationSyncFailure.workspace_id == integration.workspace_id,
            ClinicIntegrationSyncFailure.domain == domain,
        )
        .order_by(
            ClinicIntegrationSyncFailure.created_at.desc(),
            ClinicIntegrationSyncFailure.id.desc(),
        )
        .limit(1)
    )
    policy = integration_authority_policy(integration)[domain]
    return ClinicSyncRuntimeDomainRead(
        domain=domain,
        authority_owner=domain_authority_owner(integration, domain),
        authority_fields=dict(policy.get("fields") or {}),
        checkpoint_present=checkpoint is not None,
        cursor_digest=_cursor_digest(checkpoint.cursor if checkpoint else None),
        source_revision=checkpoint.source_revision if checkpoint else None,
        last_success_at=checkpoint.last_success_at if checkpoint else None,
        last_run_id=latest_run.id if latest_run else None,
        last_run_status=latest_run.status if latest_run else None,
        last_run_started_at=latest_run.started_at if latest_run else None,
        last_run_completed_at=latest_run.completed_at if latest_run else None,
        processed_count=latest_run.processed_count if latest_run else 0,
        created_count=latest_run.created_count if latest_run else 0,
        updated_count=latest_run.updated_count if latest_run else 0,
        skipped_count=latest_run.skipped_count if latest_run else 0,
        failed_count=latest_run.failed_count if latest_run else 0,
        latest_error_code=latest_failure.error_code if latest_failure else None,
        latest_error_message=latest_failure.message if latest_failure else None,
        latest_error_retryable=latest_failure.retryable if latest_failure else None,
        latest_error_at=latest_failure.created_at if latest_failure else None,
    )


def build_clinic_integration_runtime(
    db: Session,
    workspace: Workspace,
) -> ClinicIntegrationRuntimeRead:
    """Describe the live source-system boundary without exposing credentials or raw cursors."""
    integration = db.get(ClinicIntegration, workspace.id)
    if integration is None:
        raise ClinicIntegrationRuntimeError(
            "Clinic integration configuration is missing. Run database migrations."
        )

    installed = integration.adapter_key in registered_clinic_adapter_keys()
    capabilities: dict[str, bool] = {}
    cache_namespace: str | None = None
    sync_source_domains: list[str] = []
    adapter_active = bool(integration.status == "active" and installed)
    if adapter_active:
        try:
            adapter = get_clinic_adapter(db=db, workspace=workspace)
        except ClinicAdapterConfigurationError:
            adapter_active = False
        else:
            capabilities = adapter.capabilities.as_dict()
            cache_namespace = adapter.cache_namespace
            approved_mapping_raw = dict(getattr(integration, "config_json", None) or {}).get("approved_sync_mapping")
            approved_fingerprint = str(
                dict(getattr(integration, "config_json", None) or {}).get("approved_sync_schema_fingerprint") or ""
            ).strip()
            if approved_mapping_raw is not None and approved_fingerprint and isinstance(adapter, ClinicRawSyncSource):
                try:
                    approved_mapping = ClinicSyncMapping.model_validate(approved_mapping_raw)
                    mapped_source = MappedClinicSyncSource(
                        source=adapter,
                        mapping=approved_mapping,
                        schema_fingerprint_value=approved_fingerprint,
                    )
                    sync_source_domains = [
                        domain.value
                        for domain in (
                            ClinicSyncDomain.PATIENTS,
                            ClinicSyncDomain.APPOINTMENTS,
                            ClinicSyncDomain.PAYMENTS,
                        )
                        if domain in mapped_source.sync_domains
                    ]
                except (TypeError, ValueError):
                    adapter_active = False
            elif isinstance(adapter, ClinicSyncSource):
                sync_source_domains = [
                    domain.value
                    for domain in (
                        ClinicSyncDomain.PATIENTS,
                        ClinicSyncDomain.APPOINTMENTS,
                        ClinicSyncDomain.PAYMENTS,
                    )
                    if domain in adapter.sync_domains
                ]

    counts = {
        entity_type: int(count)
        for entity_type, count in db.execute(
            select(
                ClinicIntegrationEntityLink.entity_type,
                func.count(ClinicIntegrationEntityLink.id),
            )
            .where(ClinicIntegrationEntityLink.workspace_id == workspace.id)
            .group_by(ClinicIntegrationEntityLink.entity_type)
        ).all()
    }
    try:
        authority = integration_authority_policy(integration)
        sync_domains = (
            [
                _sync_domain_runtime(db, integration=integration, domain=domain)
                for domain in ("patients", "payments", "appointments")
            ]
            if callable(getattr(db, "scalar", None))
            else []
        )
    except ClinicIntegrationAuthorityError as exc:
        raise ClinicIntegrationRuntimeError(str(exc)) from exc

    schedule = db.get(ClinicIntegrationSyncSchedule, workspace.id)
    schedule_read = (
        ClinicSyncScheduleRead(
            enabled=bool(schedule.enabled),
            interval_minutes=int(schedule.interval_minutes),
            next_run_at=schedule.next_run_at,
            locked=schedule.locked_at is not None,
            locked_at=schedule.locked_at,
            attempts=int(schedule.attempts),
            last_error=schedule.last_error,
            last_completed_at=schedule.last_completed_at,
        )
        if schedule is not None
        else None
    )

    config_json = dict(getattr(integration, "config_json", None) or {})
    approved_mapping_raw = config_json.get("approved_sync_mapping")
    approved_fingerprint = str(config_json.get("approved_sync_schema_fingerprint") or "").strip()
    approved_mapping_domains: list[str] = []
    approved_mapping_active = False
    if approved_mapping_raw is not None and approved_fingerprint:
        try:
            approved_mapping = ClinicSyncMapping.model_validate(approved_mapping_raw)
        except (TypeError, ValueError):
            approved_mapping = None
        if approved_mapping is not None:
            approved_mapping_active = True
            approved_mapping_domains = [
                domain
                for domain, section in (
                    ("patients", approved_mapping.patients),
                    ("payments", approved_mapping.payments),
                    ("appointments", approved_mapping.appointments),
                )
                if section is not None
            ]

    return ClinicIntegrationRuntimeRead(
        mode=integration.mode,
        adapter_key=integration.adapter_key,
        status=integration.status,
        adapter_installed=installed,
        adapter_active=adapter_active,
        cache_namespace=cache_namespace,
        capabilities=capabilities,
        entity_link_counts=counts,
        authority_policy=ClinicIntegrationAuthorityRead.model_validate(authority),
        sync_domains=sync_domains,
        sync_source_domains=sync_source_domains,
        approved_mapping_active=approved_mapping_active,
        approved_mapping_domains=approved_mapping_domains,
        approved_schema_fingerprint_digest=(
            hashlib.sha256(approved_fingerprint.encode("utf-8")).hexdigest()[:16]
            if approved_fingerprint else None
        ),
        sync_schedule=schedule_read,
        data_quality=dict(config_json.get("data_quality") or {}),
    )
