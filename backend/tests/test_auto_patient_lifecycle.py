import json
from datetime import UTC, datetime
from pathlib import Path

from app.core.automation_rules import DEFAULT_AUTOMATION_RULES, scheduled_for


def _root() -> Path:
    return Path(__file__).resolve().parents[2]


def test_patient_lifecycle_rules_are_automatic_by_default() -> None:
    rules = {rule.key: rule for rule in DEFAULT_AUTOMATION_RULES}
    assert rules["appointment_reminder_6h"].enabled_by_default is True
    assert "appointment_reminder_24h" not in rules
    assert "appointment_reminder_2h" not in rules
    assert rules["post_visit_followup"].enabled_by_default is True
    assert rules["booking_confirmation"].enabled_by_default is False
    assert rules["no_show_followup"].enabled_by_default is False


def test_lifecycle_timing_is_6h_and_one_day_after_real_completion() -> None:
    start = datetime(2026, 9, 5, 18, 0, tzinfo=UTC)
    completed = datetime(2026, 9, 5, 19, 15, tzinfo=UTC)
    created = datetime(2026, 8, 25, 12, 0, tzinfo=UTC)

    reminder_6h = scheduled_for(
        trigger_kind="before_appointment",
        offset_minutes=-360,
        appointment_created_at=created,
        appointment_start_at=start,
        completed_at=None,
        no_show_at=None,
    )
    post_visit = scheduled_for(
        trigger_kind="after_completed",
        offset_minutes=1440,
        appointment_created_at=created,
        appointment_start_at=start,
        completed_at=completed,
        no_show_at=None,
    )

    assert reminder_6h == datetime(2026, 9, 5, 12, 0, tzinfo=UTC)
    assert post_visit == datetime(2026, 9, 6, 19, 15, tzinfo=UTC)


def test_existing_workspaces_are_migrated_to_six_hour_policy() -> None:
    migration = (_root() / "backend/alembic/versions/0026_appointment_reminder_6h.py").read_text(
        encoding="utf-8"
    )
    assert 'down_revision: str | Sequence[str] | None = "0025_auto_patient_lifecycle"' in migration
    assert "appointment_reminder_24h" in migration
    assert "appointment_reminder_2h" in migration
    assert "appointment_reminder_6h" in migration
    assert "SET enabled = FALSE" in migration
    assert "offset_minutes = -360" in migration


def test_new_workspaces_materialize_rules_using_definition_default() -> None:
    service = (_root() / "backend/app/services/automations.py").read_text(encoding="utf-8")
    assert "enabled=definition.enabled_by_default" in service


def test_appointment_templates_use_rule_specific_db_owned_parameters() -> None:
    service = (_root() / "backend/app/services/automations.py").read_text(encoding="utf-8")
    assert "def _appointment_template_body_parameters(rule_key: str, data: dict)" in service
    assert 'rule_key == "appointment_reminder_6h"' in service
    assert 'return [patient_name, service_name, time, branch_name]' in service
    assert 'rule_key == "post_visit_followup"' in service
    assert 'return [patient_name, service_name, date]' in service
    assert '"body_parameters": _appointment_template_body_parameters(rule.key, display)' in service


def test_lifecycle_message_copy_is_natural_and_post_visit_asks_one_clear_question() -> None:
    service = (_root() / "backend/app/services/automations.py").read_text(encoding="utf-8")
    assert "فاضل حوالي 6 ساعات" in service
    assert "حبيت أطمن عليكي بعد {data['service_name']}" in service
    assert "كل حاجة تمام؟" in service


def test_n8n_outbox_supports_three_four_and_five_parameter_templates() -> None:
    workflow = json.loads(
        (_root() / "n8n/workflows/tia_whatsapp_outbox_worker.json").read_text(encoding="utf-8")
    )
    for count in (3, 4, 5):
        node = next(
            row for row in workflow["nodes"]
            if row["name"] == f"WhatsApp Send Template {count} Params"
        )
        params = node["parameters"]["components"]["component"][0]["bodyParameters"]["parameter"]
        assert len(params) == count
        for index, param in enumerate(params):
            assert param["type"] == "text"
            assert f"body_parameters?.[{index}]" in param["text"]


def test_setup_documents_exact_template_contract_and_natural_care_messages() -> None:
    setup = (_root() / "n8n/AUTOMATIONS_SETUP.md").read_text(encoding="utf-8")
    assert "exact number of positional body parameters" in setup
    assert "**4 parameters**" in setup
    assert "**3 parameters**" in setup
    assert "tia_appointment_reminder_6h_ar" in setup
    assert "tia_post_visit_followup_ar" in setup
    assert "enabled by default in v0.31.6" in setup
    assert "completed_at" in setup


def test_customer_reply_after_proactive_message_still_uses_normal_agent_runtime() -> None:
    channels = (_root() / "backend/app/services/channels.py").read_text(encoding="utf-8")
    assert "run_agent_for_existing_inbound(" in channels
    assert "return_to_ai(conversation, now=now)" in channels


def test_reenabled_lifecycle_rule_can_revive_only_lifecycle_cancelled_jobs() -> None:
    service = (_root() / "backend/app/services/automations.py").read_text(encoding="utf-8")
    assert "REPLANNABLE_CANCELLATION_REASONS" in service
    assert '"rule_disabled_by_admin"' in service
    assert '"rule_disabled_or_appointment_no_longer_eligible"' in service
    assert "_cancelled_job_can_be_replanned(existing)" in service
    assert "existing.message_id = None" in service
    assert "existing.dispatch_id = None" in service
