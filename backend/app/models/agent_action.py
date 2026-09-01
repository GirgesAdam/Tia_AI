from __future__ import annotations

from uuid import UUID

from sqlalchemy import CheckConstraint, ForeignKeyConstraint, Index, String, Text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.database.base import Base, TimestampMixin, UUIDPrimaryKeyMixin

AGENT_ACTION_STATUSES = ("success", "error", "blocked")


class AgentAction(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "agent_actions"
    __table_args__ = (
        CheckConstraint(
            "status IN ('success', 'error', 'blocked')",
            name="agent_action_status_valid",
        ),
        ForeignKeyConstraint(
            ["workspace_id"],
            ["workspaces.id"],
            ondelete="CASCADE",
            name="fk_agent_actions_workspace",
        ),
        ForeignKeyConstraint(
            ["workspace_id", "conversation_id"],
            ["conversations.workspace_id", "conversations.id"],
            ondelete="CASCADE",
            name="fk_agent_actions_conversation",
        ),
        ForeignKeyConstraint(
            ["workspace_id", "patient_id"],
            ["patients.workspace_id", "patients.id"],
            ondelete="CASCADE",
            name="fk_agent_actions_patient",
        ),
        ForeignKeyConstraint(
            ["workspace_id", "appointment_id"],
            ["appointments.workspace_id", "appointments.id"],
            ondelete="SET NULL",
            name="fk_agent_actions_appointment",
        ),
        Index("ix_agent_actions_workspace_created", "workspace_id", "created_at"),
        Index("ix_agent_actions_conversation_created", "conversation_id", "created_at"),
        Index("ix_agent_actions_run_id", "run_id"),
    )

    workspace_id: Mapped[UUID] = mapped_column(index=True, nullable=False)
    conversation_id: Mapped[UUID] = mapped_column(index=True, nullable=False)
    patient_id: Mapped[UUID] = mapped_column(index=True, nullable=False)
    appointment_id: Mapped[UUID | None] = mapped_column(index=True, nullable=True)
    run_id: Mapped[UUID] = mapped_column(index=True, nullable=False)
    tool_name: Mapped[str] = mapped_column(String(100), nullable=False)
    action_type: Mapped[str] = mapped_column(String(100), nullable=False)
    status: Mapped[str] = mapped_column(String(20), nullable=False)
    input_json: Mapped[dict] = mapped_column(
        JSONB, nullable=False, default=dict, server_default="{}"
    )
    output_json: Mapped[dict] = mapped_column(
        JSONB, nullable=False, default=dict, server_default="{}"
    )
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)
