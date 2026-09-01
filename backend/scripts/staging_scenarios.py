from __future__ import annotations

from uuid import UUID, uuid5

SEED_NAMESPACE = UUID("f99fab0a-17c5-47f3-8916-6b9cb043a3d1")
REGRESSION_WORKSPACE_ID = uuid5(SEED_NAMESPACE, "workspace:regression")
REGRESSION_WORKSPACE_SLUG = "tia-regression"


MOCK_CHANNEL_TOKEN = "tia_channel_staging_regression_v1"
MOCK_PAUSED_CHANNEL_TOKEN = "tia_channel_staging_paused_v1"
MOCK_AUTOMATION_TOKEN = "tia_auto_staging_regression_v1"

SEED_VERSION = "0.13.0"
SEED_MARKER = "tia-full-staging-regression"


def sid(workspace_id: UUID | str, name: str) -> UUID:
    return uuid5(SEED_NAMESPACE, f"{workspace_id}:{name}")


PATIENT_KEYS = (
    "active",
    "inactive",
    "blocked",
    "lead_new",
    "lead_qualified",
    "lead_lost",
    "booking_pending",
    "booking_confirmed",
    "booking_policy_cancel",
    "booking_lifecycle",
    "booking_reschedule",
    "booking_idempotent",
    "automation_success",
    "automation_no_route",
    "handoff_medical",
    "handoff_complaint",
    "handoff_resolved",
    "channel",
    "agent_booking",
)

APPOINTMENT_KEYS = (
    "pending",
    "confirmed",
    "policy_cancel",
    "lifecycle",
    "reschedule_source",
    "idempotent",
    "completed",
    "cancelled",
    "no_show",
    "rescheduled_old",
    "rescheduled_new",
    "checked_in",
    "in_progress",
    "automation_success",
    "automation_no_route",
    "automation_cancelled",
)

CONVERSATION_KEYS = (
    "web_open",
    "web_closed",
    "handoff_medical",
    "handoff_complaint",
    "handoff_resolved",
    "whatsapp_open",
)

HANDOFF_KEYS = (
    "medical_pending",
    "complaint_claimed",
    "customer_resolved",
)

AUTOMATION_JOB_KEYS = (
    "success_processing",
    "no_route_processing",
    "cancelled_target_processing",
    "historical_dispatched",
    "historical_failed",
    "historical_skipped",
    "historical_cancelled",
)
