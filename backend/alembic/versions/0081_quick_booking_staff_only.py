"""Restrict quick bookings to authenticated staff writes.

Revision ID: 0081_quick_booking_staff_only
Revises: 0080_quick_booking_device_override
"""

from __future__ import annotations

from collections.abc import Sequence

from alembic import op

revision: str = "0081_quick_booking_staff_only"
down_revision: str | Sequence[str] | None = "0080_quick_booking_device_override"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_check_constraint(
        "appointment_quick_booking_staff_only",
        "appointments",
        "NOT is_quick_booking OR (source = 'staff' AND created_by_user_id IS NOT NULL)",
    )


def downgrade() -> None:
    op.drop_constraint(
        "appointment_quick_booking_staff_only",
        "appointments",
        type_="check",
    )
