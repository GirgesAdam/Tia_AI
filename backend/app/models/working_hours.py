from __future__ import annotations

from datetime import time
from uuid import UUID

from sqlalchemy import CheckConstraint, ForeignKeyConstraint, Integer, Time, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.database.base import Base, TimestampMixin, UUIDPrimaryKeyMixin


class BranchWorkingHour(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "branch_working_hours"
    __table_args__ = (
        ForeignKeyConstraint(
            ["workspace_id", "branch_id"],
            ["branches.workspace_id", "branches.id"],
            ondelete="CASCADE",
            name="fk_branch_working_hours_branch",
        ),
        UniqueConstraint(
            "workspace_id", "branch_id", "weekday", "start_time", "end_time",
            name="uq_branch_working_hours_interval",
        ),
        CheckConstraint("weekday >= 0 AND weekday <= 6", name="branch_working_hours_weekday_valid"),
        CheckConstraint("end_time > start_time", name="branch_working_hours_interval_valid"),
    )

    workspace_id: Mapped[UUID] = mapped_column(index=True, nullable=False)
    branch_id: Mapped[UUID] = mapped_column(index=True, nullable=False)
    weekday: Mapped[int] = mapped_column(Integer, nullable=False)
    start_time: Mapped[time] = mapped_column(Time(), nullable=False)
    end_time: Mapped[time] = mapped_column(Time(), nullable=False)


class DoctorWorkingHour(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "doctor_working_hours"
    __table_args__ = (
        ForeignKeyConstraint(
            ["workspace_id", "doctor_id", "branch_id"],
            ["doctor_branches.workspace_id", "doctor_branches.doctor_id", "doctor_branches.branch_id"],
            ondelete="CASCADE",
            name="fk_doctor_working_hours_assignment",
        ),
        UniqueConstraint(
            "workspace_id", "doctor_id", "branch_id", "weekday", "start_time", "end_time",
            name="uq_doctor_working_hours_interval",
        ),
        CheckConstraint("weekday >= 0 AND weekday <= 6", name="doctor_working_hours_weekday_valid"),
        CheckConstraint("end_time > start_time", name="doctor_working_hours_interval_valid"),
    )

    workspace_id: Mapped[UUID] = mapped_column(index=True, nullable=False)
    doctor_id: Mapped[UUID] = mapped_column(index=True, nullable=False)
    branch_id: Mapped[UUID] = mapped_column(index=True, nullable=False)
    weekday: Mapped[int] = mapped_column(Integer, nullable=False)
    start_time: Mapped[time] = mapped_column(Time(), nullable=False)
    end_time: Mapped[time] = mapped_column(Time(), nullable=False)
