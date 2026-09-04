from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta


@dataclass(frozen=True)
class DefaultAutomationRule:
    key: str
    name: str
    trigger_kind: str
    offset_minutes: int
    channel: str
    template_name: str
    template_language: str
    max_lateness_minutes: int
    enabled_by_default: bool = False


DEFAULT_AUTOMATION_RULES: tuple[DefaultAutomationRule, ...] = (
    DefaultAutomationRule(
        key="booking_confirmation",
        name="Booking confirmation",
        trigger_kind="appointment_created",
        offset_minutes=0,
        channel="whatsapp",
        template_name="tia_booking_confirmation_ar",
        template_language="ar",
        max_lateness_minutes=60,
        enabled_by_default=False,
    ),
    DefaultAutomationRule(
        # Keep the historical key for database compatibility. Timing is admin-configurable.
        key="appointment_reminder_6h",
        name="Appointment reminder",
        trigger_kind="before_appointment",
        offset_minutes=-360,
        channel="whatsapp",
        template_name="tia_appointment_reminder_ar",
        template_language="ar",
        max_lateness_minutes=30,
        enabled_by_default=True,
    ),
    DefaultAutomationRule(
        key="post_visit_followup",
        name="Post-visit follow-up",
        trigger_kind="after_completed",
        offset_minutes=1440,
        channel="whatsapp",
        template_name="tia_post_visit_followup_ar",
        template_language="ar",
        max_lateness_minutes=1440,
        enabled_by_default=False,
    ),
    DefaultAutomationRule(
        key="no_show_followup",
        name="No-show recovery follow-up",
        trigger_kind="after_no_show",
        offset_minutes=30,
        channel="whatsapp",
        template_name="tia_no_show_followup_ar",
        template_language="ar",
        max_lateness_minutes=720,
        enabled_by_default=False,
    ),
)


def scheduled_for(
    *,
    trigger_kind: str,
    offset_minutes: int,
    appointment_created_at: datetime,
    appointment_start_at: datetime,
    completed_at: datetime | None,
    no_show_at: datetime | None,
) -> datetime | None:
    if trigger_kind == "appointment_created":
        anchor = appointment_created_at
    elif trigger_kind == "before_appointment":
        anchor = appointment_start_at
    elif trigger_kind == "after_completed":
        anchor = completed_at
    elif trigger_kind == "after_no_show":
        anchor = no_show_at
    else:
        return None

    if anchor is None:
        return None
    return anchor + timedelta(minutes=offset_minutes)
