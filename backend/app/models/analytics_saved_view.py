from __future__ import annotations

from uuid import UUID

from sqlalchemy import JSON, CheckConstraint, ForeignKey, Index, String, UniqueConstraint
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.database.base import Base, TimestampMixin, UUIDPrimaryKeyMixin

_ANALYTICS_JSON = JSON().with_variant(JSONB, "postgresql")


class AnalyticsSavedView(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "analytics_saved_views"
    __table_args__ = (
        UniqueConstraint("workspace_id", "id", name="uq_analytics_saved_views_workspace_id_id"),
        UniqueConstraint("workspace_id", "created_by_user_id", "name_key", name="uq_analytics_saved_views_workspace_user_name_key"),
        CheckConstraint(
            "display_mode IN ('visual','table','both')",
            name="analytics_saved_view_display_mode_valid",
        ),
        CheckConstraint(
            "chart IS NULL OR chart IN ('kpi','line','bar','heatmap','funnel','table')",
            name="analytics_saved_view_chart_valid",
        ),
        Index("ix_analytics_saved_views_workspace_user_updated", "workspace_id", "created_by_user_id", "updated_at"),
        Index("ix_analytics_saved_views_workspace_analysis", "workspace_id", "analysis_key"),
    )

    workspace_id: Mapped[UUID] = mapped_column(
        ForeignKey("workspaces.id", ondelete="CASCADE"), index=True, nullable=False
    )
    created_by_user_id: Mapped[UUID] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )
    name: Mapped[str] = mapped_column(String(160), nullable=False)
    name_key: Mapped[str] = mapped_column(String(180), nullable=False)
    analysis_key: Mapped[str] = mapped_column(String(120), nullable=False)
    request_json: Mapped[dict] = mapped_column(
        "request", _ANALYTICS_JSON, nullable=False, default=dict, server_default="{}"
    )
    chart: Mapped[str | None] = mapped_column(String(16), nullable=True)
    display_mode: Mapped[str] = mapped_column(
        String(16), nullable=False, default="visual", server_default="visual"
    )
