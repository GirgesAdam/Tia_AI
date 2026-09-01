"""Remove typed customer email fields from Tia patient/channel identity contracts.

Revision ID: 0034_drop_customer_email
Revises: 0033_sync_authority
Create Date: 2026-08-26
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0034_drop_customer_email"
down_revision: str | Sequence[str] | None = "0033_sync_authority"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.drop_column("channel_identities", "email")
    op.drop_column("patients", "email")


def downgrade() -> None:
    op.add_column("patients", sa.Column("email", sa.String(length=320), nullable=True))
    op.add_column("channel_identities", sa.Column("email", sa.String(length=320), nullable=True))
