from __future__ import annotations

from uuid import UUID

from sqlalchemy import CheckConstraint, ForeignKey, Index, String, UniqueConstraint, text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.database.base import Base, TimestampMixin, UUIDPrimaryKeyMixin

CHANNEL_CONNECTION_CHANNELS = (
    "whatsapp",
    "instagram",
    "facebook",
    "web",
    "email",
    "sms",
    "other",
)
CHANNEL_CONNECTION_STATUSES = ("active", "paused", "disconnected")


class ChannelConnection(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "channel_connections"
    __table_args__ = (
        UniqueConstraint(
            "workspace_id",
            "id",
            name="uq_channel_connections_workspace_id_id",
        ),
        CheckConstraint(
            "channel IN ('whatsapp', 'instagram', 'facebook', 'web', 'email', 'sms', 'other')",
            name="channel_connection_channel_valid",
        ),
        CheckConstraint(
            "status IN ('active', 'paused', 'disconnected')",
            name="channel_connection_status_valid",
        ),
        Index(
            "uq_channel_connections_workspace_external_account",
            "workspace_id",
            "channel",
            "provider",
            "external_account_id",
            unique=True,
            postgresql_where=text("external_account_id IS NOT NULL"),
        ),
        Index(
            "ix_channel_connections_workspace_status",
            "workspace_id",
            "status",
        ),
    )

    workspace_id: Mapped[UUID] = mapped_column(
        ForeignKey("workspaces.id", ondelete="CASCADE"),
        index=True,
        nullable=False,
    )
    channel: Mapped[str] = mapped_column(String(24), nullable=False)
    provider: Mapped[str] = mapped_column(String(40), nullable=False)
    display_name: Mapped[str] = mapped_column(String(120), nullable=False)
    status: Mapped[str] = mapped_column(
        String(20),
        nullable=False,
        default="active",
        server_default="active",
    )
    external_account_id: Mapped[str | None] = mapped_column(String(255), nullable=True)
    adapter_token_hash: Mapped[str] = mapped_column(String(64), unique=True, nullable=False)
    created_by_user_id: Mapped[UUID | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    config_json: Mapped[dict] = mapped_column(
        "config",
        JSONB,
        nullable=False,
        default=dict,
        server_default="{}",
    )
