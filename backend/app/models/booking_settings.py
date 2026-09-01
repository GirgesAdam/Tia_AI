from __future__ import annotations

from uuid import UUID

from sqlalchemy import Boolean, CheckConstraint, ForeignKey, Integer, String, text
from sqlalchemy.orm import Mapped, mapped_column

from app.database.base import Base, TimestampMixin, UUIDPrimaryKeyMixin


class BookingSettings(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "booking_settings"
    __table_args__ = (
        CheckConstraint(
            "slot_interval_minutes > 0 AND slot_interval_minutes <= 240",
            name="booking_slot_interval_valid",
        ),
        CheckConstraint("minimum_notice_minutes >= 0", name="booking_minimum_notice_non_negative"),
        CheckConstraint(
            "booking_horizon_days > 0 AND booking_horizon_days <= 730", name="booking_horizon_valid"
        ),
        CheckConstraint(
            "cancellation_notice_minutes >= 0", name="booking_cancellation_notice_non_negative"
        ),
    )

    workspace_id: Mapped[UUID] = mapped_column(
        ForeignKey("workspaces.id", ondelete="CASCADE"), unique=True, index=True, nullable=False
    )
    slot_interval_minutes: Mapped[int] = mapped_column(
        Integer, nullable=False, default=15, server_default="15"
    )
    minimum_notice_minutes: Mapped[int] = mapped_column(
        Integer, nullable=False, default=60, server_default="60"
    )
    booking_horizon_days: Mapped[int] = mapped_column(
        Integer, nullable=False, default=90, server_default="90"
    )
    cancellation_notice_minutes: Mapped[int] = mapped_column(
        Integer, nullable=False, default=720, server_default="720"
    )
    allow_same_day_booking: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=True, server_default=text("true")
    )
    require_confirmation: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=True, server_default=text("true")
    )
    default_currency: Mapped[str] = mapped_column(
        String(3), nullable=False, default="EGP", server_default="EGP"
    )
