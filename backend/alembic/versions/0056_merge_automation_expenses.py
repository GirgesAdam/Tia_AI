"""Merge automation and core-expenses migration branches.

Revision ID: 0056_merge_automation_expenses
Revises: 0055_lead_followup, 0054_core_expenses
Create Date: 2026-09-04
"""

from collections.abc import Sequence

revision: str = "0056_merge_automation_expenses"
down_revision: tuple[str, str] | Sequence[str] | None = (
    "0055_lead_followup",
    "0054_core_expenses",
)
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    pass


def downgrade() -> None:
    pass
