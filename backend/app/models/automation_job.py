from __future__ import annotations

from datetime import datetime
from uuid import UUID

from sqlalchemy import (
    CheckConstraint,
    DateTime,
    ForeignKey,
    ForeignKeyConstraint,
    Index,
    Integer,
    String,
    Text,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.database.base import Base, TimestampMixin, UUIDPrimaryKeyMixin

AUTOMATION_JOB_STATUSES = (
    "queued",
    "processing",
    "dispatched",
    "skipped",
    "failed",
    "cancelled",
)


class AutomationJob(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "automation_jobs"
    __table_args__ = (
        CheckConstraint(
            "status IN ('queued', 'processing', 'dispatched', 'skipped', 'failed', 'cancelled')",
            name="automation_job_status_valid",
        ),
        ForeignKeyConstraint(
            ["workspace_id", "appointment_id"],
            ["appointments.workspace_id", "appointments.id"],
            ondelete="CASCADE",
            name="fk_automation_jobs_appointment",
        ),
        ForeignKeyConstraint(
            ["workspace_id", "patient_id"],
            ["patients.workspace_id", "patients.id"],
            ondelete="CASCADE",
            name="fk_automation_jobs_patient",
        ),
        Index("uq_automation_jobs_workspace_dedupe", "workspace_id", "dedupe_key", unique=True),
        Index("ix_automation_jobs_workspace_due", "workspace_id", "status", "scheduled_for", "next_attempt_at"),
        Index("ix_automation_jobs_appointment", "appointment_id", "status"),
    )

    workspace_id: Mapped[UUID] = mapped_column(index=True, nullable=False)
    rule_id: Mapped[UUID] = mapped_column(
        ForeignKey("automation_rules.id", ondelete="CASCADE"),
        index=True,
        nullable=False,
    )
    appointment_id: Mapped[UUID] = mapped_column(index=True, nullable=False)
    patient_id: Mapped[UUID] = mapped_column(index=True, nullable=False)

    status: Mapped[str] = mapped_column(String(20), nullable=False, default="queued", server_default="queued")
    scheduled_for: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, index=True)
    dedupe_key: Mapped[str] = mapped_column(String(255), nullable=False)
    attempts: Mapped[int] = mapped_column(Integer, nullable=False, default=0, server_default="0")
    locked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    next_attempt_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    message_id: Mapped[UUID | None] = mapped_column(
        ForeignKey("messages.id", ondelete="SET NULL"),
        index=True,
        nullable=True,
    )
    dispatch_id: Mapped[UUID | None] = mapped_column(
        ForeignKey("message_dispatches.id", ondelete="SET NULL"),
        index=True,
        nullable=True,
    )

    last_error: Mapped[str | None] = mapped_column(Text, nullable=True)
    payload_json: Mapped[dict] = mapped_column("payload", JSONB, nullable=False, default=dict, server_default="{}")
    result_json: Mapped[dict] = mapped_column("result", JSONB, nullable=False, default=dict, server_default="{}")
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
