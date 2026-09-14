"""Serialize agent turns per conversation.

Revision ID: 0071_conversation_agent_ordering
Revises: 0070_inbound_agent_single_flight
"""

import sqlalchemy as sa

from alembic import op

revision = "0071_conversation_agent_ordering"
down_revision = "0070_inbound_agent_single_flight"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "conversations",
        sa.Column("agent_processing_token", sa.Uuid(), nullable=True),
    )
    op.add_column(
        "conversations",
        sa.Column("agent_processing_started_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.add_column(
        "conversations",
        sa.Column("agent_processing_lease_expires_at", sa.DateTime(timezone=True), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("conversations", "agent_processing_lease_expires_at")
    op.drop_column("conversations", "agent_processing_started_at")
    op.drop_column("conversations", "agent_processing_token")
