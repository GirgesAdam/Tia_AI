from __future__ import annotations

from datetime import datetime
from uuid import UUID

from sqlalchemy import (
    CheckConstraint,
    DateTime,
    ForeignKey,
    ForeignKeyConstraint,
    Integer,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.database.base import Base, TimestampMixin, UUIDPrimaryKeyMixin

LEAD_STATUSES = ("new", "contacted", "qualified", "booked", "won", "lost", "spam")


class Lead(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "leads"
    __table_args__ = (
        UniqueConstraint("workspace_id", "id", name="uq_leads_workspace_id_id"),
        CheckConstraint(
            "source IN ('whatsapp', 'instagram', 'facebook', 'website', 'referral', "
            "'walk_in', 'campaign', 'phone', 'email', 'other')",
            name="lead_source_valid",
        ),
        CheckConstraint(
            "status IN ('new', 'contacted', 'qualified', 'booked', 'won', 'lost', 'spam')",
            name="lead_status_valid",
        ),
        CheckConstraint(
            "estimated_value_minor IS NULL OR estimated_value_minor >= 0",
            name="lead_estimated_value_non_negative",
        ),
        ForeignKeyConstraint(
            ["workspace_id", "patient_id"],
            ["patients.workspace_id", "patients.id"],
            ondelete="CASCADE",
            name="fk_leads_patient",
        ),
        ForeignKeyConstraint(
            ["workspace_id", "service_id"],
            ["services.workspace_id", "services.id"],
            name="fk_leads_service",
        ),
    )

    workspace_id: Mapped[UUID] = mapped_column(index=True, nullable=False)
    patient_id: Mapped[UUID] = mapped_column(index=True, nullable=False)
    service_id: Mapped[UUID | None] = mapped_column(index=True, nullable=True)
    assigned_user_id: Mapped[UUID | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"),
        index=True,
        nullable=True,
    )
    source: Mapped[str] = mapped_column(String(32), nullable=False)
    status: Mapped[str] = mapped_column(
        String(20),
        nullable=False,
        default="new",
        server_default="new",
    )
    estimated_value_minor: Mapped[int | None] = mapped_column(Integer, nullable=True)
    currency: Mapped[str] = mapped_column(
        String(3),
        nullable=False,
        default="EGP",
        server_default="EGP",
    )
    lost_reason: Mapped[str | None] = mapped_column(Text, nullable=True)
    next_follow_up_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        index=True,
        nullable=True,
    )
    last_contact_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )
