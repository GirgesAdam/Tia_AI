"""Add explicit WhatsApp opt-in fields for proactive messaging safety.

Revision ID: 0058_whatsapp_safety
Revises: 0057_expense_type
Create Date: 2026-09-07
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "0058_whatsapp_safety"
down_revision: str | Sequence[str] | None = "0057_expense_type"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "patients",
        sa.Column(
            "whatsapp_opt_in",
            sa.Boolean(),
            nullable=False,
            server_default=sa.text("false"),
        ),
    )
    op.add_column(
        "patients",
        sa.Column("whatsapp_opt_in_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.add_column(
        "patients",
        sa.Column("whatsapp_opt_in_source", sa.String(length=32), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("patients", "whatsapp_opt_in_source")
    op.drop_column("patients", "whatsapp_opt_in_at")
    op.drop_column("patients", "whatsapp_opt_in")
