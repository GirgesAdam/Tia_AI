"""Add normalized appointment payment fields.

Revision ID: 0019_appt_payments
Revises: 0018_missing_data
Create Date: 2026-08-23
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "0019_appt_payments"
down_revision: str | Sequence[str] | None = "0018_missing_data"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "appointments",
        sa.Column("payment_status", sa.String(length=16), server_default="unknown", nullable=False),
    )
    op.add_column(
        "appointments",
        sa.Column("amount_paid_minor", sa.Integer(), nullable=True),
    )
    op.add_column(
        "appointments",
        sa.Column("payment_method", sa.String(length=20), server_default="unknown", nullable=False),
    )
    op.create_check_constraint(
        "appointment_payment_status_valid",
        "appointments",
        "payment_status IN ('unknown', 'unpaid', 'partial', 'paid', 'refunded')",
    )
    op.create_check_constraint(
        "appointment_payment_method_valid",
        "appointments",
        "payment_method IN ('unknown', 'cash', 'card', 'bank_transfer', 'wallet', 'other')",
    )
    op.create_check_constraint(
        "appointment_amount_paid_non_negative",
        "appointments",
        "amount_paid_minor IS NULL OR amount_paid_minor >= 0",
    )


def downgrade() -> None:
    op.drop_constraint("appointment_amount_paid_non_negative", "appointments", type_="check")
    op.drop_constraint("appointment_payment_method_valid", "appointments", type_="check")
    op.drop_constraint("appointment_payment_status_valid", "appointments", type_="check")
    op.drop_column("appointments", "payment_method")
    op.drop_column("appointments", "amount_paid_minor")
    op.drop_column("appointments", "payment_status")
