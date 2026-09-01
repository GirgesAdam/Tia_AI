"""Enable automatic appointment reminders and post-visit care by default.

Revision ID: 0025_auto_patient_lifecycle
Revises: 0024_ai_followup_execution
Create Date: 2026-08-25
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "0025_auto_patient_lifecycle"
down_revision: str | Sequence[str] | None = "0024_ai_followup_execution"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


_AUTOMATIC_KEYS = (
    "appointment_reminder_24h",
    "appointment_reminder_2h",
    "post_visit_followup",
)


def upgrade() -> None:
    # v0.31.2 changes these from opt-in samples into the default patient-care
    # lifecycle. Admins can still disable or retime any rule after the upgrade.
    op.execute(
        sa.text(
            """
            UPDATE automation_rules
            SET enabled = TRUE,
                updated_at = now()
            WHERE key IN (
                'appointment_reminder_24h',
                'appointment_reminder_2h',
                'post_visit_followup'
            )
            """
        )
    )


def downgrade() -> None:
    # Data-only default change: do not silently disable rules that an admin may
    # have intentionally kept enabled after running this version.
    pass
