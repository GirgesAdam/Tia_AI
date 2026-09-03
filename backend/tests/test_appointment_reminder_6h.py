from datetime import UTC, datetime
from pathlib import Path

from app.core.automation_rules import DEFAULT_AUTOMATION_RULES, scheduled_for


def _root() -> Path:
    return Path(__file__).resolve().parents[2]


def test_default_lifecycle_has_one_six_hour_reminder_only() -> None:
    rules = {rule.key: rule for rule in DEFAULT_AUTOMATION_RULES}

    assert "appointment_reminder_24h" not in rules
    assert "appointment_reminder_2h" not in rules

    reminder = rules["appointment_reminder_6h"]
    assert reminder.enabled_by_default is True
    assert reminder.trigger_kind == "before_appointment"
    assert reminder.offset_minutes == -360
    assert reminder.template_name == "tia_appointment_reminder_6h_ar"

    assert rules["post_visit_followup"].enabled_by_default is True


def test_six_hour_reminder_timing_and_post_visit_timing() -> None:
    start = datetime(2026, 9, 5, 18, 0, tzinfo=UTC)
    completed = datetime(2026, 9, 5, 19, 15, tzinfo=UTC)
    created = datetime(2026, 8, 25, 12, 0, tzinfo=UTC)

    reminder = scheduled_for(
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

    assert reminder == datetime(2026, 9, 5, 12, 0, tzinfo=UTC)
    assert post_visit == datetime(2026, 9, 6, 19, 15, tzinfo=UTC)


def test_migration_disables_old_reminders_cancels_jobs_and_materializes_6h() -> None:
    migration = (
        _root() / "backend/alembic/versions/0026_appointment_reminder_6h.py"
    ).read_text(encoding="utf-8")

    assert 'down_revision: str | Sequence[str] | None = "0025_auto_patient_lifecycle"' in migration
    assert "appointment_reminder_24h" in migration
    assert "appointment_reminder_2h" in migration
    assert "SET enabled = FALSE" in migration
    assert "superseded_by_6h_reminder" in migration
    assert "UPDATE message_dispatches" in migration
    assert "UPDATE messages" in migration
    assert "status = 'dispatched'" in migration
    assert "appointment_reminder_6h" in migration
    assert "offset_minutes = -360" in migration
    assert "tia_appointment_reminder_6h_ar" in migration


def test_six_hour_fallback_copy_is_natural_and_post_visit_is_preserved() -> None:
    service = (_root() / "backend/app/services/automations.py").read_text(encoding="utf-8")

    assert 'rule_key == "appointment_reminder_6h"' in service
    assert "فاضل حوالي 6 ساعات" in service
    assert "مستنيينك 💛" in service
    assert "تعدّلي الموعد" not in service.split('if rule_key == "appointment_reminder_6h":', 1)[1].split('if rule_key == "appointment_reminder_24h":', 1)[0]
    assert "حبيت أطمن عليكي بعد {data['service_name']}" in service
    assert "كل حاجة تمام؟" in service


def test_automation_ui_labels_six_hour_rule() -> None:
    page = (_root() / "frontend/src/app/(dashboard)/automations/page.tsx").read_text(
        encoding="utf-8"
    )

    assert page.count("appointment_reminder_6h") >= 3
    assert 'rule.key === "appointment_reminder_6h"' in page



def test_setup_documents_six_hour_template_as_the_only_default_reminder() -> None:
    setup = (_root() / "n8n/AUTOMATIONS_SETUP.md").read_text(encoding="utf-8")

    assert "tia_appointment_reminder_6h_ar" in setup
    assert "قبل الموعد بـ 6 ساعات" in setup
    assert "v0.31.6" in setup
    six_hour_line = next(line for line in setup.splitlines() if "tia_appointment_reminder_6h_ar" in line and "أهلًا" in line)
    assert "تعدّلي الموعد" not in six_hour_line
    assert "مستنيينك 💛" in six_hour_line
    assert "{{3}}" in six_hour_line and "{{4}}" in six_hour_line
    assert "{{5}}" not in six_hour_line
    post_visit_line = next(line for line in setup.splitlines() if "tia_post_visit_followup_ar" in line and "إزيك" in line)
    assert "{{1}}" in post_visit_line and "{{2}}" in post_visit_line and "{{3}}" in post_visit_line
    assert "{{4}}" not in post_visit_line and "{{5}}" not in post_visit_line
    assert "الفرع" not in post_visit_line and "في {{" not in post_visit_line
    assert "24h and 2h reminder rules are disabled" in setup
