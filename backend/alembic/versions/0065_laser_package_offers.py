"""Add configurable laser package offers and device snapshots.

Revision ID: 0065_laser_package_offers
Revises: 0064_product_stock_quantity
Create Date: 2026-09-10
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "0065_laser_package_offers"
down_revision: str | Sequence[str] | None = "0064_product_stock_quantity"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "service_package_offers",
        sa.Column("workspace_id", sa.Uuid(), nullable=False),
        sa.Column("service_id", sa.Uuid(), nullable=False),
        sa.Column("device_key", sa.String(length=40), nullable=False),
        sa.Column("device_name", sa.String(length=120), nullable=False),
        sa.Column("sessions_count", sa.Integer(), nullable=False),
        sa.Column("price_minor", sa.Integer(), nullable=False),
        sa.Column("currency", sa.String(length=3), server_default="EGP", nullable=False),
        sa.Column("is_active", sa.Boolean(), server_default=sa.text("true"), nullable=False),
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.CheckConstraint(
            "device_key IN ('prime_lase', 'candela_gentle')",
            name="service_package_offer_device_valid",
        ),
        sa.CheckConstraint(
            "sessions_count IN (3, 6, 9)",
            name="service_package_offer_sessions_valid",
        ),
        sa.CheckConstraint("price_minor >= 0", name="service_package_offer_price_non_negative"),
        sa.ForeignKeyConstraint(
            ["workspace_id", "service_id"],
            ["services.workspace_id", "services.id"],
            name="fk_service_package_offers_service",
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name="pk_service_package_offers"),
        sa.UniqueConstraint(
            "workspace_id",
            "id",
            name="uq_service_package_offers_workspace_id_id",
        ),
        sa.UniqueConstraint(
            "workspace_id",
            "service_id",
            "device_key",
            "sessions_count",
            name="uq_service_package_offers_workspace_service_device_sessions",
        ),
    )
    op.create_index(
        "ix_service_package_offers_workspace_id",
        "service_package_offers",
        ["workspace_id"],
    )
    op.create_index(
        "ix_service_package_offers_service_id",
        "service_package_offers",
        ["service_id"],
    )

    op.add_column("patient_packages", sa.Column("package_offer_id", sa.Uuid(), nullable=True))
    op.add_column("patient_packages", sa.Column("laser_device_key", sa.String(length=40), nullable=True))
    op.add_column("patient_packages", sa.Column("laser_device_name", sa.String(length=120), nullable=True))
    op.create_index("ix_patient_packages_package_offer_id", "patient_packages", ["package_offer_id"])
    op.create_check_constraint(
        "patient_package_laser_device_valid",
        "patient_packages",
        "laser_device_key IS NULL OR laser_device_key IN ('prime_lase', 'candela_gentle')",
    )
    op.create_foreign_key(
        "fk_patient_packages_package_offer",
        "patient_packages",
        "service_package_offers",
        ["workspace_id", "package_offer_id"],
        ["workspace_id", "id"],
        ondelete="RESTRICT",
    )


def downgrade() -> None:
    op.drop_constraint("fk_patient_packages_package_offer", "patient_packages", type_="foreignkey")
    op.drop_constraint("patient_package_laser_device_valid", "patient_packages", type_="check")
    op.drop_index("ix_patient_packages_package_offer_id", table_name="patient_packages")
    op.drop_column("patient_packages", "laser_device_name")
    op.drop_column("patient_packages", "laser_device_key")
    op.drop_column("patient_packages", "package_offer_id")
    op.drop_index("ix_service_package_offers_service_id", table_name="service_package_offers")
    op.drop_index("ix_service_package_offers_workspace_id", table_name="service_package_offers")
    op.drop_table("service_package_offers")
