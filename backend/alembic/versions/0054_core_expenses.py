"""Add core workspace expenses.

Revision ID: 0054_core_expenses
Revises: 0053_public_table_rls_completion
Create Date: 2026-09-03
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "0054_core_expenses"
down_revision: str | Sequence[str] | None = "0053_public_table_rls_completion"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "expenses",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("workspace_id", sa.Uuid(), nullable=False),
        sa.Column("created_by_user_id", sa.Uuid(), nullable=True),
        sa.Column("title", sa.String(length=200), nullable=False),
        sa.Column("category", sa.String(length=24), nullable=False),
        sa.Column("amount_minor", sa.Integer(), nullable=False),
        sa.Column("currency", sa.String(length=3), nullable=False),
        sa.Column("incurred_on", sa.Date(), nullable=False),
        sa.Column("note", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.CheckConstraint("amount_minor > 0", name="expense_amount_positive"),
        sa.CheckConstraint(
            "category IN ('rent', 'payroll', 'supplies', 'marketing', 'utilities', 'maintenance', 'software', 'taxes', 'other')",
            name="expense_category_valid",
        ),
        sa.ForeignKeyConstraint(
            ["workspace_id"],
            ["workspaces.id"],
            name="fk_expenses_workspace",
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["created_by_user_id"],
            ["users.id"],
            ondelete="SET NULL",
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_expenses_workspace_id", "expenses", ["workspace_id"], unique=False)
    op.create_index("ix_expenses_created_by_user_id", "expenses", ["created_by_user_id"], unique=False)
    op.create_index(
        "ix_expenses_workspace_incurred_on",
        "expenses",
        ["workspace_id", "incurred_on"],
        unique=False,
    )
    op.create_index(
        "ix_expenses_workspace_currency_incurred_on",
        "expenses",
        ["workspace_id", "currency", "incurred_on"],
        unique=False,
    )
    op.execute(sa.text('ALTER TABLE public."expenses" ENABLE ROW LEVEL SECURITY'))
    op.execute(sa.text('REVOKE ALL ON TABLE public."expenses" FROM anon, authenticated'))


def downgrade() -> None:
    op.drop_index("ix_expenses_workspace_currency_incurred_on", table_name="expenses")
    op.drop_index("ix_expenses_workspace_incurred_on", table_name="expenses")
    op.drop_index("ix_expenses_created_by_user_id", table_name="expenses")
    op.drop_index("ix_expenses_workspace_id", table_name="expenses")
    op.drop_table("expenses")
