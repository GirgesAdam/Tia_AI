from __future__ import annotations

from uuid import UUID

from sqlalchemy import CheckConstraint, ForeignKey, ForeignKeyConstraint, Index, String
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.database.base import Base, TimestampMixin, UUIDPrimaryKeyMixin

HANDOFF_EVENT_TYPES = (
    "created",
    "escalated",
    "claimed",
    "assigned",
    "staff_replied",
    "resolved",
    "reopened",
)
HANDOFF_ACTOR_TYPES = ("ai", "staff", "system")


class HandoffEvent(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "handoff_events"
    __table_args__ = (
        CheckConstraint(
            "event_type IN ('created', 'escalated', 'claimed', 'assigned', 'staff_replied', "
            "'resolved', 'reopened')",
            name="handoff_event_type_valid",
        ),
        CheckConstraint(
            "actor_type IN ('ai', 'staff', 'system')",
            name="handoff_event_actor_type_valid",
        ),
        ForeignKeyConstraint(
            ["workspace_id", "handoff_request_id"],
            ["handoff_requests.workspace_id", "handoff_requests.id"],
            ondelete="CASCADE",
            name="fk_handoff_events_handoff",
        ),
        ForeignKeyConstraint(
            ["workspace_id", "conversation_id"],
            ["conversations.workspace_id", "conversations.id"],
            ondelete="CASCADE",
            name="fk_handoff_events_conversation",
        ),
        Index(
            "ix_handoff_events_handoff_created",
            "handoff_request_id",
            "created_at",
        ),
        Index(
            "ix_handoff_events_workspace_created",
            "workspace_id",
            "created_at",
        ),
    )

    workspace_id: Mapped[UUID] = mapped_column(index=True, nullable=False)
    handoff_request_id: Mapped[UUID] = mapped_column(index=True, nullable=False)
    conversation_id: Mapped[UUID] = mapped_column(index=True, nullable=False)
    event_type: Mapped[str] = mapped_column(String(32), nullable=False)
    actor_type: Mapped[str] = mapped_column(String(20), nullable=False)
    actor_user_id: Mapped[UUID | None] = mapped_column(
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
