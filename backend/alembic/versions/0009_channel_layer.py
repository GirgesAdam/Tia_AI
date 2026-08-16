"""Add provider-neutral channel adapter, inbound queue, and outbound dispatch outbox.

Revision ID: 0009_channel_layer
Revises: 0008_team_inbox
Create Date: 2026-08-13
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0009_channel_layer"
down_revision: Union[str, Sequence[str], None] = "0008_team_inbox"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "channel_connections",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("workspace_id", sa.Uuid(), nullable=False),
        sa.Column("channel", sa.String(length=24), nullable=False),
        sa.Column("provider", sa.String(length=40), nullable=False),
        sa.Column("display_name", sa.String(length=120), nullable=False),
        sa.Column("status", sa.String(length=20), server_default="active", nullable=False),
        sa.Column("external_account_id", sa.String(length=255), nullable=True),
        sa.Column("adapter_token_hash", sa.String(length=64), nullable=False),
        sa.Column("created_by_user_id", sa.Uuid(), nullable=True),
        sa.Column(
            "config",
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
            "channel IN ('whatsapp', 'instagram', 'facebook', 'web', 'email', 'sms', 'other')",
            name="channel_connection_channel_valid",
        ),
        sa.CheckConstraint(
            "status IN ('active', 'paused', 'disconnected')",
            name="channel_connection_status_valid",
        ),
        sa.ForeignKeyConstraint(
            ["workspace_id"],
            ["workspaces.id"],
            ondelete="CASCADE",
            name="fk_channel_connections_workspace_id_workspaces",
        ),
        sa.ForeignKeyConstraint(
            ["created_by_user_id"],
            ["users.id"],
            ondelete="SET NULL",
            name="fk_channel_connections_created_by_user_id_users",
        ),
        sa.PrimaryKeyConstraint("id", name="pk_channel_connections"),
        sa.UniqueConstraint(
            "workspace_id",
            "id",
            name="uq_channel_connections_workspace_id_id",
        ),
        sa.UniqueConstraint(
            "adapter_token_hash",
            name="uq_channel_connections_adapter_token_hash",
        ),
    )
    op.create_index(
        "ix_channel_connections_workspace_id",
        "channel_connections",
        ["workspace_id"],
    )
    op.create_index(
        "ix_channel_connections_created_by_user_id",
        "channel_connections",
        ["created_by_user_id"],
    )
    op.create_index(
        "ix_channel_connections_workspace_status",
        "channel_connections",
        ["workspace_id", "status"],
    )
    op.create_index(
        "uq_channel_connections_workspace_external_account",
        "channel_connections",
        ["workspace_id", "channel", "provider", "external_account_id"],
        unique=True,
        postgresql_where=sa.text("external_account_id IS NOT NULL"),
    )

    op.create_table(
        "channel_identities",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("workspace_id", sa.Uuid(), nullable=False),
        sa.Column("channel_connection_id", sa.Uuid(), nullable=False),
        sa.Column("patient_id", sa.Uuid(), nullable=False),
        sa.Column("external_user_id", sa.String(length=255), nullable=False),
        sa.Column("display_name", sa.String(length=200), nullable=True),
        sa.Column("phone", sa.String(length=40), nullable=True),
        sa.Column("email", sa.String(length=320), nullable=True),
        sa.Column(
            "metadata",
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
        sa.ForeignKeyConstraint(
            ["workspace_id", "channel_connection_id"],
            ["channel_connections.workspace_id", "channel_connections.id"],
            ondelete="CASCADE",
            name="fk_channel_identities_connection",
        ),
        sa.ForeignKeyConstraint(
            ["workspace_id", "patient_id"],
            ["patients.workspace_id", "patients.id"],
            ondelete="CASCADE",
            name="fk_channel_identities_patient",
        ),
        sa.PrimaryKeyConstraint("id", name="pk_channel_identities"),
        sa.UniqueConstraint(
            "workspace_id",
            "id",
            name="uq_channel_identities_workspace_id_id",
        ),
        sa.UniqueConstraint(
            "channel_connection_id",
            "external_user_id",
            name="uq_channel_identities_connection_external_user",
        ),
    )
    op.create_index(
        "ix_channel_identities_workspace_id",
        "channel_identities",
        ["workspace_id"],
    )
    op.create_index(
        "ix_channel_identities_channel_connection_id",
        "channel_identities",
        ["channel_connection_id"],
    )
    op.create_index(
        "ix_channel_identities_patient_id",
        "channel_identities",
        ["patient_id"],
    )
    op.create_index(
        "ix_channel_identities_workspace_patient",
        "channel_identities",
        ["workspace_id", "patient_id"],
    )

    op.add_column(
        "conversations",
        sa.Column("channel_connection_id", sa.Uuid(), nullable=True),
    )
    op.create_foreign_key(
        "fk_conversations_channel_connection",
        "conversations",
        "channel_connections",
        ["workspace_id", "channel_connection_id"],
        ["workspace_id", "id"],
    )
    op.create_index(
        "ix_conversations_channel_connection_id",
        "conversations",
        ["channel_connection_id"],
    )
    op.drop_index(
        "uq_conversations_workspace_channel_external",
        table_name="conversations",
    )
    op.create_index(
        "uq_conversations_workspace_connection_external",
        "conversations",
        ["workspace_id", "channel_connection_id", "external_conversation_id"],
        unique=True,
        postgresql_where=sa.text(
            "channel_connection_id IS NOT NULL AND external_conversation_id IS NOT NULL"
        ),
    )

    op.add_column(
        "messages",
        sa.Column("channel_connection_id", sa.Uuid(), nullable=True),
    )
    op.create_foreign_key(
        "fk_messages_channel_connection",
        "messages",
        "channel_connections",
        ["workspace_id", "channel_connection_id"],
        ["workspace_id", "id"],
    )
    op.create_index(
        "ix_messages_channel_connection_id",
        "messages",
        ["channel_connection_id"],
    )
    op.drop_index("ix_messages_workspace_external", table_name="messages")
    op.create_index(
        "uq_messages_workspace_connection_external",
        "messages",
        ["workspace_id", "channel_connection_id", "external_message_id"],
        unique=True,
        postgresql_where=sa.text(
            "channel_connection_id IS NOT NULL AND external_message_id IS NOT NULL"
        ),
    )

    op.create_table(
        "channel_inbound_events",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("workspace_id", sa.Uuid(), nullable=False),
        sa.Column("channel_connection_id", sa.Uuid(), nullable=False),
        sa.Column("message_id", sa.Uuid(), nullable=False),
        sa.Column("outbound_message_id", sa.Uuid(), nullable=True),
        sa.Column("external_event_id", sa.String(length=255), nullable=False),
        sa.Column("status", sa.String(length=20), server_default="received", nullable=False),
        sa.Column("attempts", sa.Integer(), server_default="0", nullable=False),
        sa.Column("last_error", sa.String(length=2000), nullable=True),
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
            "status IN ('received', 'processing', 'processed', 'failed')",
            name="channel_inbound_event_status_valid",
        ),
        sa.ForeignKeyConstraint(
            ["workspace_id", "channel_connection_id"],
            ["channel_connections.workspace_id", "channel_connections.id"],
            ondelete="CASCADE",
            name="fk_channel_inbound_events_connection",
        ),
        sa.ForeignKeyConstraint(
            ["message_id"],
            ["messages.id"],
            ondelete="CASCADE",
            name="fk_channel_inbound_events_message_id_messages",
        ),
        sa.ForeignKeyConstraint(
            ["outbound_message_id"],
            ["messages.id"],
            ondelete="SET NULL",
            name="fk_channel_inbound_events_outbound_message_id_messages",
        ),
        sa.PrimaryKeyConstraint("id", name="pk_channel_inbound_events"),
    )
    op.create_index(
        "ix_channel_inbound_events_workspace_id",
        "channel_inbound_events",
        ["workspace_id"],
    )
    op.create_index(
        "ix_channel_inbound_events_channel_connection_id",
        "channel_inbound_events",
        ["channel_connection_id"],
    )
    op.create_index(
        "ix_channel_inbound_events_message_id",
        "channel_inbound_events",
        ["message_id"],
    )
    op.create_index(
        "ix_channel_inbound_events_outbound_message_id",
        "channel_inbound_events",
        ["outbound_message_id"],
    )
    op.create_index(
        "uq_channel_inbound_events_connection_external_event",
        "channel_inbound_events",
        ["channel_connection_id", "external_event_id"],
        unique=True,
    )
    op.create_index(
        "ix_channel_inbound_events_workspace_status",
        "channel_inbound_events",
        ["workspace_id", "status", "created_at"],
    )

    op.create_table(
        "message_dispatches",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("workspace_id", sa.Uuid(), nullable=False),
        sa.Column("channel_connection_id", sa.Uuid(), nullable=False),
        sa.Column("message_id", sa.Uuid(), nullable=False),
        sa.Column("status", sa.String(length=20), server_default="queued", nullable=False),
        sa.Column("attempts", sa.Integer(), server_default="0", nullable=False),
        sa.Column("provider_message_id", sa.String(length=255), nullable=True),
        sa.Column("last_error", sa.String(length=2000), nullable=True),
        sa.Column("next_attempt_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("locked_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("sent_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("delivered_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "metadata",
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
            "status IN ('queued', 'processing', 'sent', 'delivered', 'failed', 'cancelled')",
            name="message_dispatch_status_valid",
        ),
        sa.ForeignKeyConstraint(
            ["workspace_id", "channel_connection_id"],
            ["channel_connections.workspace_id", "channel_connections.id"],
            ondelete="CASCADE",
            name="fk_message_dispatches_connection",
        ),
        sa.ForeignKeyConstraint(
            ["message_id"],
            ["messages.id"],
            ondelete="CASCADE",
            name="fk_message_dispatches_message_id_messages",
        ),
        sa.PrimaryKeyConstraint("id", name="pk_message_dispatches"),
    )
    op.create_index(
        "ix_message_dispatches_workspace_id",
        "message_dispatches",
        ["workspace_id"],
    )
    op.create_index(
        "ix_message_dispatches_channel_connection_id",
        "message_dispatches",
        ["channel_connection_id"],
    )
    op.create_index(
        "ix_message_dispatches_message_id",
        "message_dispatches",
        ["message_id"],
    )
    op.create_index(
        "uq_message_dispatches_workspace_message",
        "message_dispatches",
        ["workspace_id", "message_id"],
        unique=True,
    )
    op.create_index(
        "ix_message_dispatches_connection_queue",
        "message_dispatches",
        ["channel_connection_id", "status", "next_attempt_at", "created_at"],
    )

    for table in (
        "channel_connections",
        "channel_identities",
        "channel_inbound_events",
        "message_dispatches",
    ):
        op.execute(sa.text(f'ALTER TABLE public."{table}" ENABLE ROW LEVEL SECURITY'))
        op.execute(sa.text(f'REVOKE ALL ON TABLE public."{table}" FROM anon, authenticated'))


def downgrade() -> None:
    op.drop_index(
        "ix_message_dispatches_connection_queue",
        table_name="message_dispatches",
    )
    op.drop_index(
        "uq_message_dispatches_workspace_message",
        table_name="message_dispatches",
    )
    op.drop_index("ix_message_dispatches_message_id", table_name="message_dispatches")
    op.drop_index(
        "ix_message_dispatches_channel_connection_id",
        table_name="message_dispatches",
    )
    op.drop_index("ix_message_dispatches_workspace_id", table_name="message_dispatches")
    op.drop_table("message_dispatches")

    op.drop_index(
        "ix_channel_inbound_events_workspace_status",
        table_name="channel_inbound_events",
    )
    op.drop_index(
        "uq_channel_inbound_events_connection_external_event",
        table_name="channel_inbound_events",
    )
    op.drop_index(
        "ix_channel_inbound_events_outbound_message_id",
        table_name="channel_inbound_events",
    )
    op.drop_index("ix_channel_inbound_events_message_id", table_name="channel_inbound_events")
    op.drop_index(
        "ix_channel_inbound_events_channel_connection_id",
        table_name="channel_inbound_events",
    )
    op.drop_index("ix_channel_inbound_events_workspace_id", table_name="channel_inbound_events")
    op.drop_table("channel_inbound_events")

    op.drop_index(
        "uq_messages_workspace_connection_external",
        table_name="messages",
    )
    op.create_index(
        "ix_messages_workspace_external",
        "messages",
        ["workspace_id", "external_message_id"],
        unique=False,
    )
    op.drop_index("ix_messages_channel_connection_id", table_name="messages")
    op.drop_constraint(
        "fk_messages_channel_connection",
        "messages",
        type_="foreignkey",
    )
    op.drop_column("messages", "channel_connection_id")

    op.drop_index(
        "uq_conversations_workspace_connection_external",
        table_name="conversations",
    )
    op.create_index(
        "uq_conversations_workspace_channel_external",
        "conversations",
        ["workspace_id", "channel", "external_conversation_id"],
        unique=True,
        postgresql_where=sa.text("external_conversation_id IS NOT NULL"),
    )
    op.drop_index("ix_conversations_channel_connection_id", table_name="conversations")
    op.drop_constraint(
        "fk_conversations_channel_connection",
        "conversations",
        type_="foreignkey",
    )
    op.drop_column("conversations", "channel_connection_id")

    op.drop_index(
        "ix_channel_identities_workspace_patient",
        table_name="channel_identities",
    )
    op.drop_index("ix_channel_identities_patient_id", table_name="channel_identities")
    op.drop_index(
        "ix_channel_identities_channel_connection_id",
        table_name="channel_identities",
    )
    op.drop_index("ix_channel_identities_workspace_id", table_name="channel_identities")
    op.drop_table("channel_identities")

    op.drop_index(
        "uq_channel_connections_workspace_external_account",
        table_name="channel_connections",
    )
    op.drop_index(
        "ix_channel_connections_workspace_status",
        table_name="channel_connections",
    )
    op.drop_index(
        "ix_channel_connections_created_by_user_id",
        table_name="channel_connections",
    )
    op.drop_index("ix_channel_connections_workspace_id", table_name="channel_connections")
    op.drop_table("channel_connections")
