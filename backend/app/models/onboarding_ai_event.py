from __future__ import annotations

from uuid import UUID

from sqlalchemy import (
    CheckConstraint,
    ForeignKey,
    ForeignKeyConstraint,
    Index,
    Integer,
    String,
    Text,
    text,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.database.base import Base, TimestampMixin, UUIDPrimaryKeyMixin


class OnboardingAIEvent(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "onboarding_ai_events"
    __table_args__ = (
        CheckConstraint(
            "event_type IN ('started', 'message', 'plan_proposed', "
            "'plan_revised', 'confirmed', 'write_completed', 'cancelled', "
            "'expired', 'failed')",
            name="onboarding_ai_event_type_valid",
        ),
        CheckConstraint(
            "actor_type IN ('admin', 'planner', 'system')",
            name="onboarding_ai_event_actor_valid",
        ),
        ForeignKeyConstraint(
            ["workspace_id", "session_id"],
            ["onboarding_ai_sessions.workspace_id", "onboarding_ai_sessions.id"],
            ondelete="CASCADE",
            name="fk_onboarding_ai_events_session",
        ),
        Index(
            "ix_onboarding_ai_events_session_created",
            "session_id",
            "created_at",
        ),
    )

    workspace_id: Mapped[UUID] = mapped_column(index=True, nullable=False)
    session_id: Mapped[UUID] = mapped_column(index=True, nullable=False)
    user_id: Mapped[UUID | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
    )
    event_type: Mapped[str] = mapped_column(String(40), nullable=False)
    actor_type: Mapped[str] = mapped_column(String(30), nullable=False)
    state_version: Mapped[int] = mapped_column(Integer, nullable=False)
    content: Mapped[str | None] = mapped_column(Text, nullable=True)
    event_metadata: Mapped[dict] = mapped_column(
        "metadata",
        JSONB,
        nullable=False,
        default=dict,
        server_default=text("'{}'::jsonb"),
    )
