"""Preserve sparse imported appointments without inventing doctor assignments.

Revision ID: 0046_sparse_appointment_context
Revises: 0045_public_table_rls_hardening
Create Date: 2026-08-30
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "0046_sparse_appointment_context"
down_revision: str | None = "0045_public_table_rls_hardening"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


_ACTIVE = "('pending', 'confirmed', 'checked_in', 'in_progress')"


def upgrade() -> None:
    op.add_column(
        "appointments",
        sa.Column(
            "doctor_assignment_known",
            sa.Boolean(),
            nullable=False,
            server_default=sa.text("true"),
        ),
    )
    op.execute(
        sa.text(
            "ALTER TABLE appointments "
            "DROP CONSTRAINT excl_appointments_doctor_busy_time"
        )
    )
    op.execute(
        sa.text(
            "ALTER TABLE appointments ADD CONSTRAINT excl_appointments_doctor_busy_time "
            "EXCLUDE USING gist (workspace_id WITH =, doctor_id WITH =, "
            "tstzrange(busy_start_at, busy_end_at, '[)') WITH &&) "
            f"WHERE (doctor_assignment_known AND status IN {_ACTIVE})"
        )
    )


def downgrade() -> None:
    op.execute(
        sa.text(
            "ALTER TABLE appointments "
            "DROP CONSTRAINT excl_appointments_doctor_busy_time"
        )
    )
    op.execute(
        sa.text(
            "ALTER TABLE appointments ADD CONSTRAINT excl_appointments_doctor_busy_time "
            "EXCLUDE USING gist (workspace_id WITH =, doctor_id WITH =, "
            "tstzrange(busy_start_at, busy_end_at, '[)') WITH &&) "
            f"WHERE (status IN {_ACTIVE})"
        )
    )
    op.drop_column("appointments", "doctor_assignment_known")
