"""Retire the automatic booking confirmation message.

Revision ID: 0063_retire_booking_confirmation_automation
Revises: 0062_laser_device_scheduling
Create Date: 2026-09-09

The customer agent already confirms a successful booking in the same turn. The
separate automation duplicated that message and could appear later as a system
message. Keep historical rows for audit, but disable the legacy rule and cancel
anything that has not left Tia yet.
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "0063_retire_booking_confirmation_automation"
down_revision: str | Sequence[str] | None = "0062_laser_device_scheduling"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.execute(
        sa.text(
            """
            UPDATE automation_rules
            SET enabled = FALSE,
                updated_at = now()
            WHERE key = 'booking_confirmation'
              AND enabled IS TRUE
            """
        )
    )

    op.execute(
        sa.text(
            """
            UPDATE message_dispatches AS dispatch
            SET status = 'cancelled',
                locked_at = NULL,
                next_attempt_at = NULL,
                last_error = 'booking_confirmation_retired',
                updated_at = now()
            FROM automation_jobs AS job
            JOIN automation_rules AS rule ON rule.id = job.rule_id
            WHERE rule.key = 'booking_confirmation'
              AND job.dispatch_id = dispatch.id
              AND dispatch.status = 'queued'
            """
        )
    )

    op.execute(
        sa.text(
            """
            UPDATE messages AS message
            SET delivery_status = 'cancelled',
                updated_at = now()
            FROM automation_jobs AS job
            JOIN automation_rules AS rule ON rule.id = job.rule_id
            WHERE rule.key = 'booking_confirmation'
              AND job.message_id = message.id
              AND message.delivery_status = 'queued'
            """
        )
    )

    op.execute(
        sa.text(
            """
            UPDATE automation_jobs AS job
            SET status = 'cancelled',
                locked_at = NULL,
                next_attempt_at = NULL,
                completed_at = now(),
                result = COALESCE(job.result, '{}'::jsonb)
                    || '{"reason":"booking_confirmation_retired"}'::jsonb,
                updated_at = now()
            FROM automation_rules AS rule
            WHERE job.rule_id = rule.id
              AND rule.key = 'booking_confirmation'
              AND (
                    job.status IN ('queued', 'failed', 'processing')
                    OR (
                        job.status = 'dispatched'
                        AND EXISTS (
                            SELECT 1
                            FROM message_dispatches AS dispatch
                            WHERE dispatch.id = job.dispatch_id
                              AND dispatch.status = 'cancelled'
                              AND dispatch.last_error = 'booking_confirmation_retired'
                        )
                    )
              )
            """
        )
    )


def downgrade() -> None:
    # Retirement is a product decision and historical audit rows must not be
    # re-queued automatically on downgrade.
    pass
