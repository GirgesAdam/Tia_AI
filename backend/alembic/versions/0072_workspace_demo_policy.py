"""Scope demo behavior to a durable workspace capability.

Revision ID: 0072_workspace_demo_policy
Revises: 0071_conversation_agent_ordering
Create Date: 2026-09-15
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "0072_workspace_demo_policy"
down_revision: str | Sequence[str] | None = "0071_conversation_agent_ordering"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "workspaces",
        sa.Column("is_demo", sa.Boolean(), nullable=False, server_default=sa.false()),
    )
    # One-time deterministic promotion of the existing public demo tenant.
    # Runtime policy never depends on the mutable slug after this migration.
    op.execute(
        sa.text("UPDATE workspaces SET is_demo = true WHERE slug = :slug")
        .bindparams(slug="tia")
    )
    op.create_index(
        "uq_channel_connections_active_meta_external_account",
        "channel_connections",
        ["external_account_id"],
        unique=True,
        postgresql_where=sa.text(
            "channel = 'whatsapp' AND provider = 'meta_cloud' "
            "AND external_account_id IS NOT NULL "
            "AND status IN ('active', 'paused')"
        ),
    )


def downgrade() -> None:
    op.drop_index(
        "uq_channel_connections_active_meta_external_account",
        table_name="channel_connections",
    )
    op.drop_column("workspaces", "is_demo")
