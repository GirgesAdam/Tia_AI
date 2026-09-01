from __future__ import annotations

from datetime import datetime
from uuid import UUID

from sqlalchemy import CheckConstraint, DateTime, ForeignKey, Index, String, Text, Uuid, func
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.database.base import Base, UUIDPrimaryKeyMixin

ACTIVITY_ACTOR_TYPES = ("staff", "ai", "system")


class ActivityEvent(UUIDPrimaryKeyMixin, Base):
    __tablename__ = "activity_events"
    __table_args__ = (
        CheckConstraint(
            "actor_type IN ('staff', 'ai', 'system')",
            name="activity_event_actor_type_valid",
        ),
        Index(
            "ix_activity_events_workspace_created",
            "workspace_id",
            "created_at",
        ),
        Index(
            "ix_activity_events_workspace_actor_created",
            "workspace_id",
            "actor_type",
            "created_at",
        ),
        Index(
            "ix_activity_events_workspace_entity_created",
            "workspace_id",
            "entity_type",
            "created_at",
        ),
    )

    workspace_id: Mapped[UUID] = mapped_column(
        ForeignKey("workspaces.id", ondelete="CASCADE"),
        index=True,
        nullable=False,
    )
    actor_type: Mapped[str] = mapped_column(String(20), nullable=False)
    actor_user_id: Mapped[UUID | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"),
        index=True,
        nullable=True,
    )
    action: Mapped[str] = mapped_column(String(80), nullable=False, index=True)
    entity_type: Mapped[str] = mapped_column(String(40), nullable=False, index=True)
    entity_id: Mapped[UUID | None] = mapped_column(Uuid(as_uuid=True), nullable=True, index=True)
    summary: Mapped[str] = mapped_column(Text, nullable=False)
    metadata_json: Mapped[dict] = mapped_column(
        "metadata",
        JSONB,
        nullable=False,
        default=dict,
        server_default="{}",
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
        index=True,
    )
