from __future__ import annotations

from uuid import UUID

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    ForeignKeyConstraint,
    Integer,
    UniqueConstraint,
    text,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.database.base import Base, TimestampMixin, UUIDPrimaryKeyMixin


class DoctorService(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "doctor_services"
    __table_args__ = (
        UniqueConstraint(
            "workspace_id", "doctor_id", "service_id", name="uq_doctor_services_assignment"
        ),
        ForeignKeyConstraint(
            ["workspace_id", "doctor_id"],
            ["doctors.workspace_id", "doctors.id"],
            ondelete="CASCADE",
            name="fk_doctor_services_doctor",
        ),
        ForeignKeyConstraint(
            ["workspace_id", "service_id"],
            ["services.workspace_id", "services.id"],
            ondelete="CASCADE",
            name="fk_doctor_services_service",
        ),
        CheckConstraint(
            "custom_duration_minutes IS NULL OR custom_duration_minutes > 0",
            name="doctor_service_duration_valid",
        ),
        CheckConstraint(
            "custom_price_minor IS NULL OR custom_price_minor >= 0",
            name="doctor_service_price_non_negative",
        ),
    )

    workspace_id: Mapped[UUID] = mapped_column(index=True, nullable=False)
    doctor_id: Mapped[UUID] = mapped_column(index=True, nullable=False)
    service_id: Mapped[UUID] = mapped_column(index=True, nullable=False)
    custom_duration_minutes: Mapped[int | None] = mapped_column(Integer, nullable=True)
    custom_price_minor: Mapped[int | None] = mapped_column(Integer, nullable=True)
    is_active: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=True, server_default=text("true")
    )
