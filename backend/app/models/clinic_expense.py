from __future__ import annotations

from datetime import datetime
from uuid import UUID

from sqlalchemy import CheckConstraint, DateTime, ForeignKey, Index, Integer, String
from sqlalchemy.orm import Mapped, mapped_column

from app.database.base import Base, TimestampMixin, UUIDPrimaryKeyMixin

EXPENSE_CATEGORIES = (
    "rent",
    "payroll",
    "marketing",
    "supplies",
    "utilities",
    "software",
    "other",
)


class ClinicExpense(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    """A simple workspace operating cost, separate from patient payments."""

    __tablename__ = "clinic_expenses"
    __table_args__ = (
        CheckConstraint("amount_minor > 0", name="clinic_expense_amount_positive"),
        CheckConstraint(
            "category IN ('rent','payroll','marketing','supplies','utilities','software','other')",
            name="clinic_expense_category_valid",
        ),
        Index("ix_clinic_expenses_workspace_incurred", "workspace_id", "incurred_at"),
    )

    workspace_id: Mapped[UUID] = mapped_column(
        ForeignKey("workspaces.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    incurred_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    category: Mapped[str] = mapped_column(String(32), nullable=False)
    description: Mapped[str | None] = mapped_column(String(240), nullable=True)
    amount_minor: Mapped[int] = mapped_column(Integer, nullable=False)
    currency: Mapped[str] = mapped_column(
        String(3),
        nullable=False,
        default="EGP",
        server_default="EGP",
    )
