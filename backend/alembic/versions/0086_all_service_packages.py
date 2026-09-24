"""Allow package offers for non-laser services.

Revision ID: 0086_all_service_packages
Revises: 0085_custom_package_sessions
Create Date: 2026-09-24
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "0086_all_service_packages"
down_revision: str | Sequence[str] | None = "0085_custom_package_sessions"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.drop_constraint(
        "service_package_offer_device_valid",
        "service_package_offers",
        type_="check",
    )
    op.alter_column(
        "service_package_offers",
        "device_key",
        existing_type=sa.String(length=40),
        nullable=True,
    )
    op.alter_column(
        "service_package_offers",
        "device_name",
        existing_type=sa.String(length=120),
        nullable=True,
    )
    op.create_check_constraint(
        "service_package_offer_device_valid",
        "service_package_offers",
        "device_key IS NULL OR device_key IN ('prime_lase', 'candela_gentle')",
    )
    op.create_check_constraint(
        "service_package_offer_device_pair_consistent",
        "service_package_offers",
        "(device_key IS NULL AND device_name IS NULL) OR "
        "(device_key IS NOT NULL AND device_name IS NOT NULL)",
    )
    op.create_index(
        "uq_service_package_offers_service_sessions_no_device",
        "service_package_offers",
        ["workspace_id", "service_id", "sessions_count"],
        unique=True,
        postgresql_where=sa.text("device_key IS NULL"),
    )


def downgrade() -> None:
    bind = op.get_bind()
    if bind.execute(
        sa.text("SELECT 1 FROM service_package_offers WHERE device_key IS NULL LIMIT 1")
    ).first() is not None:
        raise RuntimeError(
            "Cannot downgrade while non-laser service package offers exist."
        )

    op.drop_index(
        "uq_service_package_offers_service_sessions_no_device",
        table_name="service_package_offers",
    )
    op.drop_constraint(
        "service_package_offer_device_pair_consistent",
        "service_package_offers",
        type_="check",
    )
    op.drop_constraint(
        "service_package_offer_device_valid",
        "service_package_offers",
        type_="check",
    )
    op.alter_column(
        "service_package_offers",
        "device_name",
        existing_type=sa.String(length=120),
        nullable=False,
    )
    op.alter_column(
        "service_package_offers",
        "device_key",
        existing_type=sa.String(length=40),
        nullable=False,
    )
    op.create_check_constraint(
        "service_package_offer_device_valid",
        "service_package_offers",
        "device_key IN ('prime_lase', 'candela_gentle')",
    )
