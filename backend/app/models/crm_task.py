from __future__ import annotations

from datetime import datetime
from uuid import UUID

from sqlalchemy import (
    CheckConstraint,
    DateTime,
    ForeignKey,
    ForeignKeyConstraint,
    Index,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.database.base import Base, TimestampMixin, UUIDPrimaryKeyMixin

CRM_TASK_TYPES = ("follow_up", "general")
CRM_TASK_STATUSES = ("pending", "in_progress", "completed", "cancelled")
CRM_TASK_PRIORITIES = ("low", "normal", "high", "urgent")
CRM_TASK_SOURCES = ("manual", "ai", "system")
CRM_TASK_EXECUTION_MODES = ("human", "ai")


class CRMTask(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "crm_tasks"
    __table_args__ = (
        UniqueConstraint("workspace_id", "id", name="uq_crm_tasks_workspace_id_id"),
        CheckConstraint(
            "task_type IN ('follow_up', 'general')",
            name="crm_task_type_valid",
        ),
        CheckConstraint(
            "status IN ('pending', 'in_progress', 'completed', 'cancelled')",
            name="crm_task_status_valid",
        ),
        CheckConstraint(
            "priority IN ('low', 'normal', 'high', 'urgent')",
            name="crm_task_priority_valid",
        ),
        CheckConstraint(
            "source IN ('manual', 'ai', 'system')",
            name="crm_task_source_valid",
        ),
        CheckConstraint(
            "execution_mode IN ('human', 'ai')",
            name="crm_task_execution_mode_valid",
        ),
        ForeignKeyConstraint(
            ["workspace_id", "patient_id"],
            ["patients.workspace_id", "patients.id"],
            ondelete="CASCADE",
            name="fk_crm_tasks_patient",
        ),
        ForeignKeyConstraint(
            ["workspace_id", "lead_id"],
            ["leads.workspace_id", "leads.id"],
            name="fk_crm_tasks_lead",
        ),
        ForeignKeyConstraint(
            ["workspace_id", "conversation_id"],
            ["conversations.workspace_id", "conversations.id"],
            name="fk_crm_tasks_conversation",
        ),
        Index(
            "ix_crm_tasks_workspace_queue",
            "workspace_id",
            "status",
            "due_at",
            "assigned_user_id",
        ),
        Index(
            "ix_crm_tasks_workspace_patient_status",
            "workspace_id",
            "patient_id",
            "status",
        ),
        Index(
            "uq_crm_tasks_workspace_dedupe",
            "workspace_id",
            "dedupe_key",
            unique=True,
        ),
    )

    workspace_id: Mapped[UUID] = mapped_column(
        ForeignKey("workspaces.id", ondelete="CASCADE"),
        index=True,
        nullable=False,
    )
    patient_id: Mapped[UUID] = mapped_column(index=True, nullable=False)
    lead_id: Mapped[UUID | None] = mapped_column(index=True, nullable=True)
    conversation_id: Mapped[UUID | None] = mapped_column(index=True, nullable=True)

    assigned_user_id: Mapped[UUID | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"),
        index=True,
        nullable=True,
    )
    created_by_user_id: Mapped[UUID | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
    )
    completed_by_user_id: Mapped[UUID | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
    )

    task_type: Mapped[str] = mapped_column(
        String(24),
        nullable=False,
        default="follow_up",
        server_default="follow_up",
    )
    source: Mapped[str] = mapped_column(
        String(20),
        nullable=False,
        default="manual",
        server_default="manual",
    )
    status: Mapped[str] = mapped_column(
        String(20),
        nullable=False,
        default="pending",
        server_default="pending",
    )
    execution_mode: Mapped[str] = mapped_column(
        String(16),
        nullable=False,
        default="human",
        server_default="human",
    )
    priority: Mapped[str] = mapped_column(
        String(20),
        nullable=False,
        default="normal",
        server_default="normal",
    )
    title: Mapped[str] = mapped_column(String(200), nullable=False)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    due_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True, nullable=False)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    dedupe_key: Mapped[str | None] = mapped_column(String(255), nullable=True)
