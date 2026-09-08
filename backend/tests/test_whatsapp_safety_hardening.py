from pathlib import Path
from types import SimpleNamespace

from app.schemas.crm import PatientCreate
from app.services.channels import (
    _provider_failure_is_permanent,
    _record_connection_provider_health,
    _whatsapp_dispatch_requires_opt_in,
)


def _root() -> Path:
    return Path(__file__).resolve().parents[2]


def test_whatsapp_opt_in_is_separate_and_defaults_off() -> None:
    patient = PatientCreate(first_name="Adam")
    assert patient.whatsapp_opt_in is False
    model = (_root() / "backend/app/models/patient.py").read_text(encoding="utf-8")
    assert "whatsapp_opt_in" in model
    assert "whatsapp_opt_in_at" in model
    assert "whatsapp_opt_in_source" in model


def test_customer_inbound_whatsapp_records_opt_in() -> None:
    service = (_root() / "backend/app/services/channels.py").read_text(encoding="utf-8")
    assert 'connection.channel == "whatsapp" and not patient.whatsapp_opt_in' in service
    assert 'patient.whatsapp_opt_in_source = "customer_inbound"' in service


def test_proactive_whatsapp_contract_requires_opt_in() -> None:
    connection = SimpleNamespace(channel="whatsapp")
    assert _whatsapp_dispatch_requires_opt_in(
        connection,
        SimpleNamespace(message_type="template", metadata_json={}),
    ) is True
    assert _whatsapp_dispatch_requires_opt_in(
        connection,
        SimpleNamespace(message_type="text", metadata_json={"source": "ai_followup"}),
    ) is True
    assert _whatsapp_dispatch_requires_opt_in(
        connection,
        SimpleNamespace(message_type="text", metadata_json={"source": "channel_adapter"}),
    ) is False


def test_meta_account_lock_pauses_only_the_connection() -> None:
    metadata = {"errors": [{"code": 131031, "title": "Business Account locked"}]}
    assert _provider_failure_is_permanent("Business Account locked", metadata) is True
    assert _provider_failure_is_permanent("temporary provider failure", {}) is False

    connection = SimpleNamespace(status="active", config_json={})
    permanent = _record_connection_provider_health(
        connection,
        provider_status="failed",
        error="Business Account locked",
        metadata=metadata,
    )
    assert permanent is True
    assert connection.status == "paused"
    assert connection.config_json["provider_health"]["state"] == "disabled"
    assert connection.config_json["provider_health"]["current_error_code"] == 131031
    assert connection.config_json["provider_health"]["action_required"] == "meta_account_review"


def test_paused_adapter_can_report_delivery_but_new_work_stays_blocked() -> None:
    service = (_root() / "backend/app/services/channels.py").read_text(encoding="utf-8")
    routes = (_root() / "backend/app/api/routes/channels.py").read_text(encoding="utf-8")
    assert 'ChannelConnection.status.in_(("active", "paused"))' in service
    assert "_require_active(adapter.connection)" in routes
    assert '"/adapter/outbox/provider-status"' in routes


def test_automation_ui_surfaces_provider_health_and_recovery() -> None:
    page = (_root() / "frontend/src/app/(dashboard)/automations/page.tsx").read_text(encoding="utf-8")
    actions = (_root() / "frontend/src/app/(dashboard)/automations/actions.ts").read_text(encoding="utf-8")
    assert "providerHealth" in page
    assert "متوقف تلقائيًا" in page
    assert "resumeWhatsappConnection" in page
    assert 'body: JSON.stringify({ status: "active" })' in actions


def test_whatsapp_safety_migration_is_current_head() -> None:
    migration = (_root() / "backend/alembic/versions/0058_whatsapp_safety.py").read_text(encoding="utf-8")
    readiness = (_root() / "backend/app/services/operational_readiness.py").read_text(encoding="utf-8")
    assert 'revision: str = "0058_whatsapp_safety"' in migration
    assert 'down_revision: str | Sequence[str] | None = "0057_expense_type"' in migration
    assert 'EXPECTED_MIGRATION_HEAD = "0060_whatsapp_direct_credentials"' in readiness
