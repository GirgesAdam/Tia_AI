from __future__ import annotations

from uuid import UUID

from sqlalchemy import CheckConstraint, ForeignKey, ForeignKeyConstraint, Index, String, Text, text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.database.base import Base, TimestampMixin, UUIDPrimaryKeyMixin

MESSAGE_SENDER_TYPES = ("patient", "ai", "staff", "system")
MESSAGE_DIRECTIONS = ("inbound", "outbound", "internal")
MESSAGE_STATUSES = ("received", "queued", "sent", "delivered", "read", "failed", "cancelled")


class Message(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "messages"
    __table_args__ = (
        CheckConstraint(
            "sender_type IN ('patient', 'ai', 'staff', 'system')",
            name="message_sender_type_valid",
        ),
        CheckConstraint(
            "direction IN ('inbound', 'outbound', 'internal')",
            name="message_direction_valid",
        ),
        CheckConstraint(
            "delivery_status IN ('received', 'queued', 'sent', 'delivered', 'read', 'failed', 'cancelled')",
            name="message_delivery_status_valid",
        ),
        ForeignKeyConstraint(
            ["workspace_id", "conversation_id"],
            ["conversations.workspace_id", "conversations.id"],
            ondelete="CASCADE",
            name="fk_messages_conversation",
        ),
        ForeignKeyConstraint(
            ["workspace_id", "channel_connection_id"],
            ["channel_connections.workspace_id", "channel_connections.id"],
            name="fk_messages_channel_connection",
        ),
        Index("ix_messages_conversation_created", "conversation_id", "created_at"),
        Index(
            "uq_messages_workspace_connection_external",
            "workspace_id",
            "channel_connection_id",
            "external_message_id",
            unique=True,
            postgresql_where=text(
                "channel_connection_id IS NOT NULL AND external_message_id IS NOT NULL"
            ),
        ),
    )

    workspace_id: Mapped[UUID] = mapped_column(index=True, nullable=False)
    conversation_id: Mapped[UUID] = mapped_column(index=True, nullable=False)
    channel_connection_id: Mapped[UUID | None] = mapped_column(
        index=True,
        nullable=True,
    )
    sender_type: Mapped[str] = mapped_column(String(20), nullable=False)
    direction: Mapped[str] = mapped_column(String(20), nullable=False)
    message_type: Mapped[str] = mapped_column(
        String(32),
        nullable=False,
        default="text",
        server_default="text",
    )
    content: Mapped[str | None] = mapped_column(Text, nullable=True)
    external_message_id: Mapped[str | None] = mapped_column(String(255), nullable=True)
    delivery_status: Mapped[str] = mapped_column(String(20), nullable=False)
    sent_by_user_id: Mapped[UUID | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"),
        index=True,
        nullable=True,
    )
    metadata_json: Mapped[dict] = mapped_column(
        "metadata",
        JSONB,
        nullable=False,
        default=dict,
        server_default="{}",
    )
