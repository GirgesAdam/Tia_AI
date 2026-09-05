"""Allow lead follow-up automation rules.

Revision ID: 0055_lead_followup
Revises: 0054_cancel_recovery
Create Date: 2026-09-04
"""

from collections.abc import Sequence

from alembic import op

revision: str = "0055_lead_followup"
down_revision: str | Sequence[str] | None = "0054_cancel_recovery"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def _replace_trigger_constraint(values: str) -> None:
    op.drop_constraint(
        "automation_rule_trigger_kind_valid",
        "automation_rules",
        type_="check",
    )
    op.create_check_constraint(
        "automation_rule_trigger_kind_valid",
        "automation_rules",
        f"trigger_kind IN ({values})",
    )


def upgrade() -> None:
    _replace_trigger_constraint(
        "'appointment_created', 'before_appointment', 'after_completed', 'after_no_show', 'after_cancelled', 'after_lead_activity'"
    )


def downgrade() -> None:
    _replace_trigger_constraint(
        "'appointment_created', 'before_appointment', 'after_completed', 'after_no_show', 'after_cancelled'"
    )
