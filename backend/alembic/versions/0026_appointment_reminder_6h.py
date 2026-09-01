"""Replace default 24h/2h appointment reminders with one 6h reminder.

Revision ID: 0026_appointment_reminder_6h
Revises: 0025_auto_patient_lifecycle
Create Date: 2026-08-25
"""

from collections.abc import Sequence
from uuid import uuid4

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql
from alembic import op

revision: str = "0026_appointment_reminder_6h"
down_revision: str | Sequence[str] | None = "0025_auto_patient_lifecycle"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_LEGACY_REMINDER_KEYS = ("appointment_reminder_24h", "appointment_reminder_2h")
_NEW_KEY = "appointment_reminder_6h"


def upgrade() -> None:
    bind = op.get_bind()

    # The desired lifecycle has exactly one pre-appointment reminder. Disable
    # the two legacy defaults for every existing workspace before adding 6h.
    bind.execute(
        sa.text(
            """
            UPDATE automation_rules
            SET enabled = FALSE,
                updated_at = now()
            WHERE key IN ('appointment_reminder_24h', 'appointment_reminder_2h')
            """
        )
    )

    # Cancel provider dispatches that were already prepared by a legacy job but
    # have not been sent yet. Operators should pause n8n while migrating so a
    # dispatch already leased by the provider cannot race this data change.
    bind.execute(
        sa.text(
            """
            UPDATE message_dispatches
            SET status = 'cancelled',
                locked_at = NULL,
                next_attempt_at = NULL,
                last_error = 'superseded_by_6h_reminder',
                updated_at = now()
            WHERE status IN ('queued', 'failed', 'processing')
              AND id IN (
                  SELECT job.dispatch_id
                  FROM automation_jobs AS job
                  JOIN automation_rules AS rule ON rule.id = job.rule_id
                  WHERE rule.key IN ('appointment_reminder_24h', 'appointment_reminder_2h')
                    AND job.dispatch_id IS NOT NULL
              )
            """
        )
    )
    bind.execute(
        sa.text(
            """
            UPDATE messages
            SET delivery_status = 'cancelled',
                updated_at = now()
            WHERE delivery_status IN ('queued', 'failed')
              AND id IN (
                  SELECT job.message_id
                  FROM automation_jobs AS job
                  JOIN automation_rules AS rule ON rule.id = job.rule_id
                  WHERE rule.key IN ('appointment_reminder_24h', 'appointment_reminder_2h')
                    AND job.message_id IS NOT NULL
                    AND (
                        job.dispatch_id IS NULL
                        OR job.dispatch_id IN (
                            SELECT id FROM message_dispatches WHERE status = 'cancelled'
                        )
                    )
              )
            """
        )
    )

    # Cancel legacy jobs that have not produced a provider send. execute_job also
    # re-checks rule enabled state, so queued/claimed work cannot be recreated.
    bind.execute(
        sa.text(
            """
            UPDATE automation_jobs
            SET status = 'cancelled',
                completed_at = now(),
                locked_at = NULL,
                next_attempt_at = NULL,
                result = jsonb_build_object('reason', 'superseded_by_6h_reminder'),
                updated_at = now()
            WHERE job_kind = 'appointment_rule'
              AND rule_id IN (
                  SELECT id
                  FROM automation_rules
                  WHERE key IN ('appointment_reminder_24h', 'appointment_reminder_2h')
              )
              AND (
                  status IN ('queued', 'failed', 'processing')
                  OR (
                      status = 'dispatched'
                      AND dispatch_id IN (
                          SELECT id FROM message_dispatches WHERE status = 'cancelled'
                      )
                  )
              )
            """
        )
    )

    # Materialize the 6h rule for existing workspaces. Python-generated UUIDs
    # keep the migration independent of PostgreSQL UUID extensions.
    workspace_ids = [row[0] for row in bind.execute(sa.text("SELECT id FROM workspaces"))]
    existing_workspace_ids = {
        row[0]
        for row in bind.execute(
            sa.text("SELECT workspace_id FROM automation_rules WHERE key = :key"),
            {"key": _NEW_KEY},
        )
    }

    automation_rules = sa.table(
        "automation_rules",
        sa.column("id", sa.Uuid()),
        sa.column("workspace_id", sa.Uuid()),
        sa.column("key", sa.String()),
        sa.column("name", sa.String()),
        sa.column("enabled", sa.Boolean()),
        sa.column("trigger_kind", sa.String()),
        sa.column("offset_minutes", sa.Integer()),
        sa.column("channel", sa.String()),
        sa.column("template_name", sa.String()),
        sa.column("template_language", sa.String()),
        sa.column("max_lateness_minutes", sa.Integer()),
        sa.column("config", postgresql.JSONB()),
    )

    rows = [
        {
            "id": uuid4(),
            "workspace_id": workspace_id,
            "key": _NEW_KEY,
            "name": "Appointment reminder - 6 hours",
            "enabled": True,
            "trigger_kind": "before_appointment",
            "offset_minutes": -360,
            "channel": "whatsapp",
            "template_name": "tia_appointment_reminder_6h_ar",
            "template_language": "ar",
            "max_lateness_minutes": 30,
            "config": {},
        }
        for workspace_id in workspace_ids
        if workspace_id not in existing_workspace_ids
    ]
    if rows:
        op.bulk_insert(automation_rules, rows)

    # If a workspace had already created the key manually, preserve the row but
    # align it with the canonical lifecycle timing and enable it.
    bind.execute(
        sa.text(
            """
            UPDATE automation_rules
            SET name = 'Appointment reminder - 6 hours',
                enabled = TRUE,
                trigger_kind = 'before_appointment',
                offset_minutes = -360,
                channel = 'whatsapp',
                template_name = 'tia_appointment_reminder_6h_ar',
                template_language = 'ar',
                max_lateness_minutes = 30,
                updated_at = now()
            WHERE key = 'appointment_reminder_6h'
            """
        )
    )


def downgrade() -> None:
    # Do not re-enable the legacy 24h/2h rules automatically on downgrade;
    # doing so could create surprise patient messages. The rows remain available
    # for an admin to explicitly re-enable if reverting policy is intentional.
    pass
