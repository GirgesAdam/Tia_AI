"""Add confirmed WhatsApp cohort campaigns with per-recipient delivery tracking.

Revision ID: 0039_crm_campaigns
Revises: 0038_crm_cohorts
Create Date: 2026-08-27
"""

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision: str = "0039_crm_campaigns"
down_revision: str | Sequence[str] | None = "0038_crm_cohorts"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "crm_campaigns",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("workspace_id", sa.Uuid(), nullable=False),
        sa.Column("cohort_id", sa.Uuid(), nullable=False),
        sa.Column("channel_connection_id", sa.Uuid(), nullable=False),
        sa.Column("created_by_user_id", sa.Uuid(), nullable=True),
        sa.Column("confirmed_by_user_id", sa.Uuid(), nullable=True),
        sa.Column("request_key", sa.String(length=64), nullable=False),
        sa.Column("confirmation_key", sa.String(length=64), nullable=True),
        sa.Column("name", sa.String(length=160), nullable=False),
        sa.Column("status", sa.String(length=16), server_default="draft", nullable=False),
        sa.Column("template_name", sa.String(length=160), nullable=False),
        sa.Column("template_language", sa.String(length=32), server_default="ar", nullable=False),
        sa.Column("body_parameter_keys", postgresql.JSONB(astext_type=sa.Text()), server_default="[]", nullable=False),
        sa.Column("rate_limit_per_minute", sa.Integer(), server_default="10", nullable=False),
        sa.Column("recipient_count", sa.Integer(), nullable=False),
        sa.Column("eligible_count", sa.Integer(), nullable=False),
        sa.Column("confirmed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.CheckConstraint("status IN ('draft','confirmed','cancelled')", name="crm_campaign_status_valid"),
        sa.CheckConstraint("recipient_count >= 1 AND recipient_count <= 25", name="crm_campaign_recipient_count_valid"),
        sa.CheckConstraint("eligible_count >= 0 AND eligible_count <= recipient_count", name="crm_campaign_eligible_count_valid"),
        sa.CheckConstraint("rate_limit_per_minute >= 1 AND rate_limit_per_minute <= 60", name="crm_campaign_rate_limit_valid"),
        sa.ForeignKeyConstraint(["workspace_id"], ["workspaces.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["created_by_user_id"], ["users.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["confirmed_by_user_id"], ["users.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(
            ["workspace_id", "cohort_id"], ["crm_cohorts.workspace_id", "crm_cohorts.id"],
            name="fk_crm_campaigns_cohort", ondelete="CASCADE"
        ),
        sa.ForeignKeyConstraint(
            ["workspace_id", "channel_connection_id"], ["channel_connections.workspace_id", "channel_connections.id"],
            name="fk_crm_campaigns_connection", ondelete="RESTRICT"
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("workspace_id", "id", name="uq_crm_campaigns_workspace_id_id"),
        sa.UniqueConstraint("workspace_id", "request_key", name="uq_crm_campaigns_workspace_request_key"),
    )
    op.create_index("ix_crm_campaigns_workspace_id", "crm_campaigns", ["workspace_id"], unique=False)
    op.create_index("ix_crm_campaigns_cohort_id", "crm_campaigns", ["cohort_id"], unique=False)
    op.create_index("ix_crm_campaigns_channel_connection_id", "crm_campaigns", ["channel_connection_id"], unique=False)
    op.create_index("ix_crm_campaigns_workspace_created", "crm_campaigns", ["workspace_id", "created_at"], unique=False)

    op.create_table(
        "crm_campaign_recipients",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("workspace_id", sa.Uuid(), nullable=False),
        sa.Column("campaign_id", sa.Uuid(), nullable=False),
        sa.Column("patient_id", sa.Uuid(), nullable=False),
        sa.Column("rank", sa.Integer(), nullable=False),
        sa.Column("status", sa.String(length=32), nullable=False),
        sa.Column("reason", sa.String(length=120), nullable=True),
        sa.Column("conversation_id", sa.Uuid(), nullable=True),
        sa.Column("channel_identity_id", sa.Uuid(), nullable=True),
        sa.Column("message_id", sa.Uuid(), nullable=True),
        sa.Column("dispatch_id", sa.Uuid(), nullable=True),
        sa.Column("scheduled_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.CheckConstraint("rank >= 1 AND rank <= 25", name="crm_campaign_recipient_rank_valid"),
        sa.CheckConstraint(
            "status IN ('eligible','skipped_no_consent','skipped_inactive','skipped_no_route','cancelled_no_consent','cancelled_inactive','cancelled_no_route','queued','processing','sent','delivered','read','failed','cancelled')",
            name="crm_campaign_recipient_status_valid",
        ),
        sa.ForeignKeyConstraint(
            ["workspace_id", "campaign_id"], ["crm_campaigns.workspace_id", "crm_campaigns.id"],
            name="fk_crm_campaign_recipients_campaign", ondelete="CASCADE"
        ),
        sa.ForeignKeyConstraint(
            ["workspace_id", "patient_id"], ["patients.workspace_id", "patients.id"],
            name="fk_crm_campaign_recipients_patient", ondelete="CASCADE"
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("campaign_id", "patient_id", name="uq_crm_campaign_recipients_patient"),
    )
    for column in ("workspace_id", "campaign_id", "patient_id", "conversation_id", "channel_identity_id", "message_id", "dispatch_id"):
        op.create_index(f"ix_crm_campaign_recipients_{column}", "crm_campaign_recipients", [column], unique=False)
    op.create_index("ix_crm_campaign_recipients_campaign_rank", "crm_campaign_recipients", ["campaign_id", "rank"], unique=False)


def downgrade() -> None:
    op.drop_index("ix_crm_campaign_recipients_campaign_rank", table_name="crm_campaign_recipients")
    for column in reversed(("workspace_id", "campaign_id", "patient_id", "conversation_id", "channel_identity_id", "message_id", "dispatch_id")):
        op.drop_index(f"ix_crm_campaign_recipients_{column}", table_name="crm_campaign_recipients")
    op.drop_table("crm_campaign_recipients")
    op.drop_index("ix_crm_campaigns_workspace_created", table_name="crm_campaigns")
    op.drop_index("ix_crm_campaigns_channel_connection_id", table_name="crm_campaigns")
    op.drop_index("ix_crm_campaigns_cohort_id", table_name="crm_campaigns")
    op.drop_index("ix_crm_campaigns_workspace_id", table_name="crm_campaigns")
    op.drop_table("crm_campaigns")
