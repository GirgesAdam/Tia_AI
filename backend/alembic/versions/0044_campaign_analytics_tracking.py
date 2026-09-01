"""add explicit CRM campaign booking attribution tracking

Revision ID: 0044_campaign_analytics_tracking
Revises: 0043_analytics_scale_guards
Create Date: 2026-08-30
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0044_campaign_analytics_tracking"
down_revision: str | None = "0043_analytics_scale_guards"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # Composite workspace-safe FK target for the conversion table below.
    op.create_unique_constraint(
        "uq_crm_campaign_recipients_workspace_id_id",
        "crm_campaign_recipients",
        ["workspace_id", "id"],
    )

    op.create_table(
        "crm_campaign_conversions",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("workspace_id", sa.Uuid(), nullable=False),
        sa.Column("campaign_id", sa.Uuid(), nullable=False),
        sa.Column("recipient_id", sa.Uuid(), nullable=False),
        sa.Column("patient_id", sa.Uuid(), nullable=False),
        sa.Column("conversation_id", sa.Uuid(), nullable=False),
        sa.Column("original_appointment_id", sa.Uuid(), nullable=False),
        sa.Column("appointment_id", sa.Uuid(), nullable=False),
        sa.Column("response_message_id", sa.Uuid(), nullable=False),
        sa.Column("attribution_kind", sa.String(length=48), nullable=False),
        sa.Column("campaign_sent_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("patient_replied_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("booked_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.CheckConstraint(
            "attribution_kind IN ('direct_same_conversation_response')",
            name="crm_campaign_conversion_attribution_kind_valid",
        ),
        sa.ForeignKeyConstraint(["workspace_id"], ["workspaces.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(
            ["workspace_id", "campaign_id"],
            ["crm_campaigns.workspace_id", "crm_campaigns.id"],
            name="fk_crm_campaign_conversions_campaign",
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["workspace_id", "recipient_id"],
            ["crm_campaign_recipients.workspace_id", "crm_campaign_recipients.id"],
            name="fk_crm_campaign_conversions_recipient",
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["workspace_id", "patient_id"],
            ["patients.workspace_id", "patients.id"],
            name="fk_crm_campaign_conversions_patient",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["workspace_id", "conversation_id"],
            ["conversations.workspace_id", "conversations.id"],
            name="fk_crm_campaign_conversions_conversation",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["workspace_id", "original_appointment_id"],
            ["appointments.workspace_id", "appointments.id"],
            name="fk_crm_campaign_conversions_original_appointment",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["workspace_id", "appointment_id"],
            ["appointments.workspace_id", "appointments.id"],
            name="fk_crm_campaign_conversions_current_appointment",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(["response_message_id"], ["messages.id"], ondelete="RESTRICT"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("workspace_id", "id", name="uq_crm_campaign_conversions_workspace_id_id"),
        sa.UniqueConstraint(
            "workspace_id",
            "appointment_id",
            name="uq_crm_campaign_conversions_workspace_appointment",
        ),
    )
    for column in (
        "workspace_id",
        "campaign_id",
        "recipient_id",
        "patient_id",
        "conversation_id",
        "original_appointment_id",
        "appointment_id",
        "response_message_id",
    ):
        op.create_index(f"ix_crm_campaign_conversions_{column}", "crm_campaign_conversions", [column])
    op.create_index(
        "ix_crm_campaign_conversions_campaign_booked",
        "crm_campaign_conversions",
        ["workspace_id", "campaign_id", "booked_at"],
    )
    op.create_index(
        "ix_crm_campaign_conversions_recipient",
        "crm_campaign_conversions",
        ["workspace_id", "recipient_id"],
    )

    # API-owned attribution facts: clients must go through FastAPI workspace auth.
    op.execute(sa.text('ALTER TABLE public."crm_campaign_conversions" ENABLE ROW LEVEL SECURITY'))
    op.execute(sa.text('REVOKE ALL ON TABLE public."crm_campaign_conversions" FROM anon, authenticated'))


def downgrade() -> None:
    op.drop_index("ix_crm_campaign_conversions_recipient", table_name="crm_campaign_conversions")
    op.drop_index("ix_crm_campaign_conversions_campaign_booked", table_name="crm_campaign_conversions")
    for column in reversed(
        (
            "workspace_id",
            "campaign_id",
            "recipient_id",
            "patient_id",
            "conversation_id",
            "original_appointment_id",
            "appointment_id",
            "response_message_id",
        )
    ):
        op.drop_index(f"ix_crm_campaign_conversions_{column}", table_name="crm_campaign_conversions")
    op.drop_table("crm_campaign_conversions")
    op.drop_constraint(
        "uq_crm_campaign_recipients_workspace_id_id",
        "crm_campaign_recipients",
        type_="unique",
    )
