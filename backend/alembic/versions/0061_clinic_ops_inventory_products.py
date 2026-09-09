"""Add inventory, appointment products, laser device prices and payment methods.

Revision ID: 0061_clinic_ops_inventory_products
Revises: 0060_whatsapp_direct_credentials
Create Date: 2026-09-09
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "0061_clinic_ops_inventory_products"
down_revision: str | Sequence[str] | None = "0060_whatsapp_direct_credentials"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def _secure(table: str) -> None:
    op.execute(sa.text(f'ALTER TABLE public."{table}" ENABLE ROW LEVEL SECURITY'))
    op.execute(sa.text(f'REVOKE ALL ON TABLE public."{table}" FROM anon, authenticated'))


def upgrade() -> None:
    op.create_table(
        "service_device_prices",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("workspace_id", sa.Uuid(), nullable=False),
        sa.Column("service_id", sa.Uuid(), nullable=False),
        sa.Column("device_key", sa.String(length=40), nullable=False),
        sa.Column("device_name", sa.String(length=120), nullable=False),
        sa.Column("price_minor", sa.Integer(), nullable=True),
        sa.Column("currency", sa.String(length=3), server_default="EGP", nullable=False),
        sa.Column("is_active", sa.Boolean(), server_default=sa.text("true"), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.CheckConstraint("device_key IN ('prime_lase', 'candela_gentle')", name="service_device_price_device_valid"),
        sa.CheckConstraint("price_minor IS NULL OR price_minor >= 0", name="service_device_price_non_negative"),
        sa.ForeignKeyConstraint(["workspace_id", "service_id"], ["services.workspace_id", "services.id"], ondelete="CASCADE", name="fk_service_device_prices_service"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("workspace_id", "id", name="uq_service_device_prices_workspace_id_id"),
        sa.UniqueConstraint("workspace_id", "service_id", "device_key", name="uq_service_device_prices_workspace_service_device"),
    )
    op.create_index("ix_service_device_prices_workspace_id", "service_device_prices", ["workspace_id"])
    op.create_index("ix_service_device_prices_service_id", "service_device_prices", ["service_id"])

    op.create_table(
        "clinic_products",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("workspace_id", sa.Uuid(), nullable=False),
        sa.Column("name", sa.String(length=180), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("is_active", sa.Boolean(), server_default=sa.text("true"), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.ForeignKeyConstraint(["workspace_id"], ["workspaces.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("workspace_id", "id", name="uq_clinic_products_workspace_id_id"),
        sa.UniqueConstraint("workspace_id", "name", name="uq_clinic_products_workspace_name"),
    )
    op.create_index("ix_clinic_products_workspace_id", "clinic_products", ["workspace_id"])

    op.create_table(
        "appointment_product_lines",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("workspace_id", sa.Uuid(), nullable=False),
        sa.Column("appointment_id", sa.Uuid(), nullable=False),
        sa.Column("product_id", sa.Uuid(), nullable=False),
        sa.Column("product_name", sa.String(length=180), nullable=False),
        sa.Column("quantity", sa.Integer(), server_default="1", nullable=False),
        sa.Column("unit_price_minor", sa.Integer(), nullable=False),
        sa.Column("currency", sa.String(length=3), server_default="EGP", nullable=False),
        sa.Column("created_by_user_id", sa.Uuid(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.CheckConstraint("quantity > 0", name="appointment_product_line_quantity_positive"),
        sa.CheckConstraint("unit_price_minor >= 0", name="appointment_product_line_price_non_negative"),
        sa.ForeignKeyConstraint(["workspace_id", "appointment_id"], ["appointments.workspace_id", "appointments.id"], ondelete="CASCADE", name="fk_appointment_product_lines_appointment"),
        sa.ForeignKeyConstraint(["workspace_id", "product_id"], ["clinic_products.workspace_id", "clinic_products.id"], ondelete="RESTRICT", name="fk_appointment_product_lines_product"),
        sa.ForeignKeyConstraint(["created_by_user_id"], ["users.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("workspace_id", "id", name="uq_appointment_product_lines_workspace_id_id"),
    )
    op.create_index("ix_appointment_product_lines_workspace_id", "appointment_product_lines", ["workspace_id"])
    op.create_index("ix_appointment_product_lines_appointment_id", "appointment_product_lines", ["appointment_id"])
    op.create_index("ix_appointment_product_lines_product_id", "appointment_product_lines", ["product_id"])

    op.create_table(
        "inventory_items",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("workspace_id", sa.Uuid(), nullable=False),
        sa.Column("name", sa.String(length=180), nullable=False),
        sa.Column("category", sa.String(length=80), server_default="injectable", nullable=False),
        sa.Column("quantity_ml", sa.Numeric(14, 3), server_default="0", nullable=False),
        sa.Column("concentration_mg_per_ml", sa.Numeric(14, 3), nullable=False),
        sa.Column("low_stock_threshold_ml", sa.Numeric(14, 3), nullable=True),
        sa.Column("notes", sa.Text(), nullable=True),
        sa.Column("is_active", sa.Boolean(), server_default=sa.text("true"), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.CheckConstraint("quantity_ml >= 0", name="inventory_item_quantity_non_negative"),
        sa.CheckConstraint("concentration_mg_per_ml > 0", name="inventory_item_concentration_positive"),
        sa.ForeignKeyConstraint(["workspace_id"], ["workspaces.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("workspace_id", "id", name="uq_inventory_items_workspace_id_id"),
        sa.UniqueConstraint("workspace_id", "name", name="uq_inventory_items_workspace_name"),
    )
    op.create_index("ix_inventory_items_workspace_id", "inventory_items", ["workspace_id"])

    op.create_table(
        "inventory_usages",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("workspace_id", sa.Uuid(), nullable=False),
        sa.Column("inventory_item_id", sa.Uuid(), nullable=False),
        sa.Column("appointment_id", sa.Uuid(), nullable=True),
        sa.Column("used_mg", sa.Numeric(14, 3), nullable=False),
        sa.Column("used_ml", sa.Numeric(14, 3), nullable=False),
        sa.Column("note", sa.Text(), nullable=True),
        sa.Column("created_by_user_id", sa.Uuid(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.CheckConstraint("used_mg > 0", name="inventory_usage_mg_positive"),
        sa.CheckConstraint("used_ml > 0", name="inventory_usage_ml_positive"),
        sa.ForeignKeyConstraint(["workspace_id", "inventory_item_id"], ["inventory_items.workspace_id", "inventory_items.id"], ondelete="RESTRICT", name="fk_inventory_usages_item"),
        sa.ForeignKeyConstraint(["workspace_id", "appointment_id"], ["appointments.workspace_id", "appointments.id"], ondelete="SET NULL", name="fk_inventory_usages_appointment"),
        sa.ForeignKeyConstraint(["created_by_user_id"], ["users.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_inventory_usages_workspace_id", "inventory_usages", ["workspace_id"])
    op.create_index("ix_inventory_usages_inventory_item_id", "inventory_usages", ["inventory_item_id"])
    op.create_index("ix_inventory_usages_appointment_id", "inventory_usages", ["appointment_id"])

    op.add_column("appointments", sa.Column("laser_device_key", sa.String(length=40), nullable=True))
    op.add_column("appointments", sa.Column("laser_device_name", sa.String(length=120), nullable=True))
    op.create_check_constraint(
        "appointment_laser_device_valid",
        "appointments",
        "laser_device_key IS NULL OR laser_device_key IN ('prime_lase', 'candela_gentle')",
    )

    op.drop_constraint("ck_appointments_appointment_payment_method_valid", "appointments", type_="check")
    op.create_check_constraint(
        "appointment_payment_method_valid",
        "appointments",
        "payment_method IN ('unknown', 'cash', 'visa', 'instapay', 'card', 'bank_transfer', 'wallet', 'other')",
    )
    op.drop_constraint("ck_payment_transactions_payment_transaction_method_valid", "payment_transactions", type_="check")
    op.create_check_constraint(
        "payment_transaction_method_valid",
        "payment_transactions",
        "payment_method IN ('unknown', 'cash', 'visa', 'instapay', 'card', 'bank_transfer', 'wallet', 'online', 'other')",
    )

    for table in (
        "service_device_prices",
        "clinic_products",
        "appointment_product_lines",
        "inventory_items",
        "inventory_usages",
    ):
        _secure(table)


def downgrade() -> None:
    op.drop_constraint("ck_payment_transactions_payment_transaction_method_valid", "payment_transactions", type_="check")
    op.create_check_constraint(
        "payment_transaction_method_valid",
        "payment_transactions",
        "payment_method IN ('unknown', 'cash', 'card', 'bank_transfer', 'wallet', 'online', 'other')",
    )
    op.drop_constraint("ck_appointments_appointment_payment_method_valid", "appointments", type_="check")
    op.create_check_constraint(
        "appointment_payment_method_valid",
        "appointments",
        "payment_method IN ('unknown', 'cash', 'card', 'bank_transfer', 'wallet', 'other')",
    )
    op.drop_constraint("ck_appointments_appointment_laser_device_valid", "appointments", type_="check")
    op.drop_column("appointments", "laser_device_name")
    op.drop_column("appointments", "laser_device_key")
    op.drop_table("inventory_usages")
    op.drop_table("inventory_items")
    op.drop_table("appointment_product_lines")
    op.drop_table("clinic_products")
    op.drop_table("service_device_prices")
