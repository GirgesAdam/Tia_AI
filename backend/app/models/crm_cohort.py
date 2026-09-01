from __future__ import annotations

from uuid import UUID

from sqlalchemy import CheckConstraint, ForeignKey, ForeignKeyConstraint, Index, Integer, String, Text, UniqueConstraint
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.database.base import Base, TimestampMixin, UUIDPrimaryKeyMixin

CRM_COHORT_SOURCES = ("analytics_bi",)
CRM_COHORT_STATUSES = ("active", "archived")


class CRMCohort(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "crm_cohorts"
    __table_args__ = (
        UniqueConstraint("workspace_id", "id", name="uq_crm_cohorts_workspace_id_id"),
        UniqueConstraint("workspace_id", "request_key", name="uq_crm_cohorts_workspace_request_key"),
        CheckConstraint("source IN ('analytics_bi')", name="crm_cohort_source_valid"),
        CheckConstraint("status IN ('active', 'archived')", name="crm_cohort_status_valid"),
        CheckConstraint("member_count >= 1 AND member_count <= 25", name="crm_cohort_member_count_valid"),
        Index("ix_crm_cohorts_workspace_created", "workspace_id", "created_at"),
    )

    workspace_id: Mapped[UUID] = mapped_column(
        ForeignKey("workspaces.id", ondelete="CASCADE"), index=True, nullable=False
    )
    created_by_user_id: Mapped[UUID | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    name: Mapped[str] = mapped_column(String(160), nullable=False)
    request_key: Mapped[str] = mapped_column(String(64), nullable=False)
    source: Mapped[str] = mapped_column(String(24), nullable=False, default="analytics_bi", server_default="analytics_bi")
    status: Mapped[str] = mapped_column(String(16), nullable=False, default="active", server_default="active")
    analytics_operation: Mapped[str] = mapped_column(String(48), nullable=False)
    question: Mapped[str] = mapped_column(Text, nullable=False)
    plan_json: Mapped[dict] = mapped_column("plan", JSONB, nullable=False, default=dict, server_default="{}")
    period_label: Mapped[str] = mapped_column(String(120), nullable=False)
    member_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0, server_default="0")


class CRMCohortMember(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "crm_cohort_members"
    __table_args__ = (
        ForeignKeyConstraint(
            ["workspace_id", "cohort_id"],
            ["crm_cohorts.workspace_id", "crm_cohorts.id"],
            ondelete="CASCADE",
            name="fk_crm_cohort_members_cohort",
        ),
        ForeignKeyConstraint(
            ["workspace_id", "patient_id"],
            ["patients.workspace_id", "patients.id"],
            ondelete="CASCADE",
            name="fk_crm_cohort_members_patient",
        ),
        UniqueConstraint("cohort_id", "patient_id", name="uq_crm_cohort_members_cohort_patient"),
        CheckConstraint("rank >= 1 AND rank <= 25", name="crm_cohort_member_rank_valid"),
        Index("ix_crm_cohort_members_workspace_patient", "workspace_id", "patient_id"),
        Index("ix_crm_cohort_members_cohort_rank", "cohort_id", "rank"),
    )

    workspace_id: Mapped[UUID] = mapped_column(index=True, nullable=False)
    cohort_id: Mapped[UUID] = mapped_column(index=True, nullable=False)
    patient_id: Mapped[UUID] = mapped_column(index=True, nullable=False)
    rank: Mapped[int] = mapped_column(Integer, nullable=False)
    snapshot_metrics_json: Mapped[list] = mapped_column(
        "snapshot_metrics", JSONB, nullable=False, default=list, server_default="[]"
    )
