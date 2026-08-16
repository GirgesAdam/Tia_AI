"""Add WhatsApp/n8n delivery tracking and read receipts.

Revision ID: 0010_whatsapp_n8n_bridge
Revises: 0009_channel_layer
Create Date: 2026-08-13
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0010_whatsapp_n8n_bridge"
down_revision: Union[str, Sequence[str], None] = "0009_channel_layer"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "message_dispatches",
        sa.Column("read_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.drop_constraint(
        "message_dispatch_status_valid",
        "message_dispatches",
        type_="check",
    )
    op.create_check_constraint(
        "message_dispatch_status_valid",
        "message_dispatches",
        "status IN ('queued', 'processing', 'sent', 'delivered', 'read', 'failed', 'cancelled')",
    )
    op.create_index(
        "uq_message_dispatches_connection_provider_message",
        "message_dispatches",
        ["channel_connection_id", "provider_message_id"],
        unique=True,
        postgresql_where=sa.text("provider_message_id IS NOT NULL"),
    )

    op.create_table(
        "channel_delivery_events",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("workspace_id", sa.Uuid(), nullable=False),
        sa.Column("channel_connection_id", sa.Uuid(), nullable=False),
        sa.Column("provider_message_id", sa.String(length=255), nullable=False),
        sa.Column("external_event_id", sa.String(length=512), nullable=False),
        sa.Column("status", sa.String(length=20), nullable=False),
        sa.Column("occurred_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("processed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "payload",
            postgresql.JSONB(astext_type=sa.Text()),
            server_default=sa.text("'{}'::jsonb"),
            nullable=False,
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.CheckConstraint(
            "status IN ('sent', 'delivered', 'read', 'failed')",
            name="channel_delivery_event_status_valid",
        ),
        sa.ForeignKeyConstraint(
            ["workspace_id", "channel_connection_id"],
            ["channel_connections.workspace_id", "channel_connections.id"],
            ondelete="CASCADE",
            name="fk_channel_delivery_events_connection",
        ),
        sa.PrimaryKeyConstraint("id", name="pk_channel_delivery_events"),
    )
    op.create_index(
        "ix_channel_delivery_events_workspace_id",
        "channel_delivery_events",
        ["workspace_id"],
    )
    op.create_index(
        "ix_channel_delivery_events_channel_connection_id",
        "channel_delivery_events",
        ["channel_connection_id"],
    )
    op.create_index(
        "uq_channel_delivery_events_connection_external_event",
        "channel_delivery_events",
        ["channel_connection_id", "external_event_id"],
        unique=True,
    )
    op.create_index(
        "ix_channel_delivery_events_provider_pending",
        "channel_delivery_events",
        ["channel_connection_id", "provider_message_id", "processed_at"],
    )

    op.execute(sa.text('ALTER TABLE public."channel_delivery_events" ENABLE ROW LEVEL SECURITY'))
    op.execute(sa.text('REVOKE ALL ON TABLE public."channel_delivery_events" FROM anon, authenticated'))


def downgrade() -> None:
    op.drop_index(
        "ix_channel_delivery_events_provider_pending",
        table_name="channel_delivery_events",
    )
    op.drop_index(
        "uq_channel_delivery_events_connection_external_event",
        table_name="channel_delivery_events",
    )
    op.drop_index(
        "ix_channel_delivery_events_channel_connection_id",
        table_name="channel_delivery_events",
    )
    op.drop_index(
        "ix_channel_delivery_events_workspace_id",
        table_name="channel_delivery_events",
    )
    op.drop_table("channel_delivery_events")

    op.drop_index(
        "uq_message_dispatches_connection_provider_message",
        table_name="message_dispatches",
    )
    op.drop_constraint(
        "message_dispatch_status_valid",
        "message_dispatches",
        type_="check",
    )
    op.create_check_constraint(
        "message_dispatch_status_valid",
        "message_dispatches",
        "status IN ('queued', 'processing', 'sent', 'delivered', 'failed', 'cancelled')",
    )
    op.drop_column("message_dispatches", "read_at")
