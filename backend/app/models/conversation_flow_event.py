from __future__ import annotations

from uuid import UUID

from sqlalchemy import (
    CheckConstraint,
    ForeignKeyConstraint,
    Index,
    Integer,
    String,
    text,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.database.base import Base, TimestampMixin, UUIDPrimaryKeyMixin


FLOW_EVENT_TYPES = (
    "started",
    "updated",
    "options_presented",
    "write_authorized",
    "write_completed",
    "completed",
    "cancelled",
    "interrupted",
    "expired",
    "conflict",
)
FLOW_EVENT_ACTORS = ("router", "flow_interpreter", "agent", "tool", "system")


class ConversationFlowEvent(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "conversation_flow_events"
    __table_args__ = (
        CheckConstraint(
            "event_type IN ('started', 'updated', 'options_presented', "
            "'write_authorized', 'write_completed', 'completed', 'cancelled', "
            "'interrupted', 'expired', 'conflict')",
            name="conversation_flow_event_type_valid",
        ),
        CheckConstraint(
            "actor_type IN ('router', 'flow_interpreter', 'agent', 'tool', 'system')",
            name="conversation_flow_event_actor_valid",
        ),
        ForeignKeyConstraint(
            ["workspace_id", "flow_state_id"],
            ["conversation_flow_states.workspace_id", "conversation_flow_states.id"],
            ondelete="CASCADE",
            name="fk_conversation_flow_events_flow_state",
        ),
        ForeignKeyConstraint(
            ["workspace_id", "conversation_id"],
            ["conversations.workspace_id", "conversations.id"],
            ondelete="CASCADE",
            name="fk_conversation_flow_events_conversation",
        ),
        Index(
            "ix_conversation_flow_events_flow_created",
            "flow_state_id",
            "created_at",
        ),
        Index(
            "ix_conversation_flow_events_conversation_created",
            "conversation_id",
            "created_at",
        ),
        Index(
            "ix_conversation_flow_events_run_id",
            "run_id",
        ),
    )

    workspace_id: Mapped[UUID] = mapped_column(index=True, nullable=False)
    flow_state_id: Mapped[UUID] = mapped_column(index=True, nullable=False)
    conversation_id: Mapped[UUID] = mapped_column(index=True, nullable=False)
    run_id: Mapped[UUID | None] = mapped_column(index=True, nullable=True)
    event_type: Mapped[str] = mapped_column(String(40), nullable=False)
    actor_type: Mapped[str] = mapped_column(String(30), nullable=False)
    state_version: Mapped[int] = mapped_column(Integer, nullable=False)
    metadata_json: Mapped[dict] = mapped_column(
        "metadata",
        JSONB,
        nullable=False,
        default=dict,
        server_default=text("'{}'::jsonb"),
    )
