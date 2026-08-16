from __future__ import annotations

from datetime import datetime
from uuid import UUID

from sqlalchemy import (
    CheckConstraint,
    DateTime,
    ForeignKey,
    ForeignKeyConstraint,
    Index,
    Integer,
    String,
    text,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.database.base import Base, TimestampMixin, UUIDPrimaryKeyMixin

MESSAGE_DISPATCH_STATUSES = (
    "queued",
    "processing",
    "sent",
    "delivered",
    "read",
    "failed",
    "cancelled",
)


class MessageDispatch(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "message_dispatches"
    __table_args__ = (
        CheckConstraint(
            "status IN ('queued', 'processing', 'sent', 'delivered', 'read', 'failed', 'cancelled')",
            name="message_dispatch_status_valid",
        ),
        ForeignKeyConstraint(
            ["workspace_id", "channel_connection_id"],
            ["channel_connections.workspace_id", "channel_connections.id"],
            ondelete="CASCADE",
            name="fk_message_dispatches_connection",
        ),
        Index(
            "uq_message_dispatches_workspace_message",
            "workspace_id",
            "message_id",
            unique=True,
        ),
        Index(
            "uq_message_dispatches_connection_provider_message",
            "channel_connection_id",
            "provider_message_id",
            unique=True,
            postgresql_where=text("provider_message_id IS NOT NULL"),
        ),
        Index(
            "ix_message_dispatches_connection_queue",
            "channel_connection_id",
            "status",
            "next_attempt_at",
            "created_at",
        ),
    )

    workspace_id: Mapped[UUID] = mapped_column(index=True, nullable=False)
    channel_connection_id: Mapped[UUID] = mapped_column(index=True, nullable=False)
    message_id: Mapped[UUID] = mapped_column(
        ForeignKey("messages.id", ondelete="CASCADE"),
        index=True,
        nullable=False,
    )
    status: Mapped[str] = mapped_column(
        String(20),
        nullable=False,
        default="queued",
        server_default="queued",
    )
    attempts: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        default=0,
        server_default="0",
    )
    provider_message_id: Mapped[str | None] = mapped_column(String(255), nullable=True)
    last_error: Mapped[str | None] = mapped_column(String(2000), nullable=True)
    next_attempt_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    locked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    sent_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    delivered_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    read_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    metadata_json: Mapped[dict] = mapped_column(
        "metadata",
        JSONB,
        nullable=False,
        default=dict,
        server_default="{}",
    )
