from __future__ import annotations

from datetime import datetime
from uuid import UUID

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    String,
    UniqueConstraint,
    text,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.database.base import Base, TimestampMixin, UUIDPrimaryKeyMixin

ONBOARDING_AI_STATUSES = (
    "drafting",
    "awaiting_confirmation",
    "executing",
    "completed",
    "cancelled",
    "expired",
    "failed",
)


class OnboardingAISession(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "onboarding_ai_sessions"
    __table_args__ = (
        UniqueConstraint(
            "workspace_id",
            "id",
            name="uq_onboarding_ai_sessions_workspace_id_id",
        ),
        CheckConstraint(
            "status IN ('drafting', 'awaiting_confirmation', 'executing', "
            "'completed', 'cancelled', 'expired', 'failed')",
            name="onboarding_ai_session_status_valid",
        ),
        CheckConstraint(
            "version >= 1",
            name="onboarding_ai_session_version_positive",
        ),
        Index(
            "uq_onboarding_ai_sessions_active_admin",
            "workspace_id",
            "created_by_user_id",
            unique=True,
            postgresql_where=text("is_active = true"),
        ),
    )

    workspace_id: Mapped[UUID] = mapped_column(
        ForeignKey("workspaces.id", ondelete="CASCADE"),
        index=True,
        nullable=False,
    )
    created_by_user_id: Mapped[UUID] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"),
        index=True,
        nullable=False,
    )
    status: Mapped[str] = mapped_column(
        String(40),
        nullable=False,
        default="drafting",
        server_default="drafting",
    )
    is_active: Mapped[bool] = mapped_column(
        Boolean,
        nullable=False,
        default=True,
        server_default=text("true"),
    )
    plan: Mapped[dict] = mapped_column(
        JSONB,
        nullable=False,
        default=dict,
        server_default=text("'{}'::jsonb"),
    )
    plan_summary: Mapped[dict] = mapped_column(
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
    last_decision: Mapped[dict] = mapped_column(
        JSONB,
        nullable=False,
        default=dict,
        server_default=text("'{}'::jsonb"),
    )
    execution_result: Mapped[dict] = mapped_column(
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
    cancelled_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )
