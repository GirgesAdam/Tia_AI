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
EXPENSE_SOURCES = ("manual", "import", "integration")
EXPENSE_STATUSES = ("active", "voided")


class ClinicExpense(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    """Workspace operating cost kept separate from patient payment facts."""

    __tablename__ = "clinic_expenses"
    __table_args__ = (
        CheckConstraint("amount_minor > 0", name="clinic_expense_amount_positive"),
        CheckConstraint(
            "category IN ('rent','payroll','marketing','supplies','utilities','software','other')",
            name="clinic_expense_category_valid",
        ),
        CheckConstraint(
            "source IN ('manual','import','integration')",
            name="clinic_expense_source_valid",
        ),
        CheckConstraint(
            "status IN ('active','voided')",
            name="clinic_expense_status_valid",
        ),
        CheckConstraint(
            "(status = 'active' AND voided_at IS NULL AND voided_by_user_id IS NULL) OR "
            "(status = 'voided' AND voided_at IS NOT NULL)",
            name="clinic_expense_void_state_valid",
        ),
        Index("ix_clinic_expenses_workspace_incurred", "workspace_id", "incurred_at"),
        Index(
            "ix_clinic_expenses_workspace_status_incurred",
            "workspace_id",
            "status",
            "incurred_at",
        ),
    )

    workspace_id: Mapped[UUID] = mapped_column(
        ForeignKey("workspaces.id", ondelete="CASCADE"), nullable=False, index=True
    )
    incurred_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    category: Mapped[str] = mapped_column(String(32), nullable=False)
    vendor: Mapped[str | None] = mapped_column(String(160), nullable=True)
    description: Mapped[str | None] = mapped_column(String(240), nullable=True)
    amount_minor: Mapped[int] = mapped_column(Integer, nullable=False)
    currency: Mapped[str] = mapped_column(
        String(3), nullable=False, default="EGP", server_default="EGP"
    )
    source: Mapped[str] = mapped_column(
        String(32), nullable=False, default="manual", server_default="manual"
    )
    status: Mapped[str] = mapped_column(
        String(16), nullable=False, default="active", server_default="active"
    )
    created_by_user_id: Mapped[UUID | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"), nullable=True, index=True
    )
    voided_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    voided_by_user_id: Mapped[UUID | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"), nullable=True, index=True
    )
