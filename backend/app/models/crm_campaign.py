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
    UniqueConstraint,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.database.base import Base, TimestampMixin, UUIDPrimaryKeyMixin

CRM_CAMPAIGN_STATUSES = ("draft", "confirmed", "cancelled")
CRM_CAMPAIGN_RECIPIENT_STATUSES = (
    "eligible",
    "skipped_no_consent",
    "skipped_inactive",
    "skipped_no_route",
    "cancelled_no_consent",
    "cancelled_inactive",
    "cancelled_no_route",
    "queued",
    "processing",
    "sent",
    "delivered",
    "read",
    "failed",
    "cancelled",
)


class CRMCampaign(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "crm_campaigns"
    __table_args__ = (
        UniqueConstraint("workspace_id", "id", name="uq_crm_campaigns_workspace_id_id"),
        UniqueConstraint("workspace_id", "request_key", name="uq_crm_campaigns_workspace_request_key"),
        CheckConstraint("status IN ('draft','confirmed','cancelled')", name="crm_campaign_status_valid"),
        CheckConstraint("recipient_count >= 1 AND recipient_count <= 25", name="crm_campaign_recipient_count_valid"),
        CheckConstraint("eligible_count >= 0 AND eligible_count <= recipient_count", name="crm_campaign_eligible_count_valid"),
        CheckConstraint("rate_limit_per_minute >= 1 AND rate_limit_per_minute <= 60", name="crm_campaign_rate_limit_valid"),
        Index("ix_crm_campaigns_workspace_created", "workspace_id", "created_at"),
    )

    workspace_id: Mapped[UUID] = mapped_column(ForeignKey("workspaces.id", ondelete="CASCADE"), index=True, nullable=False)
    cohort_id: Mapped[UUID] = mapped_column(index=True, nullable=False)
    channel_connection_id: Mapped[UUID] = mapped_column(index=True, nullable=False)
    created_by_user_id: Mapped[UUID | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    confirmed_by_user_id: Mapped[UUID | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    request_key: Mapped[str] = mapped_column(String(64), nullable=False)
    confirmation_key: Mapped[str | None] = mapped_column(String(64), nullable=True)
    name: Mapped[str] = mapped_column(String(160), nullable=False)
    status: Mapped[str] = mapped_column(String(16), nullable=False, default="draft", server_default="draft")
    template_name: Mapped[str] = mapped_column(String(160), nullable=False)
    template_language: Mapped[str] = mapped_column(String(32), nullable=False, default="ar", server_default="ar")
    body_parameter_keys_json: Mapped[list] = mapped_column("body_parameter_keys", JSONB, nullable=False, default=list, server_default="[]")
    rate_limit_per_minute: Mapped[int] = mapped_column(Integer, nullable=False, default=10, server_default="10")
    recipient_count: Mapped[int] = mapped_column(Integer, nullable=False)
    eligible_count: Mapped[int] = mapped_column(Integer, nullable=False)
    confirmed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    __table_args__ = __table_args__ + (
        ForeignKeyConstraint(
            ["workspace_id", "cohort_id"],
            ["crm_cohorts.workspace_id", "crm_cohorts.id"],
            ondelete="CASCADE",
            name="fk_crm_campaigns_cohort",
        ),
        ForeignKeyConstraint(
            ["workspace_id", "channel_connection_id"],
            ["channel_connections.workspace_id", "channel_connections.id"],
            ondelete="RESTRICT",
            name="fk_crm_campaigns_connection",
        ),
    )


class CRMCampaignRecipient(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "crm_campaign_recipients"
    __table_args__ = (
        ForeignKeyConstraint(
            ["workspace_id", "campaign_id"],
            ["crm_campaigns.workspace_id", "crm_campaigns.id"],
            ondelete="CASCADE",
            name="fk_crm_campaign_recipients_campaign",
        ),
        ForeignKeyConstraint(
            ["workspace_id", "patient_id"],
            ["patients.workspace_id", "patients.id"],
            ondelete="CASCADE",
            name="fk_crm_campaign_recipients_patient",
        ),
        UniqueConstraint("campaign_id", "patient_id", name="uq_crm_campaign_recipients_patient"),
        UniqueConstraint("workspace_id", "id", name="uq_crm_campaign_recipients_workspace_id_id"),
        CheckConstraint("rank >= 1 AND rank <= 25", name="crm_campaign_recipient_rank_valid"),
        CheckConstraint(
            "status IN ('eligible','skipped_no_consent','skipped_inactive','skipped_no_route','cancelled_no_consent','cancelled_inactive','cancelled_no_route','queued','processing','sent','delivered','read','failed','cancelled')",
            name="crm_campaign_recipient_status_valid",
        ),
        Index("ix_crm_campaign_recipients_campaign_rank", "campaign_id", "rank"),
        Index("ix_crm_campaign_recipients_dispatch", "dispatch_id"),
    )

    workspace_id: Mapped[UUID] = mapped_column(index=True, nullable=False)
    campaign_id: Mapped[UUID] = mapped_column(index=True, nullable=False)
    patient_id: Mapped[UUID] = mapped_column(index=True, nullable=False)
    rank: Mapped[int] = mapped_column(Integer, nullable=False)
    status: Mapped[str] = mapped_column(String(32), nullable=False)
    reason: Mapped[str | None] = mapped_column(String(120), nullable=True)
    conversation_id: Mapped[UUID | None] = mapped_column(index=True, nullable=True)
    channel_identity_id: Mapped[UUID | None] = mapped_column(index=True, nullable=True)
    message_id: Mapped[UUID | None] = mapped_column(index=True, nullable=True)
    dispatch_id: Mapped[UUID | None] = mapped_column(index=True, nullable=True)
    scheduled_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
