"""Add deferred clinic data issue inbox.

Revision ID: 0050_clinic_data_issues
Revises: 0049_package_refund_pricing
Create Date: 2026-08-31
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0050_clinic_data_issues"
down_revision: str | None = "0049_package_refund_pricing"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.drop_constraint(
        "clinic_integration_entity_link_type_valid",
        "clinic_integration_entity_links",
        type_="check",
    )
    op.create_check_constraint(
        "clinic_integration_entity_link_type_valid",
        "clinic_integration_entity_links",
        "entity_type IN ('service', 'branch', 'doctor', 'patient', 'appointment', 'payment', 'patient_package', 'package_usage')",
    )

    op.create_table(
        "clinic_data_issues",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("workspace_id", sa.Uuid(), nullable=False),
        sa.Column("onboarding_session_id", sa.Uuid(), nullable=True),
        sa.Column("severity", sa.String(length=16), nullable=False),
        sa.Column("status", sa.String(length=20), server_default="open", nullable=False),
        sa.Column("category", sa.String(length=64), nullable=False),
        sa.Column("code", sa.String(length=120), nullable=False),
        sa.Column("title", sa.String(length=300), nullable=False),
        sa.Column("description", sa.String(length=1200), nullable=False),
        sa.Column("entity_type", sa.String(length=48), nullable=True),
        sa.Column("entity_external_id", sa.String(length=512), nullable=True),
        sa.Column("related_external_id", sa.String(length=512), nullable=True),
        sa.Column("occurrence_count", sa.Integer(), server_default="1", nullable=False),
        sa.Column("source_context", postgresql.JSONB(astext_type=sa.Text()), server_default="{}", nullable=False),
        sa.Column("resolution", postgresql.JSONB(astext_type=sa.Text()), server_default="{}", nullable=False),
        sa.Column("resolved_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.CheckConstraint("severity IN ('critical', 'normal', 'simple')", name="clinic_data_issue_severity_valid"),
        sa.CheckConstraint("status IN ('open', 'resolved', 'ignored', 'auto_resolved')", name="clinic_data_issue_status_valid"),
        sa.ForeignKeyConstraint(["workspace_id"], ["workspaces.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["onboarding_session_id"], ["clinic_integration_onboarding_sessions.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_clinic_data_issues_workspace_status", "clinic_data_issues", ["workspace_id", "status"])
    op.create_index("ix_clinic_data_issues_workspace_severity", "clinic_data_issues", ["workspace_id", "severity"])
    op.create_index("ix_clinic_data_issues_workspace_category", "clinic_data_issues", ["workspace_id", "category"])


def downgrade() -> None:
    op.drop_index("ix_clinic_data_issues_workspace_category", table_name="clinic_data_issues")
    op.drop_index("ix_clinic_data_issues_workspace_severity", table_name="clinic_data_issues")
    op.drop_index("ix_clinic_data_issues_workspace_status", table_name="clinic_data_issues")
    op.drop_table("clinic_data_issues")
    op.drop_constraint(
        "clinic_integration_entity_link_type_valid",
        "clinic_integration_entity_links",
        type_="check",
    )
    op.create_check_constraint(
        "clinic_integration_entity_link_type_valid",
        "clinic_integration_entity_links",
        "entity_type IN ('service', 'branch', 'doctor', 'patient', 'appointment', 'payment')",
    )
