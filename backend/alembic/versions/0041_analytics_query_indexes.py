"""add analytics query index for appointment cohorts

Revision ID: 0041_analytics_query_indexes
Revises: 0040_doctor_name_hygiene
Create Date: 2026-08-30
"""

from __future__ import annotations

from collections.abc import Sequence

from alembic import op

revision: str = "0041_analytics_query_indexes"
down_revision: str | None = "0040_doctor_name_hygiene"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_index(
        "ix_appointments_workspace_status_start_patient",
        "appointments",
        ["workspace_id", "status", "start_at", "patient_id"],
    )


def downgrade() -> None:
    op.drop_index("ix_appointments_workspace_status_start_patient", table_name="appointments")
