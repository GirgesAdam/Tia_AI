"""Store per-clinic Meta app secrets for direct WhatsApp setup.

Revision ID: 0060_whatsapp_direct_credentials
Revises: 0059_channel_credentials
Create Date: 2026-09-08
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "0060_whatsapp_direct_credentials"
down_revision: str | Sequence[str] | None = "0059_channel_credentials"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "channel_provider_credentials",
        sa.Column("app_secret_ciphertext", sa.Text(), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("channel_provider_credentials", "app_secret_ciphertext")
