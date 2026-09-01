from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace
from uuid import uuid4

import pytest
from pydantic import ValidationError

from app.integrations.clinic.configuration import (
    DEFAULT_CLINIC_ADAPTER_KEY,
    get_clinic_integration_config,
)
from app.integrations.clinic.registry import (
    ClinicAdapterConfigurationError,
    get_clinic_adapter,
)
from app.integrations.clinic.tia_database import TiaDatabaseClinicAdapter
from app.models.clinic_integration import ClinicIntegration
from app.schemas.clinic_integration import ClinicIntegrationUpsert


def test_missing_config_keeps_existing_workspace_tia_native_during_rollout() -> None:
    workspace_id = uuid4()

    class _Db:
        @staticmethod
        def get(model, identity):
            assert model is ClinicIntegration
            assert identity == workspace_id
            return None

    config = get_clinic_integration_config(db=_Db(), workspace_id=workspace_id)

    assert config.adapter_key == DEFAULT_CLINIC_ADAPTER_KEY
    assert config.mode == "tia_native"
    assert config.status == "active"
    assert config.persisted is False


def test_active_native_workspace_resolves_tia_database_adapter() -> None:
    workspace = SimpleNamespace(id=uuid4())
    integration = SimpleNamespace(
        workspace_id=workspace.id,
        mode="tia_native",
        adapter_key="tia_database",
        status="active",
        external_clinic_id=None,
        secret_ref=None,
        config_json={},
    )

    class _Db:
        @staticmethod
        def get(model, identity):
            assert model is ClinicIntegration
            assert identity == workspace.id
            return integration

    adapter = get_clinic_adapter(db=_Db(), workspace=workspace)
    assert isinstance(adapter, TiaDatabaseClinicAdapter)


def test_inactive_workspace_integration_fails_closed() -> None:
    workspace = SimpleNamespace(id=uuid4())
    integration = SimpleNamespace(
        workspace_id=workspace.id,
        mode="external_api",
        adapter_key="future_clinic_api",
        status="setup_required",
        external_clinic_id="CLINIC-77",
        secret_ref="vault://clinics/77",
        config_json={"base_url": "https://clinic.example/api"},
    )

    class _Db:
        @staticmethod
        def get(_model, _identity):
            return integration

    with pytest.raises(ClinicAdapterConfigurationError, match="not active"):
        get_clinic_adapter(db=_Db(), workspace=workspace)


def test_unknown_active_adapter_never_silently_falls_back_to_tia_database() -> None:
    workspace = SimpleNamespace(id=uuid4())
    integration = SimpleNamespace(
        workspace_id=workspace.id,
        mode="external_api",
        adapter_key="future_clinic_api",
        status="active",
        external_clinic_id="CLINIC-77",
        secret_ref="vault://clinics/77",
        config_json={},
    )

    class _Db:
        @staticmethod
        def get(_model, _identity):
            return integration

    with pytest.raises(ClinicAdapterConfigurationError, match="not installed"):
        get_clinic_adapter(db=_Db(), workspace=workspace)


def test_external_adapter_can_be_saved_as_setup_required_before_it_is_installed() -> None:
    payload = ClinicIntegrationUpsert(
        mode="external_api",
        adapter_key="clinic_xyz_api",
        status="setup_required",
        external_clinic_id="XYZ-1",
        secret_ref="vault://tia/clinic-xyz",
        config={"base_url": "https://example.invalid/v1", "timeout_seconds": 10},
    )

    assert payload.adapter_key == "clinic_xyz_api"
    assert payload.status == "setup_required"


def test_unknown_adapter_cannot_be_marked_active() -> None:
    with pytest.raises(ValidationError, match="cannot be active"):
        ClinicIntegrationUpsert(
            mode="external_api",
            adapter_key="not_installed",
            status="active",
        )


def test_plain_config_rejects_embedded_secrets() -> None:
    with pytest.raises(ValidationError, match="cannot contain credentials or secrets"):
        ClinicIntegrationUpsert(
            mode="external_api",
            adapter_key="future_api",
            status="setup_required",
            config={"api_key": "do-not-store-this"},
        )


def test_native_and_imported_modes_use_tia_database_adapter() -> None:
    native = ClinicIntegrationUpsert(
        mode="tia_native",
        adapter_key="tia_database",
        status="active",
    )
    imported = ClinicIntegrationUpsert(
        mode="imported",
        adapter_key="tia_database",
        status="active",
    )
    assert native.adapter_key == imported.adapter_key == "tia_database"

    with pytest.raises(ValidationError, match="requires adapter_key='tia_database'"):
        ClinicIntegrationUpsert(
            mode="imported",
            adapter_key="spreadsheet_runtime",
            status="setup_required",
        )


def test_migration_backfills_existing_workspaces_as_native() -> None:
    backend = Path(__file__).resolve().parent.parent
    source = (backend / "alembic/versions/0015_clinic_integrations.py").read_text(
        encoding="utf-8"
    )

    assert "CREATE" not in source  # migration stays in Alembic operations/text, not raw DDL
    assert "INSERT INTO clinic_integrations" in source
    assert "SELECT id, 'tia_native', 'tia_database', 'active'" in source
    assert "clinic_integration_entity_links" in source


def test_registry_reads_configuration_by_workspace_primary_key() -> None:
    backend = Path(__file__).resolve().parent.parent
    source = (
        backend / "app/integrations/clinic/configuration.py"
    ).read_text(encoding="utf-8")
    model_source = (backend / "app/models/clinic_integration.py").read_text(encoding="utf-8")

    assert "get(ClinicIntegration, workspace_id)" in source
    assert 'primary_key=True' in model_source


def test_new_workspace_creation_persists_native_integration_row() -> None:
    backend = Path(__file__).resolve().parent.parent
    source = (backend / "app/api/routes/onboarding.py").read_text(encoding="utf-8")

    assert "integration = ClinicIntegration(" in source
    assert 'mode="tia_native"' in source
    assert 'adapter_key="tia_database"' in source
    assert 'status="active"' in source
