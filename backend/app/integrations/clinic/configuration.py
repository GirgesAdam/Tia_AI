from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any
from uuid import UUID

from sqlalchemy.orm import Session

from app.models.clinic_integration import ClinicIntegration

DEFAULT_CLINIC_ADAPTER_KEY = "tia_database"
DEFAULT_CLINIC_INTEGRATION_MODE = "tia_native"
DEFAULT_CLINIC_INTEGRATION_STATUS = "active"


@dataclass(frozen=True)
class ClinicIntegrationConfig:
    workspace_id: UUID
    mode: str = DEFAULT_CLINIC_INTEGRATION_MODE
    adapter_key: str = DEFAULT_CLINIC_ADAPTER_KEY
    status: str = DEFAULT_CLINIC_INTEGRATION_STATUS
    external_clinic_id: str | None = None
    secret_ref: str | None = None
    config: dict[str, Any] = field(default_factory=dict)
    persisted: bool = True

    @property
    def is_active(self) -> bool:
        return self.status == "active"


def default_clinic_integration_config(workspace_id: UUID) -> ClinicIntegrationConfig:
    """Backward-compatible native config used before/without the migration row.

    Existing workspaces are backfilled by Alembic. The fallback keeps unit-test
    doubles and rolling deployments safe while the database migration and app
    release cross over.
    """

    return ClinicIntegrationConfig(
        workspace_id=workspace_id,
        persisted=False,
    )


def get_clinic_integration_config(
    *, db: Session, workspace_id: UUID
) -> ClinicIntegrationConfig:
    # ``Session.get`` is intentional: workspace_id is the table PK, so repeated
    # adapter resolution in the same Session can be served from the identity map.
    get = getattr(db, "get", None)
    if get is None:
        return default_clinic_integration_config(workspace_id)

    integration = get(ClinicIntegration, workspace_id)
    if integration is None:
        return default_clinic_integration_config(workspace_id)

    return ClinicIntegrationConfig(
        workspace_id=integration.workspace_id,
        mode=integration.mode,
        adapter_key=integration.adapter_key,
        status=integration.status,
        external_clinic_id=integration.external_clinic_id,
        secret_ref=integration.secret_ref,
        config=dict(integration.config_json or {}),
        persisted=True,
    )


def get_external_entity_id(
    *,
    db: Session,
    workspace_id: UUID,
    entity_type: str,
    canonical_id: str,
) -> str | None:
    from sqlalchemy import select

    from app.models.clinic_integration import ClinicIntegrationEntityLink

    return db.scalar(
        select(ClinicIntegrationEntityLink.external_id).where(
            ClinicIntegrationEntityLink.workspace_id == workspace_id,
            ClinicIntegrationEntityLink.entity_type == entity_type,
            ClinicIntegrationEntityLink.canonical_id == canonical_id,
        )
    )


def get_canonical_entity_id(
    *,
    db: Session,
    workspace_id: UUID,
    entity_type: str,
    external_id: str,
) -> str | None:
    from sqlalchemy import select

    from app.models.clinic_integration import ClinicIntegrationEntityLink

    return db.scalar(
        select(ClinicIntegrationEntityLink.canonical_id).where(
            ClinicIntegrationEntityLink.workspace_id == workspace_id,
            ClinicIntegrationEntityLink.entity_type == entity_type,
            ClinicIntegrationEntityLink.external_id == external_id,
        )
    )
