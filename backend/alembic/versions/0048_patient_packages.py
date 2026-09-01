"""Add prepaid patient package entitlements and usage ledger.

Revision ID: 0048_patient_packages
Revises: 0047_appointment_billing_context
Create Date: 2026-08-31
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0048_patient_packages"
down_revision: str | None = "0047_appointment_billing_context"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "patient_packages",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("workspace_id", sa.Uuid(), nullable=False),
        sa.Column("patient_id", sa.Uuid(), nullable=False),
        sa.Column("service_id", sa.Uuid(), nullable=False),
        sa.Column("purchase_transaction_id", sa.Uuid(), nullable=True),
        sa.Column("created_by_user_id", sa.Uuid(), nullable=True),
        sa.Column("external_id", sa.String(length=128), nullable=True),
        sa.Column("name", sa.String(length=200), nullable=False),
        sa.Column("sessions_purchased", sa.Integer(), nullable=False),
        sa.Column("sale_price_minor", sa.Integer(), server_default="0", nullable=False),
        sa.Column("currency", sa.String(length=3), server_default="EGP", nullable=False),
        sa.Column("purchased_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("expires_at", sa.Date(), nullable=True),
        sa.Column("status", sa.String(length=16), server_default="active", nullable=False),
        sa.Column("source", sa.String(length=16), server_default="staff", nullable=False),
        sa.Column("idempotency_key", sa.String(length=128), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.CheckConstraint("sessions_purchased > 0", name="patient_package_sessions_positive"),
        sa.CheckConstraint("sale_price_minor >= 0", name="patient_package_price_non_negative"),
        sa.CheckConstraint("status IN ('active', 'expired', 'cancelled')", name="patient_package_status_valid"),
        sa.CheckConstraint("source IN ('staff', 'integration')", name="patient_package_source_valid"),
        sa.ForeignKeyConstraint(["workspace_id"], ["workspaces.id"], ondelete="CASCADE", name="fk_patient_packages_workspace"),
        sa.ForeignKeyConstraint(["workspace_id", "patient_id"], ["patients.workspace_id", "patients.id"], ondelete="RESTRICT", name="fk_patient_packages_patient"),
        sa.ForeignKeyConstraint(["workspace_id", "service_id"], ["services.workspace_id", "services.id"], ondelete="RESTRICT", name="fk_patient_packages_service"),
        sa.ForeignKeyConstraint(["workspace_id", "purchase_transaction_id"], ["payment_transactions.workspace_id", "payment_transactions.id"], ondelete="RESTRICT", name="fk_patient_packages_purchase_transaction"),
        sa.ForeignKeyConstraint(["created_by_user_id"], ["users.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("workspace_id", "id", name="uq_patient_packages_workspace_id_id"),
    )
    op.create_index("ix_patient_packages_workspace_id", "patient_packages", ["workspace_id"])
    op.create_index("ix_patient_packages_patient_id", "patient_packages", ["patient_id"])
    op.create_index("ix_patient_packages_service_id", "patient_packages", ["service_id"])
    op.create_index("ix_patient_packages_purchase_transaction_id", "patient_packages", ["purchase_transaction_id"])
    op.create_index("ix_patient_packages_created_by_user_id", "patient_packages", ["created_by_user_id"])
    op.create_index("ix_patient_packages_workspace_patient_service", "patient_packages", ["workspace_id", "patient_id", "service_id"])
    op.create_index(
        "uq_patient_packages_workspace_external_id",
        "patient_packages",
        ["workspace_id", "external_id"],
        unique=True,
        postgresql_where=sa.text("external_id IS NOT NULL"),
    )
    op.create_index(
        "uq_patient_packages_workspace_idempotency_key",
        "patient_packages",
        ["workspace_id", "idempotency_key"],
        unique=True,
        postgresql_where=sa.text("idempotency_key IS NOT NULL"),
    )

    op.add_column("appointments", sa.Column("patient_package_id", sa.Uuid(), nullable=True))
    op.create_index("ix_appointments_patient_package_id", "appointments", ["patient_package_id"])
    op.create_foreign_key(
        "fk_appointments_patient_package",
        "appointments",
        "patient_packages",
        ["workspace_id", "patient_package_id"],
        ["workspace_id", "id"],
        ondelete="RESTRICT",
    )

    op.create_table(
        "package_usages",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("workspace_id", sa.Uuid(), nullable=False),
        sa.Column("patient_package_id", sa.Uuid(), nullable=False),
        sa.Column("appointment_id", sa.Uuid(), nullable=False),
        sa.Column("external_id", sa.String(length=128), nullable=True),
        sa.Column("sessions_used", sa.Integer(), server_default="1", nullable=False),
        sa.Column("status", sa.String(length=16), server_default="reserved", nullable=False),
        sa.Column("used_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.CheckConstraint("sessions_used > 0", name="package_usage_sessions_positive"),
        sa.CheckConstraint("status IN ('reserved', 'consumed', 'released')", name="package_usage_status_valid"),
        sa.ForeignKeyConstraint(["workspace_id"], ["workspaces.id"], ondelete="CASCADE", name="fk_package_usages_workspace"),
        sa.ForeignKeyConstraint(["workspace_id", "patient_package_id"], ["patient_packages.workspace_id", "patient_packages.id"], ondelete="CASCADE", name="fk_package_usages_package"),
        sa.ForeignKeyConstraint(["workspace_id", "appointment_id"], ["appointments.workspace_id", "appointments.id"], ondelete="RESTRICT", name="fk_package_usages_appointment"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("workspace_id", "id", name="uq_package_usages_workspace_id_id"),
        sa.UniqueConstraint("workspace_id", "appointment_id", name="uq_package_usages_workspace_appointment"),
    )
    op.create_index("ix_package_usages_workspace_id", "package_usages", ["workspace_id"])
    op.create_index("ix_package_usages_patient_package_id", "package_usages", ["patient_package_id"])
    op.create_index("ix_package_usages_appointment_id", "package_usages", ["appointment_id"])
    op.create_index("ix_package_usages_workspace_package_status", "package_usages", ["workspace_id", "patient_package_id", "status"])
    op.create_index(
        "uq_package_usages_workspace_external_id",
        "package_usages",
        ["workspace_id", "external_id"],
        unique=True,
        postgresql_where=sa.text("external_id IS NOT NULL"),
    )

    for table in ("patient_packages", "package_usages"):
        op.execute(sa.text(f'ALTER TABLE public."{table}" ENABLE ROW LEVEL SECURITY'))
        op.execute(sa.text(f'REVOKE ALL ON TABLE public."{table}" FROM anon, authenticated'))


def downgrade() -> None:
    op.drop_table("package_usages")
    op.drop_constraint("fk_appointments_patient_package", "appointments", type_="foreignkey")
    op.drop_index("ix_appointments_patient_package_id", table_name="appointments")
    op.drop_column("appointments", "patient_package_id")
    op.drop_table("patient_packages")
