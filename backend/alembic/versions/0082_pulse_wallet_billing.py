"""Add prepaid pulse wallets and post-session settlement.

Revision ID: 0082_pulse_wallet_billing
Revises: 0081_quick_booking_staff_only
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "0082_pulse_wallet_billing"
down_revision: str | Sequence[str] | None = "0081_quick_booking_staff_only"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "pulse_billing_settings",
        sa.Column("workspace_id", sa.Uuid(), nullable=False),
        sa.Column("overage_price_minor", sa.Integer(), nullable=False),
        sa.Column("currency", sa.String(length=3), server_default="EGP", nullable=False),
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.CheckConstraint(
            "overage_price_minor > 0",
            name="pulse_billing_overage_price_positive",
        ),
        sa.ForeignKeyConstraint(
            ["workspace_id"],
            ["workspaces.id"],
            name="fk_pulse_billing_settings_workspace",
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name="pk_pulse_billing_settings"),
        sa.UniqueConstraint("workspace_id", name="uq_pulse_billing_settings_workspace"),
    )
    op.create_index(
        "ix_pulse_billing_settings_workspace_id",
        "pulse_billing_settings",
        ["workspace_id"],
    )

    op.create_table(
        "pulse_pack_offers",
        sa.Column("workspace_id", sa.Uuid(), nullable=False),
        sa.Column("device_key", sa.String(length=40), nullable=False),
        sa.Column("device_name", sa.String(length=120), nullable=False),
        sa.Column("pulses_count", sa.Integer(), nullable=False),
        sa.Column("price_minor", sa.Integer(), nullable=False),
        sa.Column("currency", sa.String(length=3), server_default="EGP", nullable=False),
        sa.Column("is_active", sa.Boolean(), server_default=sa.text("true"), nullable=False),
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.CheckConstraint(
            "device_key IN ('prime_lase', 'candela_gentle')",
            name="pulse_pack_offer_device_valid",
        ),
        sa.CheckConstraint("pulses_count > 0", name="pulse_pack_offer_count_positive"),
        sa.CheckConstraint("price_minor >= 0", name="pulse_pack_offer_price_non_negative"),
        sa.ForeignKeyConstraint(
            ["workspace_id"],
            ["workspaces.id"],
            name="fk_pulse_pack_offers_workspace",
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name="pk_pulse_pack_offers"),
        sa.UniqueConstraint(
            "workspace_id",
            "id",
            name="uq_pulse_pack_offers_workspace_id_id",
        ),
        sa.UniqueConstraint(
            "workspace_id",
            "device_key",
            "pulses_count",
            name="uq_pulse_pack_offers_workspace_device_count",
        ),
    )
    op.create_index("ix_pulse_pack_offers_workspace_id", "pulse_pack_offers", ["workspace_id"])

    op.create_table(
        "patient_pulse_packs",
        sa.Column("workspace_id", sa.Uuid(), nullable=False),
        sa.Column("patient_id", sa.Uuid(), nullable=False),
        sa.Column("pulse_pack_offer_id", sa.Uuid(), nullable=True),
        sa.Column("origin_appointment_id", sa.Uuid(), nullable=True),
        sa.Column("purchase_transaction_id", sa.Uuid(), nullable=True),
        sa.Column("created_by_user_id", sa.Uuid(), nullable=True),
        sa.Column("device_key", sa.String(length=40), nullable=False),
        sa.Column("device_name", sa.String(length=120), nullable=False),
        sa.Column("pulses_purchased", sa.Integer(), nullable=False),
        sa.Column("sale_price_minor", sa.Integer(), nullable=False),
        sa.Column("standalone_pulse_price_minor_at_purchase", sa.Integer(), nullable=True),
        sa.Column("currency", sa.String(length=3), server_default="EGP", nullable=False),
        sa.Column("purchased_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("expires_at", sa.Date(), nullable=True),
        sa.Column("status", sa.String(length=16), server_default="active", nullable=False),
        sa.Column("idempotency_key", sa.String(length=128), nullable=True),
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.CheckConstraint("pulses_purchased > 0", name="patient_pulse_pack_count_positive"),
        sa.CheckConstraint("sale_price_minor >= 0", name="patient_pulse_pack_price_non_negative"),
        sa.CheckConstraint(
            "standalone_pulse_price_minor_at_purchase IS NULL "
            "OR standalone_pulse_price_minor_at_purchase > 0",
            name="patient_pulse_pack_standalone_price_positive",
        ),
        sa.CheckConstraint(
            "device_key IN ('prime_lase', 'candela_gentle')",
            name="patient_pulse_pack_device_valid",
        ),
        sa.CheckConstraint(
            "status IN ('active', 'cancelled')",
            name="patient_pulse_pack_status_valid",
        ),
        sa.ForeignKeyConstraint(
            ["workspace_id"],
            ["workspaces.id"],
            name="fk_patient_pulse_packs_workspace",
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["workspace_id", "patient_id"],
            ["patients.workspace_id", "patients.id"],
            name="fk_patient_pulse_packs_patient",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["workspace_id", "pulse_pack_offer_id"],
            ["pulse_pack_offers.workspace_id", "pulse_pack_offers.id"],
            name="fk_patient_pulse_packs_offer",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["workspace_id", "origin_appointment_id"],
            ["appointments.workspace_id", "appointments.id"],
            name="fk_patient_pulse_packs_origin_appointment",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["created_by_user_id"],
            ["users.id"],
            name="fk_patient_pulse_packs_created_by_user",
            ondelete="SET NULL",
        ),
        sa.PrimaryKeyConstraint("id", name="pk_patient_pulse_packs"),
        sa.UniqueConstraint(
            "workspace_id",
            "id",
            name="uq_patient_pulse_packs_workspace_id_id",
        ),
    )
    op.create_index("ix_patient_pulse_packs_workspace_id", "patient_pulse_packs", ["workspace_id"])
    op.create_index("ix_patient_pulse_packs_patient_id", "patient_pulse_packs", ["patient_id"])
    op.create_index("ix_patient_pulse_packs_pulse_pack_offer_id", "patient_pulse_packs", ["pulse_pack_offer_id"])
    op.create_index("ix_patient_pulse_packs_origin_appointment_id", "patient_pulse_packs", ["origin_appointment_id"])
    op.create_index("ix_patient_pulse_packs_purchase_transaction_id", "patient_pulse_packs", ["purchase_transaction_id"])
    op.create_index(
        "ix_patient_pulse_packs_workspace_patient_device",
        "patient_pulse_packs",
        ["workspace_id", "patient_id", "device_key"],
    )
    op.create_index(
        "uq_patient_pulse_packs_workspace_idempotency_key",
        "patient_pulse_packs",
        ["workspace_id", "idempotency_key"],
        unique=True,
        postgresql_where=sa.text("idempotency_key IS NOT NULL"),
    )

    op.create_table(
        "pulse_usages",
        sa.Column("workspace_id", sa.Uuid(), nullable=False),
        sa.Column("patient_pulse_pack_id", sa.Uuid(), nullable=False),
        sa.Column("appointment_id", sa.Uuid(), nullable=False),
        sa.Column("pulses_used", sa.Integer(), nullable=False),
        sa.Column("status", sa.String(length=16), server_default="consumed", nullable=False),
        sa.Column("used_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.CheckConstraint("pulses_used > 0", name="pulse_usage_count_positive"),
        sa.CheckConstraint(
            "status IN ('consumed', 'reversed')",
            name="pulse_usage_status_valid",
        ),
        sa.ForeignKeyConstraint(
            ["workspace_id"],
            ["workspaces.id"],
            name="fk_pulse_usages_workspace",
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["workspace_id", "patient_pulse_pack_id"],
            ["patient_pulse_packs.workspace_id", "patient_pulse_packs.id"],
            name="fk_pulse_usages_pack",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["workspace_id", "appointment_id"],
            ["appointments.workspace_id", "appointments.id"],
            name="fk_pulse_usages_appointment",
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id", name="pk_pulse_usages"),
        sa.UniqueConstraint("workspace_id", "id", name="uq_pulse_usages_workspace_id_id"),
    )
    op.create_index("ix_pulse_usages_workspace_id", "pulse_usages", ["workspace_id"])
    op.create_index("ix_pulse_usages_patient_pulse_pack_id", "pulse_usages", ["patient_pulse_pack_id"])
    op.create_index("ix_pulse_usages_appointment_id", "pulse_usages", ["appointment_id"])
    op.create_index(
        "ix_pulse_usages_workspace_pack_status",
        "pulse_usages",
        ["workspace_id", "patient_pulse_pack_id", "status"],
    )
    op.create_index(
        "ix_pulse_usages_workspace_appointment",
        "pulse_usages",
        ["workspace_id", "appointment_id"],
    )

    op.create_table(
        "appointment_pulse_settlements",
        sa.Column("workspace_id", sa.Uuid(), nullable=False),
        sa.Column("appointment_id", sa.Uuid(), nullable=False),
        sa.Column("pulses_used", sa.Integer(), nullable=False),
        sa.Column("pulses_from_balance", sa.Integer(), server_default="0", nullable=False),
        sa.Column("deficit_pulses", sa.Integer(), server_default="0", nullable=False),
        sa.Column("resolution", sa.String(length=16), server_default="pending", nullable=False),
        sa.Column("resolution_pulse_pack_id", sa.Uuid(), nullable=True),
        sa.Column("overage_unit_price_minor", sa.Integer(), nullable=True),
        sa.Column("overage_charge_minor", sa.Integer(), server_default="0", nullable=False),
        sa.Column("resolved_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.CheckConstraint("pulses_used >= 0", name="pulse_settlement_used_non_negative"),
        sa.CheckConstraint("pulses_from_balance >= 0", name="pulse_settlement_balance_non_negative"),
        sa.CheckConstraint("deficit_pulses >= 0", name="pulse_settlement_deficit_non_negative"),
        sa.CheckConstraint(
            "overage_unit_price_minor IS NULL OR overage_unit_price_minor > 0",
            name="pulse_settlement_overage_price_positive",
        ),
        sa.CheckConstraint("overage_charge_minor >= 0", name="pulse_settlement_overage_charge_non_negative"),
        sa.CheckConstraint(
            "resolution IN ('pending', 'balance', 'new_pack', 'overage')",
            name="pulse_settlement_resolution_valid",
        ),
        sa.ForeignKeyConstraint(
            ["workspace_id"],
            ["workspaces.id"],
            name="fk_appointment_pulse_settlements_workspace",
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["workspace_id", "appointment_id"],
            ["appointments.workspace_id", "appointments.id"],
            name="fk_appointment_pulse_settlements_appointment",
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["workspace_id", "resolution_pulse_pack_id"],
            ["patient_pulse_packs.workspace_id", "patient_pulse_packs.id"],
            name="fk_appointment_pulse_settlements_resolution_pack",
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id", name="pk_appointment_pulse_settlements"),
        sa.UniqueConstraint(
            "workspace_id",
            "appointment_id",
            name="uq_appointment_pulse_settlements_workspace_appointment",
        ),
    )
    op.create_index(
        "ix_appointment_pulse_settlements_workspace_id",
        "appointment_pulse_settlements",
        ["workspace_id"],
    )
    op.create_index(
        "ix_appointment_pulse_settlements_appointment_id",
        "appointment_pulse_settlements",
        ["appointment_id"],
    )
    op.create_index(
        "ix_appointment_pulse_settlements_resolution_pulse_pack_id",
        "appointment_pulse_settlements",
        ["resolution_pulse_pack_id"],
    )

    op.add_column(
        "payment_transactions",
        sa.Column("patient_pulse_pack_id", sa.Uuid(), nullable=True),
    )
    op.create_index(
        "ix_payment_transactions_patient_pulse_pack_id",
        "payment_transactions",
        ["patient_pulse_pack_id"],
    )
    op.create_foreign_key(
        "fk_payment_transactions_patient_pulse_pack",
        "payment_transactions",
        "patient_pulse_packs",
        ["workspace_id", "patient_pulse_pack_id"],
        ["workspace_id", "id"],
        ondelete="RESTRICT",
    )
    op.create_foreign_key(
        "fk_patient_pulse_packs_purchase_transaction",
        "patient_pulse_packs",
        "payment_transactions",
        ["workspace_id", "purchase_transaction_id"],
        ["workspace_id", "id"],
        ondelete="RESTRICT",
    )

    op.drop_constraint(
        "appointment_billing_context_valid",
        "appointments",
        type_="check",
    )
    op.create_check_constraint(
        "appointment_billing_context_valid",
        "appointments",
        "billing_context IN ('standard', 'package_prepaid', 'pulse_prepaid')",
    )

    for table in (
        "pulse_billing_settings",
        "pulse_pack_offers",
        "patient_pulse_packs",
        "pulse_usages",
        "appointment_pulse_settlements",
    ):
        op.execute(sa.text(f"ALTER TABLE public.{table} ENABLE ROW LEVEL SECURITY"))
        op.execute(sa.text(f"REVOKE ALL ON TABLE public.{table} FROM anon, authenticated"))


def downgrade() -> None:
    op.drop_constraint("appointment_billing_context_valid", "appointments", type_="check")
    op.create_check_constraint(
        "appointment_billing_context_valid",
        "appointments",
        "billing_context IN ('standard', 'package_prepaid')",
    )

    op.drop_constraint(
        "fk_patient_pulse_packs_purchase_transaction",
        "patient_pulse_packs",
        type_="foreignkey",
    )
    op.drop_constraint(
        "fk_payment_transactions_patient_pulse_pack",
        "payment_transactions",
        type_="foreignkey",
    )
    op.drop_index("ix_payment_transactions_patient_pulse_pack_id", table_name="payment_transactions")
    op.drop_column("payment_transactions", "patient_pulse_pack_id")

    op.drop_table("appointment_pulse_settlements")
    op.drop_table("pulse_usages")
    op.drop_table("patient_pulse_packs")
    op.drop_table("pulse_pack_offers")
    op.drop_table("pulse_billing_settings")
