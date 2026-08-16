from __future__ import annotations

from uuid import UUID

from staging_scenarios import sid

GATE_VERSION = "0.15.0"
GATE_MARKER = "tia-final-internal-gate"


def secondary_workspace_id(primary_workspace_id: UUID) -> UUID:
    return sid(primary_workspace_id, "workspace:final-gate-secondary")


def gate_ids(primary_workspace_id: UUID) -> dict[str, UUID]:
    secondary = secondary_workspace_id(primary_workspace_id)
    return {
        "secondary_workspace": secondary,
        "race_patient_a": sid(primary_workspace_id, "final-gate:patient:race-a"),
        "race_patient_b": sid(primary_workspace_id, "final-gate:patient:race-b"),
        "member_patient": sid(primary_workspace_id, "final-gate:patient:member"),
        "automation_reschedule_patient": sid(primary_workspace_id, "final-gate:patient:auto-reschedule"),
        "automation_cancel_patient": sid(primary_workspace_id, "final-gate:patient:auto-cancel"),
        "channel_patient": sid(primary_workspace_id, "final-gate:patient:channel-handoff"),
        "channel_conversation": sid(primary_workspace_id, "final-gate:conversation:channel-handoff"),
        "channel_identity": sid(primary_workspace_id, "final-gate:identity:channel-handoff"),
        "channel_handoff": sid(primary_workspace_id, "final-gate:handoff:channel-handoff"),
        "provider_message": sid(primary_workspace_id, "final-gate:message:provider-status"),
        "provider_dispatch": sid(primary_workspace_id, "final-gate:dispatch:provider-status"),
        "automation_rule": sid(primary_workspace_id, "final-gate:automation-rule:before-24h"),
        "secondary_branch": sid(secondary, "final-gate:branch"),
        "secondary_staff": sid(secondary, "final-gate:staff"),
        "secondary_doctor": sid(secondary, "final-gate:doctor"),
        "secondary_service": sid(secondary, "final-gate:service"),
        "secondary_doctor_branch": sid(secondary, "final-gate:doctor-branch"),
        "secondary_doctor_service": sid(secondary, "final-gate:doctor-service"),
        "secondary_patient": sid(secondary, "final-gate:patient"),
        "secondary_appointment": sid(secondary, "final-gate:appointment"),
        "secondary_conversation": sid(secondary, "final-gate:conversation"),
    }


def member_email_for(admin_email: str) -> str:
    local, sep, domain = admin_email.strip().lower().partition("@")
    if not sep:
        raise ValueError("Admin email is invalid.")
    return f"{local}+tia-final-gate-member@{domain}"
