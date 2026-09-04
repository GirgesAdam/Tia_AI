from datetime import UTC, datetime

from app.core.automation_rules import DEFAULT_AUTOMATION_RULES, scheduled_for


def test_default_rules_cover_core_clinic_automations() -> None:
    keys = {rule.key for rule in DEFAULT_AUTOMATION_RULES}
    assert keys == {
        "booking_confirmation",
        "appointment_reminder_6h",
        "post_visit_followup",
        "cancellation_recovery",
        "lead_not_booked_followup",
        "no_show_followup",
    }


def test_6_hour_reminder_is_scheduled_before_appointment() -> None:
    start = datetime(2026, 8, 20, 18, 0, tzinfo=UTC)
    created = datetime(2026, 8, 15, 12, 0, tzinfo=UTC)

    when = scheduled_for(
        trigger_kind="before_appointment",
        offset_minutes=-360,
        appointment_created_at=created,
        appointment_start_at=start,
        completed_at=None,
        no_show_at=None,
    )

    assert when == datetime(2026, 8, 20, 12, 0, tzinfo=UTC)


def test_no_show_followup_is_30_minutes_after_no_show() -> None:
    no_show = datetime(2026, 8, 20, 18, 0, tzinfo=UTC)

    when = scheduled_for(
        trigger_kind="after_no_show",
        offset_minutes=30,
        appointment_created_at=no_show,
        appointment_start_at=no_show,
        completed_at=None,
        no_show_at=no_show,
    )

    assert when == datetime(2026, 8, 20, 18, 30, tzinfo=UTC)
