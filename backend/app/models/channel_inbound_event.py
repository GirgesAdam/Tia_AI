from __future__ import annotations

from uuid import UUID

from sqlalchemy import CheckConstraint, ForeignKey, ForeignKeyConstraint, Index, Integer, String
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.database.base import Base, TimestampMixin, UUIDPrimaryKeyMixin

CHANNEL_INBOUND_STATUSES = ("received", "processing", "processed", "failed")


class ChannelInboundEvent(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "channel_inbound_events"
    __table_args__ = (
        CheckConstraint(
            "status IN ('received', 'processing', 'processed', 'failed')",
            name="channel_inbound_event_status_valid",
        ),
        ForeignKeyConstraint(
            ["workspace_id", "channel_connection_id"],
            ["channel_connections.workspace_id", "channel_connections.id"],
            ondelete="CASCADE",
            name="fk_channel_inbound_events_connection",
        ),
        Index(
            "uq_channel_inbound_events_connection_external_event",
            "channel_connection_id",
            "external_event_id",
            unique=True,
        ),
        Index(
            "ix_channel_inbound_events_workspace_status",
            "workspace_id",
            "status",
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
    outbound_message_id: Mapped[UUID | None] = mapped_column(
        ForeignKey("messages.id", ondelete="SET NULL"),
        index=True,
        nullable=True,
    )
    external_event_id: Mapped[str] = mapped_column(String(255), nullable=False)
    status: Mapped[str] = mapped_column(
        String(20),
        nullable=False,
        default="received",
        server_default="received",
    )
    attempts: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        default=0,
        server_default="0",
    )
    last_error: Mapped[str | None] = mapped_column(String(2000), nullable=True)
    payload_json: Mapped[dict] = mapped_column(
        "payload",
        JSONB,
        nullable=False,
        default=dict,
        server_default="{}",
    )
