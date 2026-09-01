"""add deterministic analytics saved views

Revision ID: 0042_analytics_saved_views
Revises: 0041_analytics_query_indexes
Create Date: 2026-08-30
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0042_analytics_saved_views"
down_revision: str | None = "0041_analytics_query_indexes"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "analytics_saved_views",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("workspace_id", sa.Uuid(), nullable=False),
        sa.Column("created_by_user_id", sa.Uuid(), nullable=False),
        sa.Column("name", sa.String(length=160), nullable=False),
        sa.Column("name_key", sa.String(length=180), nullable=False),
        sa.Column("analysis_key", sa.String(length=120), nullable=False),
        sa.Column("request", postgresql.JSONB(astext_type=sa.Text()), server_default="{}", nullable=False),
        sa.Column("chart", sa.String(length=16), nullable=True),
        sa.Column("display_mode", sa.String(length=16), server_default="visual", nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.CheckConstraint(
            "display_mode IN ('visual','table','both')",
            name="analytics_saved_view_display_mode_valid",
        ),
        sa.CheckConstraint(
            "chart IS NULL OR chart IN ('kpi','line','bar','heatmap','funnel','table')",
            name="analytics_saved_view_chart_valid",
        ),
        sa.ForeignKeyConstraint(["workspace_id"], ["workspaces.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["created_by_user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("workspace_id", "id", name="uq_analytics_saved_views_workspace_id_id"),
        sa.UniqueConstraint(
            "workspace_id", "created_by_user_id", "name_key",
            name="uq_analytics_saved_views_workspace_user_name_key",
        ),
    )
    op.create_index("ix_analytics_saved_views_workspace_id", "analytics_saved_views", ["workspace_id"])
    op.create_index(
        "ix_analytics_saved_views_workspace_user_updated",
        "analytics_saved_views",
        ["workspace_id", "created_by_user_id", "updated_at"],
    )
    op.create_index("ix_analytics_saved_views_workspace_analysis", "analytics_saved_views", ["workspace_id", "analysis_key"])

    # Saved analytics configuration is API-owned data. Prevent Supabase Data API
    # clients from bypassing FastAPI workspace/user authorization.
    op.execute(sa.text('ALTER TABLE public."analytics_saved_views" ENABLE ROW LEVEL SECURITY'))
    op.execute(sa.text('REVOKE ALL ON TABLE public."analytics_saved_views" FROM anon, authenticated'))


def downgrade() -> None:
    op.drop_index("ix_analytics_saved_views_workspace_analysis", table_name="analytics_saved_views")
    op.drop_index("ix_analytics_saved_views_workspace_user_updated", table_name="analytics_saved_views")
    op.drop_index("ix_analytics_saved_views_workspace_id", table_name="analytics_saved_views")
    op.drop_table("analytics_saved_views")
