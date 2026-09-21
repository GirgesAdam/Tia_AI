from __future__ import annotations

from uuid import UUID

from sqlalchemy import CheckConstraint, ForeignKey, ForeignKeyConstraint, Index, Integer, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.database.base import Base, TimestampMixin, UUIDPrimaryKeyMixin


class AppointmentAdditionalService(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    """Billing-only service added during a visit without extending its reserved time."""

    __tablename__ = "appointment_additional_services"
    __table_args__ = (
        UniqueConstraint("workspace_id", "id", name="uq_appointment_additional_services_workspace_id_id"),
        UniqueConstraint(
            "workspace_id",
            "appointment_id",
            "service_id",
            name="uq_appointment_additional_services_appointment_service",
        ),
        CheckConstraint("unit_price_minor >= 0", name="appointment_additional_service_price_non_negative"),
        CheckConstraint(
            "laser_device_key IS NULL OR laser_device_key IN ('prime_lase', 'candela_gentle')",
            name="appointment_additional_service_device_valid",
        ),
        ForeignKeyConstraint(
            ["workspace_id", "appointment_id"],
            ["appointments.workspace_id", "appointments.id"],
            ondelete="CASCADE",
            name="fk_appointment_additional_services_appointment",
        ),
        ForeignKeyConstraint(
            ["workspace_id", "service_id"],
            ["services.workspace_id", "services.id"],
            ondelete="RESTRICT",
            name="fk_appointment_additional_services_service",
        ),
        Index(
            "ix_appointment_additional_services_workspace_appointment",
            "workspace_id",
            "appointment_id",
        ),
    )

    workspace_id: Mapped[UUID] = mapped_column(index=True, nullable=False)
    appointment_id: Mapped[UUID] = mapped_column(index=True, nullable=False)
    service_id: Mapped[UUID] = mapped_column(index=True, nullable=False)
    service_name: Mapped[str] = mapped_column(String(200), nullable=False)
    unit_price_minor: Mapped[int] = mapped_column(Integer, nullable=False)
    currency: Mapped[str] = mapped_column(
        String(3), nullable=False, default="EGP", server_default="EGP"
    )
    laser_device_key: Mapped[str | None] = mapped_column(String(40), nullable=True)
    laser_device_name: Mapped[str | None] = mapped_column(String(120), nullable=True)
    created_by_user_id: Mapped[UUID | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
