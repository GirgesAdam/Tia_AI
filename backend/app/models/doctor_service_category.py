from __future__ import annotations

from uuid import UUID

from sqlalchemy import CheckConstraint, ForeignKeyConstraint, String
from sqlalchemy.orm import Mapped, mapped_column

from app.database.base import Base, TimestampMixin


class DoctorServiceCategory(TimestampMixin, Base):
    __tablename__ = "doctor_service_categories"
    __table_args__ = (
        ForeignKeyConstraint(
            ["workspace_id", "doctor_id"],
            ["doctors.workspace_id", "doctors.id"],
            ondelete="CASCADE",
            name="fk_doctor_service_categories_doctor",
        ),
        CheckConstraint(
            "category IN ('laser', 'dermatology', 'slimming')",
            name="doctor_service_category_valid",
        ),
    )

    workspace_id: Mapped[UUID] = mapped_column(primary_key=True)
    doctor_id: Mapped[UUID] = mapped_column(primary_key=True)
    category: Mapped[str] = mapped_column(String(20), primary_key=True)
