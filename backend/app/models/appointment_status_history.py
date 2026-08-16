from __future__ import annotations

from datetime import datetime
from uuid import UUID

from sqlalchemy import CheckConstraint, DateTime, ForeignKey, ForeignKeyConstraint, String, Text, func, text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.database.base import Base, UUIDPrimaryKeyMixin


class AppointmentStatusHistory(UUIDPrimaryKeyMixin, Base):
    __tablename__ = "appointment_status_history"
    __table_args__ = (
        CheckConstraint(
            "from_status IS NULL OR from_status IN ('pending', 'confirmed', 'checked_in', "
            "'in_progress', 'completed', 'cancelled', 'no_show', 'rescheduled')",
            name="appointment_history_from_status_valid",
        ),
        CheckConstraint(
            "to_status IN ('pending', 'confirmed', 'checked_in', 'in_progress', "
            "'completed', 'cancelled', 'no_show', 'rescheduled')",
            name="appointment_history_to_status_valid",
        ),
        ForeignKeyConstraint(
            ["workspace_id", "appointment_id"],
            ["appointments.workspace_id", "appointments.id"],
            ondelete="CASCADE",
            name="fk_appointment_status_history_appointment",
        ),
    )

    workspace_id: Mapped[UUID] = mapped_column(index=True, nullable=False)
    appointment_id: Mapped[UUID] = mapped_column(index=True, nullable=False)
    changed_by_user_id: Mapped[UUID | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"),
        index=True,
        nullable=True,
    )
    from_status: Mapped[str | None] = mapped_column(String(20), nullable=True)
    to_status: Mapped[str] = mapped_column(String(20), nullable=False)
    reason: Mapped[str | None] = mapped_column(Text, nullable=True)
    metadata_json: Mapped[dict] = mapped_column(
        "metadata",
        JSONB,
        nullable=False,
        default=dict,
        server_default=text("'{}'::jsonb"),
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
        index=True,
    )
