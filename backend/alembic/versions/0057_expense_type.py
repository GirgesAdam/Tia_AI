"""Add fixed/variable classification to expenses.

Revision ID: 0057_expense_type
Revises: 0056_merge_automation_expenses
Create Date: 2026-09-07
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "0057_expense_type"
down_revision: str | Sequence[str] | None = "0056_merge_automation_expenses"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "expenses",
        sa.Column("expense_type", sa.String(length=16), nullable=False, server_default="variable"),
    )
    op.create_check_constraint(
        "expense_type_valid",
        "expenses",
        "expense_type IN ('fixed', 'variable')",
    )


def downgrade() -> None:
    op.drop_constraint("expense_type_valid", "expenses", type_="check")
    op.drop_column("expenses", "expense_type")
