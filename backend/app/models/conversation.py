from __future__ import annotations

from datetime import datetime
from uuid import UUID

from sqlalchemy import (
    CheckConstraint,
    DateTime,
    ForeignKey,
    ForeignKeyConstraint,
    Index,
    String,
    UniqueConstraint,
    text,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.database.base import Base, TimestampMixin, UUIDPrimaryKeyMixin

CONVERSATION_CHANNELS = (
    "whatsapp",
    "instagram",
    "facebook",
    "web",
    "email",
    "sms",
    "phone",
    "other",
)
CONVERSATION_STATUSES = ("open", "pending", "closed")


class Conversation(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "conversations"
    __table_args__ = (
        UniqueConstraint("workspace_id", "id", name="uq_conversations_workspace_id_id"),
        CheckConstraint(
            "channel IN ('whatsapp', 'instagram', 'facebook', 'web', 'email', "
            "'sms', 'phone', 'other')",
            name="conversation_channel_valid",
        ),
        CheckConstraint(
            "status IN ('open', 'pending', 'closed')",
            name="conversation_status_valid",
        ),
        ForeignKeyConstraint(
            ["workspace_id", "patient_id"],
            ["patients.workspace_id", "patients.id"],
            ondelete="CASCADE",
            name="fk_conversations_patient",
        ),
        ForeignKeyConstraint(
            ["workspace_id", "channel_connection_id"],
            ["channel_connections.workspace_id", "channel_connections.id"],
            name="fk_conversations_channel_connection",
        ),
        Index(
            "uq_conversations_workspace_connection_external",
            "workspace_id",
            "channel_connection_id",
            "external_conversation_id",
            unique=True,
            postgresql_where=text(
                "channel_connection_id IS NOT NULL AND external_conversation_id IS NOT NULL"
            ),
        ),
        Index("ix_conversations_workspace_status", "workspace_id", "status"),
    )

    workspace_id: Mapped[UUID] = mapped_column(index=True, nullable=False)
    patient_id: Mapped[UUID] = mapped_column(index=True, nullable=False)
    channel: Mapped[str] = mapped_column(String(24), nullable=False)
    status: Mapped[str] = mapped_column(
        String(20),
        nullable=False,
        default="open",
        server_default="open",
    )
    external_conversation_id: Mapped[str | None] = mapped_column(String(255), nullable=True)
    channel_connection_id: Mapped[UUID | None] = mapped_column(
        index=True,
        nullable=True,
    )
    assigned_user_id: Mapped[UUID | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"),
        index=True,
        nullable=True,
    )
    subject: Mapped[str | None] = mapped_column(String(250), nullable=True)
    started_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
    )
    last_message_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        index=True,
        nullable=True,
    )
    closed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
