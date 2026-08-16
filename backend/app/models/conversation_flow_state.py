from __future__ import annotations

from datetime import datetime
from uuid import UUID

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    DateTime,
    ForeignKeyConstraint,
    Index,
    Integer,
    String,
    UniqueConstraint,
    text,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.database.base import Base, TimestampMixin, UUIDPrimaryKeyMixin


FLOW_TYPES = ("booking", "appointment_reschedule")
FLOW_STATUSES = (
    "collecting_requirements",
    "awaiting_option_selection",
    "ready_to_execute",
    "completed",
    "cancelled",
    "interrupted",
    "expired",
)


class ConversationFlowState(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "conversation_flow_states"
    __table_args__ = (
        UniqueConstraint(
            "workspace_id",
            "id",
            name="uq_conversation_flow_states_workspace_id_id",
        ),
        CheckConstraint(
            "flow_type IN ('booking', 'appointment_reschedule')",
            name="conversation_flow_state_type_valid",
        ),
        CheckConstraint(
            "status IN ('collecting_requirements', 'awaiting_option_selection', "
            "'ready_to_execute', 'completed', 'cancelled', 'interrupted', 'expired')",
            name="conversation_flow_state_status_valid",
        ),
        CheckConstraint(
            "version >= 1",
            name="conversation_flow_state_version_positive",
        ),
        ForeignKeyConstraint(
            ["workspace_id", "conversation_id"],
            ["conversations.workspace_id", "conversations.id"],
            ondelete="CASCADE",
            name="fk_conversation_flow_states_conversation",
        ),
        ForeignKeyConstraint(
            ["workspace_id", "patient_id"],
            ["patients.workspace_id", "patients.id"],
            ondelete="CASCADE",
            name="fk_conversation_flow_states_patient",
        ),
        Index(
            "uq_conversation_flow_states_active_conversation",
            "workspace_id",
            "conversation_id",
            unique=True,
            postgresql_where=text("is_active = true"),
        ),
        Index(
            "ix_conversation_flow_states_workspace_active",
            "workspace_id",
            "is_active",
            "expires_at",
        ),
        Index(
            "ix_conversation_flow_states_conversation_created",
            "conversation_id",
            "created_at",
        ),
    )

    workspace_id: Mapped[UUID] = mapped_column(index=True, nullable=False)
    conversation_id: Mapped[UUID] = mapped_column(index=True, nullable=False)
    patient_id: Mapped[UUID] = mapped_column(index=True, nullable=False)

    flow_type: Mapped[str] = mapped_column(String(40), nullable=False)
    status: Mapped[str] = mapped_column(
        String(40),
        nullable=False,
        default="collecting_requirements",
        server_default="collecting_requirements",
    )
    is_active: Mapped[bool] = mapped_column(
        Boolean,
        nullable=False,
        default=True,
        server_default=text("true"),
    )

    capabilities: Mapped[list] = mapped_column(
        JSONB,
        nullable=False,
        default=list,
        server_default=text("'[]'::jsonb"),
    )
    entity_state: Mapped[dict] = mapped_column(
        JSONB,
        nullable=False,
        default=dict,
        server_default=text("'{}'::jsonb"),
    )
    missing_information: Mapped[list] = mapped_column(
        JSONB,
        nullable=False,
        default=list,
        server_default=text("'[]'::jsonb"),
    )
    pending_action: Mapped[dict] = mapped_column(
        JSONB,
        nullable=False,
        default=dict,
        server_default=text("'{}'::jsonb"),
    )
    option_snapshot: Mapped[dict] = mapped_column(
        JSONB,
        nullable=False,
        default=dict,
        server_default=text("'{}'::jsonb"),
    )
    last_decision: Mapped[dict] = mapped_column(
        JSONB,
        nullable=False,
        default=dict,
        server_default=text("'{}'::jsonb"),
    )

    version: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        default=1,
        server_default="1",
    )
    expires_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        index=True,
    )
    last_turn_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
    )
    completed_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )
    interrupted_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )
