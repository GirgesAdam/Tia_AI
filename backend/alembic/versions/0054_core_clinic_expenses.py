"""Add workspace operating expenses for core financial reporting.

Revision ID: 0054_core_clinic_expenses
Revises: 0053_public_table_rls_completion
Create Date: 2026-09-03
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "0054_core_clinic_expenses"
down_revision: str | Sequence[str] | None = "0053_public_table_rls_completion"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "clinic_expenses",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("workspace_id", sa.Uuid(), nullable=False),
        sa.Column("incurred_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("category", sa.String(length=32), nullable=False),
        sa.Column("vendor", sa.String(length=160), nullable=True),
        sa.Column("description", sa.String(length=240), nullable=True),
        sa.Column("amount_minor", sa.Integer(), nullable=False),
        sa.Column("currency", sa.String(length=3), server_default="EGP", nullable=False),
        sa.Column("source", sa.String(length=32), server_default="manual", nullable=False),
        sa.Column("status", sa.String(length=16), server_default="active", nullable=False),
        sa.Column("created_by_user_id", sa.Uuid(), nullable=True),
        sa.Column("voided_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("voided_by_user_id", sa.Uuid(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.CheckConstraint("amount_minor > 0", name="clinic_expense_amount_positive"),
        sa.CheckConstraint(
            "category IN ('rent','payroll','marketing','supplies','utilities','software','other')",
            name="clinic_expense_category_valid",
        ),
        sa.CheckConstraint(
            "source IN ('manual','import','integration')",
            name="clinic_expense_source_valid",
        ),
        sa.CheckConstraint(
            "status IN ('active','voided')",
            name="clinic_expense_status_valid",
        ),
        sa.CheckConstraint(
            "(status = 'active' AND voided_at IS NULL AND voided_by_user_id IS NULL) OR "
            "(status = 'voided' AND voided_at IS NOT NULL)",
            name="clinic_expense_void_state_valid",
        ),
        sa.ForeignKeyConstraint(["workspace_id"], ["workspaces.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["created_by_user_id"], ["users.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["voided_by_user_id"], ["users.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_clinic_expenses_workspace_id", "clinic_expenses", ["workspace_id"], unique=False)
    op.create_index(
        "ix_clinic_expenses_workspace_incurred",
        "clinic_expenses",
        ["workspace_id", "incurred_at"],
        unique=False,
    )
    op.create_index(
        "ix_clinic_expenses_workspace_status_incurred",
        "clinic_expenses",
        ["workspace_id", "status", "incurred_at"],
        unique=False,
    )
    op.execute(sa.text('ALTER TABLE public."clinic_expenses" ENABLE ROW LEVEL SECURITY'))
    op.execute(sa.text('REVOKE ALL ON TABLE public."clinic_expenses" FROM anon, authenticated'))


def downgrade() -> None:
    op.drop_index("ix_clinic_expenses_workspace_status_incurred", table_name="clinic_expenses")
    op.drop_index("ix_clinic_expenses_workspace_incurred", table_name="clinic_expenses")
    op.drop_index("ix_clinic_expenses_workspace_id", table_name="clinic_expenses")
    op.drop_table("clinic_expenses")
