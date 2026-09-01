from __future__ import annotations

from uuid import UUID

from sqlalchemy import ForeignKeyConstraint, Index, String, UniqueConstraint
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.database.base import Base, TimestampMixin, UUIDPrimaryKeyMixin


class ChannelIdentity(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "channel_identities"
    __table_args__ = (
        UniqueConstraint(
            "workspace_id",
            "id",
            name="uq_channel_identities_workspace_id_id",
        ),
        UniqueConstraint(
            "channel_connection_id",
            "external_user_id",
            name="uq_channel_identities_connection_external_user",
        ),
        ForeignKeyConstraint(
            ["workspace_id", "channel_connection_id"],
            ["channel_connections.workspace_id", "channel_connections.id"],
            ondelete="CASCADE",
            name="fk_channel_identities_connection",
        ),
        ForeignKeyConstraint(
            ["workspace_id", "patient_id"],
            ["patients.workspace_id", "patients.id"],
            ondelete="CASCADE",
            name="fk_channel_identities_patient",
        ),
        Index(
            "ix_channel_identities_workspace_patient",
            "workspace_id",
            "patient_id",
        ),
    )

    workspace_id: Mapped[UUID] = mapped_column(index=True, nullable=False)
    channel_connection_id: Mapped[UUID] = mapped_column(index=True, nullable=False)
    patient_id: Mapped[UUID] = mapped_column(index=True, nullable=False)
    external_user_id: Mapped[str] = mapped_column(String(255), nullable=False)
    display_name: Mapped[str | None] = mapped_column(String(200), nullable=True)
    phone: Mapped[str | None] = mapped_column(String(40), nullable=True)
    metadata_json: Mapped[dict] = mapped_column(
        "metadata",
        JSONB,
        nullable=False,
        default=dict,
        server_default="{}",
    )
