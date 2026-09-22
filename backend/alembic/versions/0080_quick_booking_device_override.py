"""Allow quick bookings to overlap laser-device reservations.

Revision ID: 0080_quick_booking_device_override
Revises: 0079_quick_booking_laser_usage
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "0080_quick_booking_device_override"
down_revision: str | Sequence[str] | None = "0079_quick_booking_laser_usage"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_ACTIVE = "('pending', 'confirmed', 'checked_in', 'in_progress')"


def upgrade() -> None:
    op.execute(
        sa.text(
            "ALTER TABLE public.appointments "
            "DROP CONSTRAINT IF EXISTS excl_appointments_laser_device_busy_time"
        )
    )
    op.execute(
        sa.text(
            "ALTER TABLE public.appointments "
            "ADD CONSTRAINT excl_appointments_laser_device_busy_time "
            "EXCLUDE USING gist (workspace_id WITH =, laser_device_key WITH =, "
            "tstzrange(busy_start_at, busy_end_at, '[)') WITH &&) "
            "WHERE (laser_device_key IS NOT NULL "
            "AND NOT is_quick_booking "
            f"AND status IN {_ACTIVE})"
        )
    )


def downgrade() -> None:
    op.execute(
        sa.text(
            "ALTER TABLE public.appointments "
            "DROP CONSTRAINT IF EXISTS excl_appointments_laser_device_busy_time"
        )
    )
    op.execute(
        sa.text(
            "ALTER TABLE public.appointments "
            "ADD CONSTRAINT excl_appointments_laser_device_busy_time "
            "EXCLUDE USING gist (workspace_id WITH =, laser_device_key WITH =, "
            "tstzrange(busy_start_at, busy_end_at, '[)') WITH &&) "
            "WHERE (laser_device_key IS NOT NULL "
            f"AND status IN {_ACTIVE})"
        )
    )
