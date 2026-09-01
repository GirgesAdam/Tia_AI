from __future__ import annotations

from collections.abc import Callable

from sqlalchemy.orm import Session

from app.integrations.clinic.base import ClinicAdapter
from app.integrations.clinic.configuration import (
    ClinicIntegrationConfig,
    get_clinic_integration_config,
    get_external_entity_id,
)
from app.models.workspace import Workspace


class ClinicAdapterConfigurationError(RuntimeError):
    """Raised when a workspace integration cannot be resolved safely."""


AdapterFactory = Callable[..., ClinicAdapter]


def _tia_database_factory(
    *, db: Session, workspace: Workspace, integration: ClinicIntegrationConfig
) -> ClinicAdapter:
    from app.integrations.clinic.tia_database import TiaDatabaseClinicAdapter

    return TiaDatabaseClinicAdapter(db=db, workspace=workspace)


def _prototype_external_factory(
    *, db: Session, workspace: Workspace, integration: ClinicIntegrationConfig
) -> ClinicAdapter:
    from app.integrations.clinic.prototype_external import (
        PrototypeExternalClinicAdapter,
        PrototypeExternalConfigurationError,
    )

    try:
        return PrototypeExternalClinicAdapter(
            workspace_timezone=workspace.timezone,
            external_clinic_id=integration.external_clinic_id,
            config=integration.config,
            resolve_patient_external_id=lambda canonical_id: get_external_entity_id(
                db=db,
                workspace_id=workspace.id,
                entity_type="patient",
                canonical_id=canonical_id,
            ),
        )
    except PrototypeExternalConfigurationError as exc:
        raise ClinicAdapterConfigurationError(str(exc)) from exc


def _postgres_readonly_factory(
    *, db: Session, workspace: Workspace, integration: ClinicIntegrationConfig
) -> ClinicAdapter:
    from app.integrations.clinic.postgres_readonly import (
        PostgresReadonlyConnectorError,
        build_postgres_readonly_adapter,
    )

    try:
        native_delegate = _tia_database_factory(
            db=db, workspace=workspace, integration=integration
        ) if integration.mode == "hybrid" else None
        return build_postgres_readonly_adapter(
            secret_ref=integration.secret_ref,
            config=integration.config,
            native_delegate=native_delegate,
        )
    except PostgresReadonlyConnectorError as exc:
        raise ClinicAdapterConfigurationError(str(exc)) from exc


_ADAPTER_FACTORIES: dict[str, AdapterFactory] = {
    "tia_database": _tia_database_factory,
    "prototype_external": _prototype_external_factory,
    "postgres_readonly": _postgres_readonly_factory,
}


def registered_clinic_adapter_keys() -> frozenset[str]:
    return frozenset(_ADAPTER_FACTORIES)


def build_clinic_adapter(
    *, db: Session, workspace: Workspace, integration: ClinicIntegrationConfig
) -> ClinicAdapter:
    """Instantiate one installed adapter from an explicit non-secret configuration."""

    factory = _ADAPTER_FACTORIES.get(integration.adapter_key)
    if factory is None:
        raise ClinicAdapterConfigurationError(
            "Clinic adapter is not installed for this workspace: "
            f"{integration.adapter_key!r}."
        )
    return factory(db=db, workspace=workspace, integration=integration)


def get_clinic_adapter(*, db: Session, workspace: Workspace) -> ClinicAdapter:
    """Resolve the configured clinic-system adapter for one workspace.

    Resolution fails closed. If a workspace is configured for an unavailable,
    paused, or not-yet-implemented external source, Tia must not silently fall
    back to its local PostgreSQL booking data and risk reading/writing the wrong
    source of truth.
    """

    integration = get_clinic_integration_config(db=db, workspace_id=workspace.id)
    if not integration.is_active:
        raise ClinicAdapterConfigurationError(
            "Clinic integration is not active "
            f"(status={integration.status!r}, mode={integration.mode!r})."
        )
    return build_clinic_adapter(db=db, workspace=workspace, integration=integration)
