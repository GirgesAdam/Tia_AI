from __future__ import annotations

from uuid import UUID

from sqlalchemy import Boolean, ForeignKeyConstraint, UniqueConstraint, text
from sqlalchemy.orm import Mapped, mapped_column

from app.database.base import Base, TimestampMixin, UUIDPrimaryKeyMixin


class DoctorBranch(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "doctor_branches"
    __table_args__ = (
        UniqueConstraint(
            "workspace_id", "doctor_id", "branch_id", name="uq_doctor_branches_assignment"
        ),
        ForeignKeyConstraint(
            ["workspace_id", "doctor_id"],
            ["doctors.workspace_id", "doctors.id"],
            ondelete="CASCADE",
            name="fk_doctor_branches_doctor",
        ),
        ForeignKeyConstraint(
            ["workspace_id", "branch_id"],
            ["branches.workspace_id", "branches.id"],
            ondelete="CASCADE",
            name="fk_doctor_branches_branch",
        ),
    )

    workspace_id: Mapped[UUID] = mapped_column(index=True, nullable=False)
    doctor_id: Mapped[UUID] = mapped_column(index=True, nullable=False)
    branch_id: Mapped[UUID] = mapped_column(index=True, nullable=False)
    is_primary: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=False, server_default=text("false")
    )
    is_active: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=True, server_default=text("true")
    )
