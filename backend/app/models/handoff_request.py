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
    text,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.database.base import Base, TimestampMixin, UUIDPrimaryKeyMixin

HANDOFF_STATUSES = ("pending", "claimed", "resolved")
HANDOFF_CATEGORIES = (
    "medical",
    "complaint",
    "payment",
    "customer_request",
    "booking_exception",
    "agent_uncertain",
    "other",
)
HANDOFF_PRIORITIES = ("low", "normal", "high", "urgent")
HANDOFF_SOURCES = ("ai", "staff", "system", "customer")


class HandoffRequest(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "handoff_requests"
    __table_args__ = (
        UniqueConstraint(
            "workspace_id",
            "id",
            name="uq_handoff_requests_workspace_id_id",
        ),
        CheckConstraint(
            "status IN ('pending', 'claimed', 'resolved')",
            name="handoff_request_status_valid",
        ),
        CheckConstraint(
            "category IN ('medical', 'complaint', 'payment', 'customer_request', "
            "'booking_exception', 'agent_uncertain', 'other')",
            name="handoff_request_category_valid",
        ),
        CheckConstraint(
            "priority IN ('low', 'normal', 'high', 'urgent')",
            name="handoff_request_priority_valid",
        ),
        CheckConstraint(
            "source IN ('ai', 'staff', 'system', 'customer')",
            name="handoff_request_source_valid",
        ),
        ForeignKeyConstraint(
            ["workspace_id", "conversation_id"],
            ["conversations.workspace_id", "conversations.id"],
            ondelete="CASCADE",
            name="fk_handoff_requests_conversation",
        ),
        ForeignKeyConstraint(
            ["workspace_id", "patient_id"],
            ["patients.workspace_id", "patients.id"],
            ondelete="CASCADE",
            name="fk_handoff_requests_patient",
        ),
        Index(
            "uq_handoff_requests_active_conversation",
            "workspace_id",
            "conversation_id",
            unique=True,
            postgresql_where=text("status IN ('pending', 'claimed')"),
        ),
        Index(
            "ix_handoff_requests_workspace_queue",
            "workspace_id",
            "status",
            "priority",
            "created_at",
        ),
        Index(
            "ix_handoff_requests_workspace_assignee",
            "workspace_id",
            "assigned_user_id",
            "status",
        ),
    )

    workspace_id: Mapped[UUID] = mapped_column(index=True, nullable=False)
    conversation_id: Mapped[UUID] = mapped_column(index=True, nullable=False)
    patient_id: Mapped[UUID] = mapped_column(index=True, nullable=False)
    status: Mapped[str] = mapped_column(
        String(20),
        nullable=False,
        default="pending",
        server_default="pending",
    )
    category: Mapped[str] = mapped_column(
        String(40),
        nullable=False,
        default="other",
        server_default="other",
    )
    priority: Mapped[str] = mapped_column(
        String(20),
        nullable=False,
        default="normal",
        server_default="normal",
    )
    source: Mapped[str] = mapped_column(
        String(20),
        nullable=False,
        default="ai",
        server_default="ai",
    )
    reason: Mapped[str] = mapped_column(Text, nullable=False)
    context_json: Mapped[dict] = mapped_column(
        "context",
        JSONB,
        nullable=False,
        default=dict,
        server_default=text("'{}'::jsonb"),
    )
    assigned_user_id: Mapped[UUID | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"),
        index=True,
        nullable=True,
    )
    created_by_user_id: Mapped[UUID | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
    )
    claimed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    resolved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    resolved_by_user_id: Mapped[UUID | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
    )
    resolution_note: Mapped[str | None] = mapped_column(Text, nullable=True)
