from __future__ import annotations

from datetime import datetime
from uuid import UUID

from sqlalchemy import (
    CheckConstraint,
    DateTime,
    ForeignKey,
    ForeignKeyConstraint,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
    func,
    text,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.database.base import Base, UUIDPrimaryKeyMixin

PAYMENT_TRANSACTION_TYPES = ("payment", "refund")
PAYMENT_METHODS = (
    "unknown",
    "cash",
    "card",
    "bank_transfer",
    "wallet",
    "online",
    "other",
)
PAYMENT_SOURCES = ("staff", "legacy_backfill", "integration", "system")


class PaymentTransaction(UUIDPrimaryKeyMixin, Base):
    """Immutable financial fact for one patient.

    Appointment linkage is intentionally optional. ``payment_allocations`` owns
    the deterministic distribution of a transaction across zero, one, or many
    appointments. The nullable appointment columns remain compatibility hints
    for single-appointment facts created by older/current appointment flows.
    """

    __tablename__ = "payment_transactions"
    __table_args__ = (
        UniqueConstraint("workspace_id", "id", name="uq_payment_transactions_workspace_id_id"),
        CheckConstraint(
            "transaction_type IN ('payment', 'refund')",
            name="payment_transaction_type_valid",
        ),
        CheckConstraint("amount_minor > 0", name="payment_transaction_amount_positive"),
        CheckConstraint(
            "payment_method IN ('unknown', 'cash', 'card', 'bank_transfer', 'wallet', 'online', 'other')",
            name="payment_transaction_method_valid",
        ),
        CheckConstraint(
            "source IN ('staff', 'legacy_backfill', 'integration', 'system')",
            name="payment_transaction_source_valid",
        ),
        CheckConstraint(
            "transaction_type = 'refund' OR reference_transaction_id IS NULL",
            name="reference_valid_v2",
        ),
        ForeignKeyConstraint(
            ["workspace_id"],
            ["workspaces.id"],
            ondelete="CASCADE",
            name="fk_payment_transactions_workspace",
        ),
        ForeignKeyConstraint(
            ["workspace_id", "appointment_id"],
            ["appointments.workspace_id", "appointments.id"],
            ondelete="RESTRICT",
            name="fk_payment_transactions_appointment",
        ),
        ForeignKeyConstraint(
            ["workspace_id", "origin_appointment_id"],
            ["appointments.workspace_id", "appointments.id"],
            ondelete="RESTRICT",
            name="fk_payment_transactions_origin_appointment",
        ),
        ForeignKeyConstraint(
            ["workspace_id", "patient_id"],
            ["patients.workspace_id", "patients.id"],
            ondelete="RESTRICT",
            name="fk_payment_transactions_patient",
        ),
        ForeignKeyConstraint(
            ["workspace_id", "reference_transaction_id"],
            ["payment_transactions.workspace_id", "payment_transactions.id"],
            ondelete="RESTRICT",
            name="fk_payment_transactions_reference",
        ),
        ForeignKeyConstraint(
            ["workspace_id", "patient_package_id"],
            ["patient_packages.workspace_id", "patient_packages.id"],
            ondelete="RESTRICT",
            name="fk_payment_transactions_patient_package",
        ),
        Index(
            "uq_payment_transactions_workspace_idempotency_key",
            "workspace_id",
            "idempotency_key",
            unique=True,
            postgresql_where=text("idempotency_key IS NOT NULL"),
        ),
        Index(
            "ix_payment_transactions_workspace_appointment_created",
            "workspace_id",
            "appointment_id",
            "created_at",
        ),
        Index(
            "ix_payment_transactions_workspace_patient_created",
            "workspace_id",
            "patient_id",
            "created_at",
        ),
        Index(
            "ix_payment_transactions_workspace_currency_created",
            "workspace_id",
            "currency",
            "created_at",
        ),
        Index(
            "ix_payment_transactions_workspace_reference",
            "workspace_id",
            "reference_transaction_id",
        ),
    )

    workspace_id: Mapped[UUID] = mapped_column(index=True, nullable=False)
    appointment_id: Mapped[UUID | None] = mapped_column(index=True, nullable=True)
    origin_appointment_id: Mapped[UUID | None] = mapped_column(index=True, nullable=True)
    patient_id: Mapped[UUID] = mapped_column(index=True, nullable=False)
    created_by_user_id: Mapped[UUID | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"),
        index=True,
        nullable=True,
    )
    reference_transaction_id: Mapped[UUID | None] = mapped_column(index=True, nullable=True)
    patient_package_id: Mapped[UUID | None] = mapped_column(index=True, nullable=True)

    transaction_type: Mapped[str] = mapped_column(String(16), nullable=False)
    amount_minor: Mapped[int] = mapped_column(Integer, nullable=False)
    currency: Mapped[str] = mapped_column(String(3), nullable=False)
    payment_method: Mapped[str] = mapped_column(String(24), nullable=False, default="unknown")
    source: Mapped[str] = mapped_column(String(24), nullable=False, default="staff")
    external_reference: Mapped[str | None] = mapped_column(String(128), nullable=True)
    reason: Mapped[str | None] = mapped_column(Text, nullable=True)
    idempotency_key: Mapped[str | None] = mapped_column(String(128), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)


class PaymentAllocation(UUIDPrimaryKeyMixin, Base):
    """Explicit appointment allocation for a financial transaction.

    A transaction may have no rows (patient-level/unallocated), one row (the
    normal appointment flow), or multiple rows when an external receipt is
    explicitly split across visits. Allocation totals are validated by services;
    the database guarantees positive, workspace-scoped, unique appointment rows.
    """

    __tablename__ = "payment_allocations"
    __table_args__ = (
        UniqueConstraint("workspace_id", "id", name="uq_payment_allocations_workspace_id_id"),
        UniqueConstraint(
            "workspace_id",
            "transaction_id",
            "appointment_id",
            name="uq_payment_allocations_workspace_transaction_appointment",
        ),
        CheckConstraint("amount_minor > 0", name="payment_allocation_amount_positive"),
        ForeignKeyConstraint(
            ["workspace_id"],
            ["workspaces.id"],
            ondelete="CASCADE",
            name="fk_payment_allocations_workspace",
        ),
        ForeignKeyConstraint(
            ["workspace_id", "transaction_id"],
            ["payment_transactions.workspace_id", "payment_transactions.id"],
            ondelete="CASCADE",
            name="fk_payment_allocations_transaction",
        ),
        ForeignKeyConstraint(
            ["workspace_id", "appointment_id"],
            ["appointments.workspace_id", "appointments.id"],
            ondelete="RESTRICT",
            name="fk_payment_allocations_appointment",
        ),
        Index(
            "ix_payment_allocations_workspace_transaction",
            "workspace_id",
            "transaction_id",
        ),
        Index(
            "ix_payment_allocations_workspace_appointment",
            "workspace_id",
            "appointment_id",
        ),
    )

    workspace_id: Mapped[UUID] = mapped_column(index=True, nullable=False)
    transaction_id: Mapped[UUID] = mapped_column(index=True, nullable=False)
    appointment_id: Mapped[UUID] = mapped_column(index=True, nullable=False)
    amount_minor: Mapped[int] = mapped_column(Integer, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)
