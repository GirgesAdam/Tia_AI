"""add production-scale analytics payment index

Revision ID: 0043_analytics_scale_guards
Revises: 0042_analytics_saved_views
Create Date: 2026-08-30
"""

from __future__ import annotations

from collections.abc import Sequence

from alembic import op

revision: str = "0043_analytics_scale_guards"
down_revision: str | None = "0042_analytics_saved_views"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # Clinic-wide revenue and revenue trends filter payment facts by workspace,
    # explicit currency and transaction timestamp. Existing appointment/patient
    # indexes cannot serve that access path because their leading columns differ.
    # Build concurrently so a large historical payment ledger remains writable
    # while the production index is being created.
    with op.get_context().autocommit_block():
        op.create_index(
            "ix_payment_transactions_workspace_currency_created",
            "payment_transactions",
            ["workspace_id", "currency", "created_at"],
            postgresql_concurrently=True,
            if_not_exists=True,
        )


def downgrade() -> None:
    with op.get_context().autocommit_block():
        op.drop_index(
            "ix_payment_transactions_workspace_currency_created",
            table_name="payment_transactions",
            postgresql_concurrently=True,
            if_exists=True,
        )
