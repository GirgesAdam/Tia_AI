"""Add durable CRM cohorts materialized from analytics patient lists.

Revision ID: 0038_crm_cohorts
Revises: 0037_patient_history
Create Date: 2026-08-27
"""

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision: str = "0038_crm_cohorts"
down_revision: str | Sequence[str] | None = "0037_patient_history"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "crm_cohorts",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("workspace_id", sa.Uuid(), nullable=False),
        sa.Column("created_by_user_id", sa.Uuid(), nullable=True),
        sa.Column("name", sa.String(length=160), nullable=False),
        sa.Column("request_key", sa.String(length=64), nullable=False),
        sa.Column("source", sa.String(length=24), server_default="analytics_bi", nullable=False),
        sa.Column("status", sa.String(length=16), server_default="active", nullable=False),
        sa.Column("analytics_operation", sa.String(length=48), nullable=False),
        sa.Column("question", sa.Text(), nullable=False),
        sa.Column("plan", postgresql.JSONB(astext_type=sa.Text()), server_default="{}", nullable=False),
        sa.Column("period_label", sa.String(length=120), nullable=False),
        sa.Column("member_count", sa.Integer(), server_default="0", nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.CheckConstraint("source IN ('analytics_bi')", name="crm_cohort_source_valid"),
        sa.CheckConstraint("status IN ('active', 'archived')", name="crm_cohort_status_valid"),
        sa.CheckConstraint("member_count >= 1 AND member_count <= 25", name="crm_cohort_member_count_valid"),
        sa.ForeignKeyConstraint(["created_by_user_id"], ["users.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["workspace_id"], ["workspaces.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("workspace_id", "id", name="uq_crm_cohorts_workspace_id_id"),
        sa.UniqueConstraint("workspace_id", "request_key", name="uq_crm_cohorts_workspace_request_key"),
    )
    op.create_index("ix_crm_cohorts_workspace_id", "crm_cohorts", ["workspace_id"], unique=False)
    op.create_index("ix_crm_cohorts_workspace_created", "crm_cohorts", ["workspace_id", "created_at"], unique=False)

    op.create_table(
        "crm_cohort_members",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("workspace_id", sa.Uuid(), nullable=False),
        sa.Column("cohort_id", sa.Uuid(), nullable=False),
        sa.Column("patient_id", sa.Uuid(), nullable=False),
        sa.Column("rank", sa.Integer(), nullable=False),
        sa.Column("snapshot_metrics", postgresql.JSONB(astext_type=sa.Text()), server_default="[]", nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.CheckConstraint("rank >= 1 AND rank <= 25", name="crm_cohort_member_rank_valid"),
        sa.ForeignKeyConstraint(
            ["workspace_id", "cohort_id"],
            ["crm_cohorts.workspace_id", "crm_cohorts.id"],
            name="fk_crm_cohort_members_cohort",
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["workspace_id", "patient_id"],
            ["patients.workspace_id", "patients.id"],
            name="fk_crm_cohort_members_patient",
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("cohort_id", "patient_id", name="uq_crm_cohort_members_cohort_patient"),
    )
    op.create_index("ix_crm_cohort_members_workspace_id", "crm_cohort_members", ["workspace_id"], unique=False)
    op.create_index("ix_crm_cohort_members_cohort_id", "crm_cohort_members", ["cohort_id"], unique=False)
    op.create_index("ix_crm_cohort_members_patient_id", "crm_cohort_members", ["patient_id"], unique=False)
    op.create_index("ix_crm_cohort_members_workspace_patient", "crm_cohort_members", ["workspace_id", "patient_id"], unique=False)
    op.create_index("ix_crm_cohort_members_cohort_rank", "crm_cohort_members", ["cohort_id", "rank"], unique=False)


def downgrade() -> None:
    op.drop_index("ix_crm_cohort_members_cohort_rank", table_name="crm_cohort_members")
    op.drop_index("ix_crm_cohort_members_workspace_patient", table_name="crm_cohort_members")
    op.drop_index("ix_crm_cohort_members_patient_id", table_name="crm_cohort_members")
    op.drop_index("ix_crm_cohort_members_cohort_id", table_name="crm_cohort_members")
    op.drop_index("ix_crm_cohort_members_workspace_id", table_name="crm_cohort_members")
    op.drop_table("crm_cohort_members")
    op.drop_index("ix_crm_cohorts_workspace_created", table_name="crm_cohorts")
    op.drop_index("ix_crm_cohorts_workspace_id", table_name="crm_cohorts")
    op.drop_table("crm_cohorts")
