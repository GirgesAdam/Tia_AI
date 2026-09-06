"""Merge automation and expense migration branches.

Revision ID: 0056_merge_automation_expenses
Revises: 0055_lead_followup, 0054_core_expenses, 0054_clinic_expenses
Create Date: 2026-09-04
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0056_merge_automation_expenses"
down_revision: tuple[str, str, str] | Sequence[str] | None = (
    "0055_lead_followup",
    "0054_core_expenses",
    "0054_clinic_expenses",
)
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_ALLOWED_CATEGORIES = (
    "rent",
    "payroll",
    "supplies",
    "marketing",
    "utilities",
    "maintenance",
    "software",
    "taxes",
    "other",
)


def upgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    if "clinic_expenses" not in inspector.get_table_names(schema="public"):
        return

    allowed = ", ".join(f"'{value}'" for value in _ALLOWED_CATEGORIES)
    op.execute(
        sa.text(
            f"""
            INSERT INTO public.expenses (
                id,
                workspace_id,
                created_by_user_id,
                title,
                category,
                amount_minor,
                currency,
                incurred_on,
                note,
                created_at,
                updated_at
            )
            SELECT
                id,
                workspace_id,
                NULL,
                LEFT(COALESCE(NULLIF(BTRIM(description), ''), category, 'Expense'), 200),
                CASE WHEN category IN ({allowed}) THEN category ELSE 'other' END,
                amount_minor,
                UPPER(LEFT(currency, 3)),
                incurred_at::date,
                CASE
                    WHEN NULLIF(BTRIM(source), '') IS NULL THEN NULL
                    ELSE 'Legacy source: ' || source
                END,
                created_at,
                updated_at
            FROM public.clinic_expenses
            ON CONFLICT (id) DO NOTHING
            """
        )
    )


def downgrade() -> None:
    # Keep migrated finance rows intact. The legacy table is deliberately retained
    # for audit/rollback safety and is no longer used by the application runtime.
    pass
