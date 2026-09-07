from __future__ import annotations

from datetime import datetime
from uuid import UUID

from sqlalchemy import ForeignKey, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.database.base import Base, TimestampMixin


class ChannelProviderCredential(TimestampMixin, Base):
    __tablename__ = "channel_provider_credentials"
    __table_args__ = (
        UniqueConstraint(
            "workspace_id",
            "channel_connection_id",
            name="uq_channel_provider_credentials_workspace_connection",
        ),
    )

    channel_connection_id: Mapped[UUID] = mapped_column(
        ForeignKey("channel_connections.id", ondelete="CASCADE"),
        primary_key=True,
        nullable=False,
    )
    workspace_id: Mapped[UUID] = mapped_column(
        ForeignKey("workspaces.id", ondelete="CASCADE"),
        index=True,
        nullable=False,
    )
    provider: Mapped[str] = mapped_column(String(40), nullable=False)
    access_token_ciphertext: Mapped[str] = mapped_column(Text, nullable=False)
    token_type: Mapped[str] = mapped_column(String(32), nullable=False, default="bearer", server_default="bearer")
    expires_at: Mapped[datetime | None] = mapped_column(nullable=True)
