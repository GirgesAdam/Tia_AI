from __future__ import annotations

from datetime import datetime
from uuid import UUID

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    DateTime,
    ForeignKey,
    ForeignKeyConstraint,
    Index,
    Integer,
    String,
    UniqueConstraint,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.database.base import Base, TimestampMixin, UUIDPrimaryKeyMixin

SYNC_DOMAINS = ("patients", "payments", "appointments")
SYNC_RUN_STATUSES = ("running", "succeeded", "partial", "failed")


class ClinicIntegrationSyncRun(UUIDPrimaryKeyMixin, Base):
    __tablename__ = "clinic_integration_sync_runs"
    __table_args__ = (
        CheckConstraint(
            "domain IN ('patients', 'payments', 'appointments')",
            name="domain_valid",
        ),
        CheckConstraint(
            "status IN ('running', 'succeeded', 'partial', 'failed')",
            name="status_valid",
        ),
        CheckConstraint("processed_count >= 0", name="processed_nonneg"),
        CheckConstraint("created_count >= 0", name="created_nonneg"),
        CheckConstraint("updated_count >= 0", name="updated_nonneg"),
        CheckConstraint("skipped_count >= 0", name="skipped_nonneg"),
        CheckConstraint("failed_count >= 0", name="failed_nonneg"),
        UniqueConstraint(
            "workspace_id",
            "id",
            name="uq_sync_runs_workspace_id",
        ),
        Index(
            "ix_clinic_integration_sync_runs_workspace_domain_started",
            "workspace_id",
            "domain",
            "started_at",
        ),
    )

    workspace_id: Mapped[UUID] = mapped_column(
        ForeignKey("clinic_integrations.workspace_id", ondelete="CASCADE", name="fk_sync_runs_integration"),
        nullable=False,
        index=True,
    )
    domain: Mapped[str] = mapped_column(String(24), nullable=False)
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="running")
    cursor_before: Mapped[str | None] = mapped_column(String(512), nullable=True)
    cursor_after: Mapped[str | None] = mapped_column(String(512), nullable=True)
    source_revision: Mapped[str | None] = mapped_column(String(255), nullable=True)
    processed_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0, server_default="0")
    created_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0, server_default="0")
    updated_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0, server_default="0")
    skipped_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0, server_default="0")
    failed_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0, server_default="0")
    started_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class ClinicIntegrationSyncCheckpoint(TimestampMixin, Base):
    __tablename__ = "clinic_integration_sync_checkpoints"
    __table_args__ = (
        CheckConstraint(
            "domain IN ('patients', 'payments', 'appointments')",
            name="domain_valid",
        ),
    )

    workspace_id: Mapped[UUID] = mapped_column(
        ForeignKey("clinic_integrations.workspace_id", ondelete="CASCADE", name="fk_sync_checkpoints_integration"),
        primary_key=True,
        nullable=False,
    )
    domain: Mapped[str] = mapped_column(String(24), primary_key=True, nullable=False)
    cursor: Mapped[str | None] = mapped_column(String(512), nullable=True)
    source_revision: Mapped[str | None] = mapped_column(String(255), nullable=True)
    last_success_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    last_run_id: Mapped[UUID | None] = mapped_column(
        ForeignKey("clinic_integration_sync_runs.id", ondelete="SET NULL", name="fk_sync_checkpoints_last_run"),
        nullable=True,
    )


class ClinicIntegrationSyncFailure(UUIDPrimaryKeyMixin, Base):
    __tablename__ = "clinic_integration_sync_failures"
    __table_args__ = (
        CheckConstraint(
            "domain IN ('patients', 'payments', 'appointments')",
            name="domain_valid",
        ),
        ForeignKeyConstraint(
            ["workspace_id", "run_id"],
            ["clinic_integration_sync_runs.workspace_id", "clinic_integration_sync_runs.id"],
            ondelete="CASCADE",
            name="fk_sync_failures_run",
        ),
        Index(
            "ix_clinic_integration_sync_failures_workspace_run",
            "workspace_id",
            "run_id",
        ),
    )

    workspace_id: Mapped[UUID] = mapped_column(
        ForeignKey("clinic_integrations.workspace_id", ondelete="CASCADE", name="fk_sync_failures_integration"),
        nullable=False,
        index=True,
    )
    run_id: Mapped[UUID] = mapped_column(nullable=False, index=True)
    domain: Mapped[str] = mapped_column(String(24), nullable=False)
    external_id_digest: Mapped[str] = mapped_column(String(64), nullable=False)
    error_code: Mapped[str] = mapped_column(String(80), nullable=False)
    message: Mapped[str] = mapped_column(String(300), nullable=False)
    retryable: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True, server_default="true")
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )


class ClinicIntegrationSyncSchedule(TimestampMixin, Base):
    __tablename__ = "clinic_integration_sync_schedules"
    __table_args__ = (
        CheckConstraint(
            "interval_minutes >= 5 AND interval_minutes <= 1440",
            name="interval_valid",
        ),
        CheckConstraint("attempts >= 0", name="attempts_nonneg"),
        Index("ix_clinic_integration_sync_schedules_due", "enabled", "next_run_at"),
    )

    workspace_id: Mapped[UUID] = mapped_column(
        ForeignKey("clinic_integrations.workspace_id", ondelete="CASCADE"),
        primary_key=True,
        nullable=False,
    )
    enabled: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False, server_default="false")
    interval_minutes: Mapped[int] = mapped_column(Integer, nullable=False, default=15, server_default="15")
    next_run_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    locked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    attempts: Mapped[int] = mapped_column(Integer, nullable=False, default=0, server_default="0")
    last_error: Mapped[str | None] = mapped_column(String(300), nullable=True)
    last_completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
