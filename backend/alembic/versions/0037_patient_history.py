"""Preserve external patient history timestamps for historical analytics.

Revision ID: 0037_patient_history
Revises: 0036_sync_runtime
Create Date: 2026-08-26
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "0037_patient_history"
down_revision: str | Sequence[str] | None = "0036_sync_runtime"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "patients",
        sa.Column("source_created_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_index(
        "ix_patients_workspace_source_created_at",
        "patients",
        ["workspace_id", "source_created_at"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index("ix_patients_workspace_source_created_at", table_name="patients")
    op.drop_column("patients", "source_created_at")
