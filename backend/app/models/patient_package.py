from __future__ import annotations

from datetime import date, datetime
from uuid import UUID

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    Date,
    DateTime,
    ForeignKey,
    ForeignKeyConstraint,
    Index,
    Integer,
    String,
    UniqueConstraint,
    text,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.database.base import Base, TimestampMixin, UUIDPrimaryKeyMixin

PACKAGE_STATUSES = ("active", "expired", "cancelled")
PACKAGE_SOURCES = ("staff", "integration")
PACKAGE_USAGE_STATUSES = ("reserved", "consumed", "released")


class PatientPackage(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    """A patient-owned prepaid entitlement for a specific service.

    The package sale is one commercial fact. Appointment usage is tracked in
    ``package_usages`` and never creates appointment-level revenue.
    """

    __tablename__ = "patient_packages"
    __table_args__ = (
        UniqueConstraint("workspace_id", "id", name="uq_patient_packages_workspace_id_id"),
        CheckConstraint("sessions_purchased > 0", name="patient_package_sessions_positive"),
        CheckConstraint(
            "opening_sessions_remaining IS NULL OR opening_sessions_remaining >= 0",
            name="patient_package_opening_remaining_non_negative",
        ),
        CheckConstraint(
            "opening_sessions_remaining IS NULL OR opening_sessions_remaining <= sessions_purchased",
            name="patient_package_opening_remaining_within_total",
        ),
        CheckConstraint("sale_price_minor >= 0", name="patient_package_price_non_negative"),
        CheckConstraint(
            "standalone_session_price_minor_at_purchase IS NULL OR standalone_session_price_minor_at_purchase >= 0",
            name="patient_package_standalone_price_non_negative",
        ),
        CheckConstraint(
            "status IN ('active', 'expired', 'cancelled')",
            name="patient_package_status_valid",
        ),
        CheckConstraint(
            "source IN ('staff', 'integration')",
            name="patient_package_source_valid",
        ),
        ForeignKeyConstraint(
            ["workspace_id"],
            ["workspaces.id"],
            ondelete="CASCADE",
            name="fk_patient_packages_workspace",
        ),
        ForeignKeyConstraint(
            ["workspace_id", "patient_id"],
            ["patients.workspace_id", "patients.id"],
            ondelete="RESTRICT",
            name="fk_patient_packages_patient",
        ),
        ForeignKeyConstraint(
            ["workspace_id", "service_id"],
            ["services.workspace_id", "services.id"],
            ondelete="RESTRICT",
            name="fk_patient_packages_service",
        ),
        ForeignKeyConstraint(
            ["workspace_id", "purchase_transaction_id"],
            ["payment_transactions.workspace_id", "payment_transactions.id"],
            ondelete="RESTRICT",
            name="fk_patient_packages_purchase_transaction",
        ),
        Index(
            "uq_patient_packages_workspace_external_id",
            "workspace_id",
            "external_id",
            unique=True,
            postgresql_where=text("external_id IS NOT NULL"),
        ),
        Index(
            "uq_patient_packages_workspace_idempotency_key",
            "workspace_id",
            "idempotency_key",
            unique=True,
            postgresql_where=text("idempotency_key IS NOT NULL"),
        ),
        Index(
            "ix_patient_packages_workspace_patient_service",
            "workspace_id",
            "patient_id",
            "service_id",
        ),
    )

    workspace_id: Mapped[UUID] = mapped_column(index=True, nullable=False)
    patient_id: Mapped[UUID] = mapped_column(index=True, nullable=False)
    service_id: Mapped[UUID] = mapped_column(index=True, nullable=False)
    purchase_transaction_id: Mapped[UUID | None] = mapped_column(index=True, nullable=True)
    created_by_user_id: Mapped[UUID | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"), index=True, nullable=True
    )

    external_id: Mapped[str | None] = mapped_column(String(128), nullable=True)
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    sessions_purchased: Mapped[int] = mapped_column(Integer, nullable=False)
    opening_sessions_remaining: Mapped[int | None] = mapped_column(Integer, nullable=True)
    sessions_total_known: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=True, server_default=text("true")
    )
    sale_price_minor: Mapped[int] = mapped_column(Integer, nullable=False, default=0, server_default="0")
    standalone_session_price_minor_at_purchase: Mapped[int | None] = mapped_column(
        Integer, nullable=True
    )
    currency: Mapped[str] = mapped_column(String(3), nullable=False, default="EGP", server_default="EGP")
    purchased_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    expires_at: Mapped[date | None] = mapped_column(Date, nullable=True)
    status: Mapped[str] = mapped_column(String(16), nullable=False, default="active", server_default="active")
    source: Mapped[str] = mapped_column(String(16), nullable=False, default="staff", server_default="staff")
    idempotency_key: Mapped[str | None] = mapped_column(String(128), nullable=True)


class PackageUsage(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    """Reservation/consumption ledger for package sessions.

    ``reserved`` counts against remaining entitlement, ``consumed`` is a
    completed treatment, and ``released`` no longer consumes entitlement.
    One appointment can own at most one usage row.
    """

    __tablename__ = "package_usages"
    __table_args__ = (
        UniqueConstraint("workspace_id", "id", name="uq_package_usages_workspace_id_id"),
        UniqueConstraint(
            "workspace_id",
            "appointment_id",
            name="uq_package_usages_workspace_appointment",
        ),
        CheckConstraint("sessions_used > 0", name="package_usage_sessions_positive"),
        CheckConstraint(
            "status IN ('reserved', 'consumed', 'released')",
            name="package_usage_status_valid",
        ),
        ForeignKeyConstraint(
            ["workspace_id"],
            ["workspaces.id"],
            ondelete="CASCADE",
            name="fk_package_usages_workspace",
        ),
        ForeignKeyConstraint(
            ["workspace_id", "patient_package_id"],
            ["patient_packages.workspace_id", "patient_packages.id"],
            ondelete="CASCADE",
            name="fk_package_usages_package",
        ),
        ForeignKeyConstraint(
            ["workspace_id", "appointment_id"],
            ["appointments.workspace_id", "appointments.id"],
            ondelete="RESTRICT",
            name="fk_package_usages_appointment",
        ),
        Index(
            "uq_package_usages_workspace_external_id",
            "workspace_id",
            "external_id",
            unique=True,
            postgresql_where=text("external_id IS NOT NULL"),
        ),
        Index(
            "ix_package_usages_workspace_package_status",
            "workspace_id",
            "patient_package_id",
            "status",
        ),
    )

    workspace_id: Mapped[UUID] = mapped_column(index=True, nullable=False)
    patient_package_id: Mapped[UUID] = mapped_column(index=True, nullable=False)
    appointment_id: Mapped[UUID] = mapped_column(index=True, nullable=False)
    external_id: Mapped[str | None] = mapped_column(String(128), nullable=True)
    sessions_used: Mapped[int] = mapped_column(Integer, nullable=False, default=1, server_default="1")
    status: Mapped[str] = mapped_column(String(16), nullable=False, default="reserved", server_default="reserved")
    used_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
