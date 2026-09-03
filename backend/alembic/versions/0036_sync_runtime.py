"""Add durable scheduler state for connector-driven incremental sync.

Revision ID: 0036_sync_runtime
Revises: 0035_appointment_sync
Create Date: 2026-08-26
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "0036_sync_runtime"
down_revision: str | Sequence[str] | None = "0035_appointment_sync"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "clinic_integration_sync_schedules",
        sa.Column("workspace_id", sa.Uuid(), nullable=False),
        sa.Column("enabled", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("interval_minutes", sa.Integer(), nullable=False, server_default="15"),
        sa.Column("next_run_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("locked_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("attempts", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("last_error", sa.String(length=300), nullable=True),
        sa.Column("last_completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.CheckConstraint(
            "interval_minutes >= 5 AND interval_minutes <= 1440",
            name=op.f("ck_clinic_integration_sync_schedules_interval_valid"),
        ),
        sa.CheckConstraint("attempts >= 0", name=op.f("ck_clinic_integration_sync_schedules_attempts_nonneg")),
        sa.ForeignKeyConstraint(
            ["workspace_id"],
            ["clinic_integrations.workspace_id"],
            ondelete="CASCADE",
            name=op.f("fk_clinic_integration_sync_schedules_workspace_id_clinic_integrations"),
        ),
        sa.PrimaryKeyConstraint("workspace_id", name=op.f("pk_clinic_integration_sync_schedules")),
    )
    op.create_index(
        "ix_clinic_integration_sync_schedules_due",
        "clinic_integration_sync_schedules",
        ["enabled", "next_run_at"],
        unique=False,
    )
    op.execute(
        """
        INSERT INTO clinic_integration_sync_schedules (workspace_id, enabled, interval_minutes)
        SELECT workspace_id, false, 15 FROM clinic_integrations
        ON CONFLICT (workspace_id) DO NOTHING
        """
    )


def downgrade() -> None:
    op.drop_index(
        "ix_clinic_integration_sync_schedules_due",
        table_name="clinic_integration_sync_schedules",
    )
    op.drop_table("clinic_integration_sync_schedules")
