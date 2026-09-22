"""Add quick booking overrides and laser pulse tracking.

Revision ID: 0079_quick_booking_laser_usage
Revises: 0078_repair_schedule_billing_categories
"""
from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "0079_quick_booking_laser_usage"
down_revision: str | Sequence[str] | None = "0078_repair_schedule_billing_categories"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None
_ACTIVE = "('pending', 'confirmed', 'checked_in', 'in_progress')"

def upgrade() -> None:
    op.add_column("appointments", sa.Column("is_quick_booking", sa.Boolean(), nullable=False, server_default=sa.text("false")))
    op.add_column("appointments", sa.Column("laser_pulses_used", sa.Integer(), nullable=True))
    op.create_check_constraint("appointment_laser_pulses_non_negative", "appointments", "laser_pulses_used IS NULL OR laser_pulses_used >= 0")
    op.execute(sa.text("""
        UPDATE appointments
        SET busy_start_at = start_at, busy_end_at = end_at
        WHERE status IN ('pending', 'confirmed', 'checked_in', 'in_progress')
    """))
    op.execute(sa.text("ALTER TABLE appointments DROP CONSTRAINT excl_appointments_doctor_busy_time"))
    op.execute(sa.text(
        "ALTER TABLE appointments ADD CONSTRAINT excl_appointments_doctor_busy_time "
        "EXCLUDE USING gist (workspace_id WITH =, doctor_id WITH =, "
        "tstzrange(busy_start_at, busy_end_at, '[)') WITH &&) "
        f"WHERE (doctor_assignment_known AND NOT is_quick_booking AND status IN {_ACTIVE})"
    ))

def downgrade() -> None:
    op.execute(sa.text("ALTER TABLE appointments DROP CONSTRAINT excl_appointments_doctor_busy_time"))
    op.execute(sa.text(
        "ALTER TABLE appointments ADD CONSTRAINT excl_appointments_doctor_busy_time "
        "EXCLUDE USING gist (workspace_id WITH =, doctor_id WITH =, "
        "tstzrange(busy_start_at, busy_end_at, '[)') WITH &&) "
        f"WHERE (doctor_assignment_known AND status IN {_ACTIVE})"
    ))
    op.drop_constraint("appointment_laser_pulses_non_negative", "appointments", type_="check")
    op.drop_column("appointments", "laser_pulses_used")
    op.drop_column("appointments", "is_quick_booking")
