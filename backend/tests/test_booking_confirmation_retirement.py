from pathlib import Path

from app.core.automation_rules import DEFAULT_AUTOMATION_RULES
from app.core.meta_whatsapp_templates import STANDARD_WHATSAPP_TEMPLATES


def _root() -> Path:
    return Path(__file__).resolve().parents[2]


def test_booking_confirmation_is_not_an_automation_or_standard_template() -> None:
    assert "booking_confirmation" not in {rule.key for rule in DEFAULT_AUTOMATION_RULES}
    assert "booking_confirmation" not in {
        template.rule_key for template in STANDARD_WHATSAPP_TEMPLATES
    }


def test_successful_booking_is_confirmed_by_the_ai_response() -> None:
    source = (_root() / "backend/app/services/agent_chat.py").read_text(encoding="utf-8")
    assert "format_booking_success(appointment)" in source
    assert 'sender_type="ai"' in source


def test_retirement_migration_disables_rule_and_cancels_only_unsent_work() -> None:
    migration = (
        _root()
        / "backend/alembic/versions/0063_retire_booking_confirmation_automation.py"
    ).read_text(encoding="utf-8")

    assert "WHERE key = 'booking_confirmation'" in migration
    assert "SET enabled = FALSE" in migration
    assert "dispatch.status = 'queued'" in migration
    assert "message.delivery_status = 'queued'" in migration
    assert "job.status IN ('queued', 'failed', 'processing')" in migration
    assert "booking_confirmation_retired" in migration
    assert "status = 'sent'" not in migration
    assert "status = 'delivered'" not in migration
