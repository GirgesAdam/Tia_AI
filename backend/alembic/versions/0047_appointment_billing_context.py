"""Preserve prepaid-package appointment coverage without fabricating revenue.

Revision ID: 0047_appointment_billing_context
Revises: 0046_sparse_appointment_context
Create Date: 2026-08-31
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0047_appointment_billing_context"
down_revision: str | None = "0046_sparse_appointment_context"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "appointments",
        sa.Column(
            "billing_context",
            sa.String(length=24),
            nullable=False,
            server_default="standard",
        ),
    )
    op.add_column(
        "appointments",
        sa.Column("package_external_id", sa.String(length=128), nullable=True),
    )
    op.create_check_constraint(
        "appointment_billing_context_valid",
        "appointments",
        "billing_context IN ('standard', 'package_prepaid')",
    )


def downgrade() -> None:
    op.drop_constraint(
        "appointment_billing_context_valid",
        "appointments",
        type_="check",
    )
    op.drop_column("appointments", "package_external_id")
    op.drop_column("appointments", "billing_context")
