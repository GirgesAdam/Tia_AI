from __future__ import annotations

from datetime import datetime
from uuid import UUID

from sqlalchemy import CheckConstraint, DateTime, ForeignKeyConstraint, Index, String
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.database.base import Base, TimestampMixin, UUIDPrimaryKeyMixin

CHANNEL_DELIVERY_STATUSES = ("sent", "delivered", "read", "failed")


class ChannelDeliveryEvent(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "channel_delivery_events"
    __table_args__ = (
        CheckConstraint(
            "status IN ('sent', 'delivered', 'read', 'failed')",
            name="channel_delivery_event_status_valid",
        ),
        ForeignKeyConstraint(
            ["workspace_id", "channel_connection_id"],
            ["channel_connections.workspace_id", "channel_connections.id"],
            ondelete="CASCADE",
            name="fk_channel_delivery_events_connection",
        ),
        Index(
            "uq_channel_delivery_events_connection_external_event",
            "channel_connection_id",
            "external_event_id",
            unique=True,
        ),
        Index(
            "ix_channel_delivery_events_provider_pending",
            "channel_connection_id",
            "provider_message_id",
            "processed_at",
        ),
    )

    workspace_id: Mapped[UUID] = mapped_column(index=True, nullable=False)
    channel_connection_id: Mapped[UUID] = mapped_column(index=True, nullable=False)
    provider_message_id: Mapped[str] = mapped_column(String(255), nullable=False)
    external_event_id: Mapped[str] = mapped_column(String(512), nullable=False)
    status: Mapped[str] = mapped_column(String(20), nullable=False)
    occurred_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    processed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    payload_json: Mapped[dict] = mapped_column(
        "payload",
        JSONB,
        nullable=False,
        default=dict,
        server_default="{}",
    )
