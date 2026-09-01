"""Add package payment linkage and standalone price snapshot.

Revision ID: 0049_package_refund_pricing
Revises: 0048_patient_packages
Create Date: 2026-08-31
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0049_package_refund_pricing"
down_revision: str | None = "0048_patient_packages"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "patient_packages",
        sa.Column("standalone_session_price_minor_at_purchase", sa.Integer(), nullable=True),
    )
    op.create_check_constraint(
        "patient_package_standalone_price_non_negative",
        "patient_packages",
        "standalone_session_price_minor_at_purchase IS NULL OR standalone_session_price_minor_at_purchase >= 0",
    )

    op.add_column(
        "payment_transactions",
        sa.Column("patient_package_id", sa.Uuid(), nullable=True),
    )
    op.create_index(
        "ix_payment_transactions_patient_package_id",
        "payment_transactions",
        ["patient_package_id"],
    )
    op.create_foreign_key(
        "fk_payment_transactions_patient_package",
        "payment_transactions",
        "patient_packages",
        ["workspace_id", "patient_package_id"],
        ["workspace_id", "id"],
        ondelete="RESTRICT",
    )

    # Existing package purchases/refunds become first-class package finance facts.
    op.execute(
        sa.text(
            """
            UPDATE payment_transactions AS pt
            SET patient_package_id = pp.id
            FROM patient_packages AS pp
            WHERE pt.workspace_id = pp.workspace_id
              AND pt.id = pp.purchase_transaction_id
              AND pt.patient_package_id IS NULL
            """
        )
    )
    op.execute(
        sa.text(
            """
            UPDATE payment_transactions AS refund
            SET patient_package_id = pp.id
            FROM patient_packages AS pp
            WHERE refund.workspace_id = pp.workspace_id
              AND refund.transaction_type = 'refund'
              AND refund.reference_transaction_id = pp.purchase_transaction_id
              AND refund.patient_package_id IS NULL
            """
        )
    )


def downgrade() -> None:
    op.drop_constraint(
        "fk_payment_transactions_patient_package",
        "payment_transactions",
        type_="foreignkey",
    )
    op.drop_index(
        "ix_payment_transactions_patient_package_id",
        table_name="payment_transactions",
    )
    op.drop_column("payment_transactions", "patient_package_id")
    op.drop_constraint(
        "patient_package_standalone_price_non_negative",
        "patient_packages",
        type_="check",
    )
    op.drop_column("patient_packages", "standalone_session_price_minor_at_purchase")
