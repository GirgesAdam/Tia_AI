from __future__ import annotations

from uuid import UUID

from sqlalchemy import Boolean, CheckConstraint, ForeignKey, Index, Integer, String, UniqueConstraint
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.database.base import Base, TimestampMixin, UUIDPrimaryKeyMixin

AUTOMATION_TRIGGER_KINDS = (
    "appointment_created",
    "before_appointment",
    "after_completed",
    "after_no_show",
)
AUTOMATION_CHANNELS = ("auto", "whatsapp", "email", "sms")


class AutomationRule(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "automation_rules"
    __table_args__ = (
        UniqueConstraint("workspace_id", "key", name="uq_automation_rules_workspace_key"),
        CheckConstraint(
            "trigger_kind IN ('appointment_created', 'before_appointment', 'after_completed', 'after_no_show')",
            name="automation_rule_trigger_kind_valid",
        ),
        CheckConstraint(
            "channel IN ('auto', 'whatsapp', 'email', 'sms')",
            name="automation_rule_channel_valid",
        ),
        Index("ix_automation_rules_workspace_enabled", "workspace_id", "enabled"),
    )

    workspace_id: Mapped[UUID] = mapped_column(
        ForeignKey("workspaces.id", ondelete="CASCADE"),
        index=True,
        nullable=False,
    )
    key: Mapped[str] = mapped_column(String(80), nullable=False)
    name: Mapped[str] = mapped_column(String(160), nullable=False)
    enabled: Mapped[bool] = mapped_column(
        Boolean,
        nullable=False,
        default=False,
        server_default="false",
    )
    trigger_kind: Mapped[str] = mapped_column(String(40), nullable=False)
    offset_minutes: Mapped[int] = mapped_column(Integer, nullable=False, default=0, server_default="0")
    channel: Mapped[str] = mapped_column(String(20), nullable=False, default="whatsapp", server_default="whatsapp")
    template_name: Mapped[str] = mapped_column(String(160), nullable=False)
    template_language: Mapped[str] = mapped_column(String(20), nullable=False, default="ar", server_default="ar")
    max_lateness_minutes: Mapped[int] = mapped_column(Integer, nullable=False, default=30, server_default="30")
    config_json: Mapped[dict] = mapped_column(
        "config",
        JSONB,
        nullable=False,
        default=dict,
        server_default="{}",
    )
