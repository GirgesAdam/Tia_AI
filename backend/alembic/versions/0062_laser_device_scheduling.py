"""Make laser device selection explicit and prevent overlapping device bookings.

Revision ID: 0062_laser_device_scheduling
Revises: 0061_clinic_ops_inventory_products
Create Date: 2026-09-09
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0062_laser_device_scheduling"
down_revision: str | Sequence[str] | None = "0061_clinic_ops_inventory_products"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "services",
        sa.Column(
            "requires_laser_device",
            sa.Boolean(),
            nullable=False,
            server_default=sa.text("false"),
        ),
    )
    op.create_index(
        "ix_appointments_workspace_laser_device_start",
        "appointments",
        ["workspace_id", "laser_device_key", "start_at"],
    )
    op.create_exclude_constraint(
        "excl_appointments_laser_device_busy_time",
        "appointments",
        ("workspace_id", "="),
        ("laser_device_key", "="),
        (sa.text("tstzrange(busy_start_at, busy_end_at, '[)')"), "&&"),
        where=sa.text(
            "laser_device_key IS NOT NULL AND status IN "
            "('pending', 'confirmed', 'checked_in', 'in_progress')"
        ),
        using="gist",
    )


def downgrade() -> None:
    op.drop_constraint(
        "excl_appointments_laser_device_busy_time",
        "appointments",
        type_="exclude",
    )
    op.drop_index(
        "ix_appointments_workspace_laser_device_start",
        table_name="appointments",
    )
    op.drop_column("services", "requires_laser_device")
