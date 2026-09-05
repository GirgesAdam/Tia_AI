from datetime import UTC, datetime
from pathlib import Path

from app.core.automation_rules import DEFAULT_AUTOMATION_RULES, scheduled_for
from app.services.automations import _appointment_template_body_parameters


def _root() -> Path:
    return Path(__file__).resolve().parents[2]


def test_cancellation_recovery_is_optional_and_uses_cancelled_at() -> None:
    rules = {rule.key: rule for rule in DEFAULT_AUTOMATION_RULES}
    rule = rules["cancellation_recovery"]
    assert rule.enabled_by_default is False
    assert rule.trigger_kind == "after_cancelled"
    assert rule.offset_minutes == 60
    cancelled_at = datetime(2026, 9, 4, 12, 0, tzinfo=UTC)
    when = scheduled_for(
        trigger_kind=rule.trigger_kind,
        offset_minutes=rule.offset_minutes,
        appointment_created_at=cancelled_at,
        appointment_start_at=cancelled_at,
        completed_at=None,
        no_show_at=None,
        cancelled_at=cancelled_at,
    )
    assert when == datetime(2026, 9, 4, 13, 0, tzinfo=UTC)


def test_cancellation_recovery_reuses_existing_appointment_engine() -> None:
    service = (_root() / "backend/app/services/automations.py").read_text(encoding="utf-8")
    assert 'rule.trigger_kind == "after_cancelled"' in service
    assert 'Appointment.status == "cancelled"' in service
    assert "Appointment.cancelled_at >= oldest" in service
    assert "CancellationRecovery" not in service
    assert "cancellation_recovery_state" not in service


def test_cancellation_recovery_template_contract_is_four_simple_variables() -> None:
    assert _appointment_template_body_parameters(
        "cancellation_recovery",
        {
            "patient_name": "سارة",
            "service_name": "ليزر",
            "date": "04/09/2026",
            "time": "18:00",
            "branch_name": "العيادة",
        },
    ) == ["سارة", "ليزر", "04/09/2026", "18:00"]


def test_cancellation_recovery_is_admin_visible_and_timing_configurable() -> None:
    page = (_root() / "frontend/src/app/(dashboard)/automations/page.tsx").read_text(encoding="utf-8")
    assert 'cancellation_recovery: "استرجاع الحجوزات الملغاة"' in page
    assert 'rule.trigger_kind === "after_cancelled"' in page


def test_migration_only_extends_automation_trigger_constraint() -> None:
    migration = (_root() / "backend/alembic/versions/0054_cancel_recovery.py").read_text(encoding="utf-8")
    assert 'revision: str = "0054_cancel_recovery"' in migration
    assert 'down_revision: str | Sequence[str] | None = "0053_public_table_rls_completion"' in migration
    assert "automation_rule_trigger_kind_valid" in migration
    assert "after_cancelled" in migration
    assert "create_table" not in migration
    assert "add_column" not in migration
