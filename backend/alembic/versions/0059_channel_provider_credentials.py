"""Store per-clinic provider credentials encrypted at rest.

Revision ID: 0059_channel_provider_credentials
Revises: 0058_whatsapp_safety
Create Date: 2026-09-07
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "0059_channel_credentials"
down_revision: str | Sequence[str] | None = "0058_whatsapp_safety"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "channel_provider_credentials",
        sa.Column("channel_connection_id", sa.Uuid(), nullable=False),
        sa.Column("workspace_id", sa.Uuid(), nullable=False),
        sa.Column("provider", sa.String(length=40), nullable=False),
        sa.Column("access_token_ciphertext", sa.Text(), nullable=False),
        sa.Column("token_type", sa.String(length=32), nullable=False, server_default="bearer"),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.ForeignKeyConstraint(
            ["channel_connection_id"],
            ["channel_connections.id"],
            name="fk_channel_provider_credentials_connection",
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["workspace_id"],
            ["workspaces.id"],
            name="fk_channel_provider_credentials_workspace",
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("channel_connection_id"),
        sa.UniqueConstraint(
            "workspace_id",
            "channel_connection_id",
            name="uq_channel_provider_credentials_workspace_connection",
        ),
    )
    op.create_index(
        "ix_channel_provider_credentials_workspace_id",
        "channel_provider_credentials",
        ["workspace_id"],
        unique=False,
    )
    op.execute(
        sa.text(
            'ALTER TABLE public."channel_provider_credentials" ENABLE ROW LEVEL SECURITY'
        )
    )
    op.execute(
        sa.text(
            'REVOKE ALL ON TABLE public."channel_provider_credentials" FROM anon, authenticated'
        )
    )


def downgrade() -> None:
    op.drop_index(
        "ix_channel_provider_credentials_workspace_id",
        table_name="channel_provider_credentials",
    )
    op.drop_table("channel_provider_credentials")
