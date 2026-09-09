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
    # UUID equality in a GiST exclusion constraint is provided by btree_gist.
    # The extension is trusted on PostgreSQL and is also available on Supabase.
    op.execute(sa.text("CREATE EXTENSION IF NOT EXISTS btree_gist"))
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
    # Alembic's create_exclude_constraint helper treats expression entries as
    # unnamed columns. Use PostgreSQL DDL directly so the tstzrange expression
    # remains exact and the database is the final concurrency guard.
    op.execute(
        sa.text(
            """
            ALTER TABLE public.appointments
            ADD CONSTRAINT excl_appointments_laser_device_busy_time
            EXCLUDE USING gist (
                workspace_id WITH =,
                laser_device_key WITH =,
                tstzrange(busy_start_at, busy_end_at, '[)') WITH &&
            )
            WHERE (
                laser_device_key IS NOT NULL
                AND status IN ('pending', 'confirmed', 'checked_in', 'in_progress')
            )
            """
        )
    )


def downgrade() -> None:
    op.execute(
        sa.text(
            "ALTER TABLE public.appointments "
            "DROP CONSTRAINT IF EXISTS excl_appointments_laser_device_busy_time"
        )
    )
    op.drop_index(
        "ix_appointments_workspace_laser_device_start",
        table_name="appointments",
    )
    op.drop_column("services", "requires_laser_device")
