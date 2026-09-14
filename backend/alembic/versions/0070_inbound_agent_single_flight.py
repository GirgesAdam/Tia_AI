"""Harden inbound agent single-flight and reply recovery.

Revision ID: 0070_inbound_agent_single_flight
Revises: 0069_service_package_offers_rls
Create Date: 2026-09-14
"""

from __future__ import annotations

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision = "0070_inbound_agent_single_flight"
down_revision = "0069_service_package_offers_rls"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "channel_inbound_events",
        sa.Column("processing_token", sa.Uuid(), nullable=True),
    )
    op.add_column(
        "channel_inbound_events",
        sa.Column("processing_started_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.add_column(
        "channel_inbound_events",
        sa.Column("processing_lease_expires_at", sa.DateTime(timezone=True), nullable=True),
    )
    # Legacy workers could die after setting `processing`; the poller never
    # selected those rows again. Make every historical orphan retryable.
    op.execute(
        sa.text(
            """
            UPDATE channel_inbound_events
            SET status = 'failed',
                last_error = COALESCE(
                    last_error,
                    'Recovered legacy processing event during 0070 migration.'
                )
            WHERE status = 'processing'
            """
        )
    )

    op.add_column(
        "messages",
        sa.Column("in_reply_to_message_id", postgresql.UUID(as_uuid=True), nullable=True),
    )
    op.create_foreign_key(
        "fk_messages_in_reply_to_message",
        "messages",
        "messages",
        ["in_reply_to_message_id"],
        ["id"],
        ondelete="SET NULL",
    )
    # Historical duplicates may already exist because the old recovery path was
    # metadata-only. Preserve every visible message, but normalize one canonical
    # execution reply per inbound deterministically: earliest valid AI outbound.
    op.execute(
        sa.text(
            """
            WITH ranked AS (
                SELECT
                    outbound.id AS outbound_id,
                    inbound.id AS inbound_id,
                    row_number() OVER (
                        PARTITION BY inbound.id
                        ORDER BY outbound.created_at ASC, outbound.id ASC
                    ) AS reply_rank
                FROM messages AS outbound
                JOIN messages AS inbound
                  ON inbound.id::text = outbound.metadata ->> 'in_reply_to_message_id'
                 AND inbound.workspace_id = outbound.workspace_id
                 AND inbound.conversation_id = outbound.conversation_id
                WHERE outbound.sender_type = 'ai'
                  AND outbound.direction = 'outbound'
                  AND inbound.sender_type = 'patient'
                  AND inbound.direction = 'inbound'
            )
            UPDATE messages AS outbound
            SET in_reply_to_message_id = ranked.inbound_id
            FROM ranked
            WHERE outbound.id = ranked.outbound_id
              AND ranked.reply_rank = 1
            """
        )
    )
    op.create_index(
        "ix_messages_in_reply_to_message_id",
        "messages",
        ["in_reply_to_message_id"],
        unique=False,
    )
    op.create_index(
        "uq_messages_ai_execution_reply_per_inbound",
        "messages",
        ["in_reply_to_message_id"],
        unique=True,
        postgresql_where=sa.text(
            "in_reply_to_message_id IS NOT NULL "
            "AND sender_type = 'ai' AND direction = 'outbound'"
        ),
    )


def downgrade() -> None:
    op.drop_index("uq_messages_ai_execution_reply_per_inbound", table_name="messages")
    op.drop_index("ix_messages_in_reply_to_message_id", table_name="messages")
    op.drop_constraint("fk_messages_in_reply_to_message", "messages", type_="foreignkey")
    op.drop_column("messages", "in_reply_to_message_id")
    op.drop_column("channel_inbound_events", "processing_lease_expires_at")
    op.drop_column("channel_inbound_events", "processing_started_at")
    op.drop_column("channel_inbound_events", "processing_token")