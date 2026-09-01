from __future__ import annotations

from datetime import datetime
from uuid import UUID

from sqlalchemy import CheckConstraint, DateTime, ForeignKey, Index, Integer, String
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.database.base import Base, TimestampMixin, UUIDPrimaryKeyMixin


class ClinicDataIssue(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    """Deferred clinic-data issue that must not block onboarding.

    The source import remains read-only. Unsafe/ambiguous facts are quarantined and
    represented here with enough normalized context to repair them later without
    reopening the onboarding flow.
    """

    __tablename__ = "clinic_data_issues"
    __table_args__ = (
        CheckConstraint(
            "severity IN ('critical', 'normal', 'simple')",
            name="clinic_data_issue_severity_valid",
        ),
        CheckConstraint(
            "status IN ('open', 'resolved', 'ignored', 'auto_resolved')",
            name="clinic_data_issue_status_valid",
        ),
        Index("ix_clinic_data_issues_workspace_status", "workspace_id", "status"),
        Index("ix_clinic_data_issues_workspace_severity", "workspace_id", "severity"),
        Index("ix_clinic_data_issues_workspace_category", "workspace_id", "category"),
    )

    workspace_id: Mapped[UUID] = mapped_column(
        ForeignKey("workspaces.id", ondelete="CASCADE"), nullable=False
    )
    severity: Mapped[str] = mapped_column(String(16), nullable=False)
    status: Mapped[str] = mapped_column(
        String(20), nullable=False, default="open", server_default="open"
    )
    category: Mapped[str] = mapped_column(String(64), nullable=False)
    code: Mapped[str] = mapped_column(String(120), nullable=False)
    title: Mapped[str] = mapped_column(String(300), nullable=False)
    description: Mapped[str] = mapped_column(String(1200), nullable=False)
    entity_type: Mapped[str | None] = mapped_column(String(48), nullable=True)
    entity_external_id: Mapped[str | None] = mapped_column(String(512), nullable=True)
    related_external_id: Mapped[str | None] = mapped_column(String(512), nullable=True)
    occurrence_count: Mapped[int] = mapped_column(Integer, nullable=False, default=1, server_default="1")
    source_context: Mapped[dict] = mapped_column(
        JSONB, nullable=False, default=dict, server_default="{}"
    )
    resolution: Mapped[dict] = mapped_column(
        JSONB, nullable=False, default=dict, server_default="{}"
    )
    resolved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
