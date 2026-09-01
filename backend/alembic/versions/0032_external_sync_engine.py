"""Add durable external sync runs, checkpoints, and isolated failures.

Revision ID: 0032_external_sync_engine
Revises: 0031_payment_allocations
Create Date: 2026-08-26
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0032_external_sync_engine"
down_revision: str | Sequence[str] | None = "0031_payment_allocations"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "clinic_integration_sync_runs",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("workspace_id", sa.Uuid(), nullable=False),
        sa.Column("domain", sa.String(length=24), nullable=False),
        sa.Column("status", sa.String(length=20), nullable=False),
        sa.Column("cursor_before", sa.String(length=512), nullable=True),
        sa.Column("cursor_after", sa.String(length=512), nullable=True),
        sa.Column("source_revision", sa.String(length=255), nullable=True),
        sa.Column("processed_count", sa.Integer(), server_default="0", nullable=False),
        sa.Column("created_count", sa.Integer(), server_default="0", nullable=False),
        sa.Column("updated_count", sa.Integer(), server_default="0", nullable=False),
        sa.Column("skipped_count", sa.Integer(), server_default="0", nullable=False),
        sa.Column("failed_count", sa.Integer(), server_default="0", nullable=False),
        sa.Column("started_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.CheckConstraint("domain IN ('patients', 'payments')", name="ck_clinic_integration_sync_runs_domain_valid"),
        sa.CheckConstraint("status IN ('running', 'succeeded', 'partial', 'failed')", name="ck_clinic_integration_sync_runs_status_valid"),
        sa.CheckConstraint("processed_count >= 0", name="ck_clinic_integration_sync_runs_processed_nonneg"),
        sa.CheckConstraint("created_count >= 0", name="ck_clinic_integration_sync_runs_created_nonneg"),
        sa.CheckConstraint("updated_count >= 0", name="ck_clinic_integration_sync_runs_updated_nonneg"),
        sa.CheckConstraint("skipped_count >= 0", name="ck_clinic_integration_sync_runs_skipped_nonneg"),
        sa.CheckConstraint("failed_count >= 0", name="ck_clinic_integration_sync_runs_failed_nonneg"),
        sa.ForeignKeyConstraint(["workspace_id"], ["clinic_integrations.workspace_id"], ondelete="CASCADE", name="fk_sync_runs_integration"),
        sa.PrimaryKeyConstraint("id", name="pk_clinic_integration_sync_runs"),
        sa.UniqueConstraint("workspace_id", "id", name="uq_sync_runs_workspace_id"),
    )
    op.create_index("ix_clinic_integration_sync_runs_workspace_id", "clinic_integration_sync_runs", ["workspace_id"])
    op.create_index("ix_clinic_integration_sync_runs_workspace_domain_started", "clinic_integration_sync_runs", ["workspace_id", "domain", "started_at"])

    op.create_table(
        "clinic_integration_sync_checkpoints",
        sa.Column("workspace_id", sa.Uuid(), nullable=False),
        sa.Column("domain", sa.String(length=24), nullable=False),
        sa.Column("cursor", sa.String(length=512), nullable=True),
        sa.Column("source_revision", sa.String(length=255), nullable=True),
        sa.Column("last_success_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_run_id", sa.Uuid(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.CheckConstraint("domain IN ('patients', 'payments')", name="ck_clinic_integration_sync_checkpoints_domain_valid"),
        sa.ForeignKeyConstraint(["workspace_id"], ["clinic_integrations.workspace_id"], ondelete="CASCADE", name="fk_sync_checkpoints_integration"),
        sa.ForeignKeyConstraint(["last_run_id"], ["clinic_integration_sync_runs.id"], ondelete="SET NULL", name="fk_sync_checkpoints_last_run"),
        sa.PrimaryKeyConstraint("workspace_id", "domain", name="pk_clinic_integration_sync_checkpoints"),
    )

    op.create_table(
        "clinic_integration_sync_failures",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("workspace_id", sa.Uuid(), nullable=False),
        sa.Column("run_id", sa.Uuid(), nullable=False),
        sa.Column("domain", sa.String(length=24), nullable=False),
        sa.Column("external_id_digest", sa.String(length=64), nullable=False),
        sa.Column("error_code", sa.String(length=80), nullable=False),
        sa.Column("message", sa.String(length=300), nullable=False),
        sa.Column("retryable", sa.Boolean(), server_default=sa.true(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.CheckConstraint("domain IN ('patients', 'payments')", name="ck_clinic_integration_sync_failures_domain_valid"),
        sa.ForeignKeyConstraint(["workspace_id"], ["clinic_integrations.workspace_id"], ondelete="CASCADE", name="fk_sync_failures_integration"),
        sa.ForeignKeyConstraint(["workspace_id", "run_id"], ["clinic_integration_sync_runs.workspace_id", "clinic_integration_sync_runs.id"], ondelete="CASCADE", name="fk_sync_failures_run"),
        sa.PrimaryKeyConstraint("id", name="pk_clinic_integration_sync_failures"),
    )
    op.create_index("ix_clinic_integration_sync_failures_workspace_id", "clinic_integration_sync_failures", ["workspace_id"])
    op.create_index("ix_clinic_integration_sync_failures_run_id", "clinic_integration_sync_failures", ["run_id"])
    op.create_index("ix_clinic_integration_sync_failures_workspace_run", "clinic_integration_sync_failures", ["workspace_id", "run_id"])


def downgrade() -> None:
    op.drop_index("ix_clinic_integration_sync_failures_workspace_run", table_name="clinic_integration_sync_failures")
    op.drop_index("ix_clinic_integration_sync_failures_run_id", table_name="clinic_integration_sync_failures")
    op.drop_index("ix_clinic_integration_sync_failures_workspace_id", table_name="clinic_integration_sync_failures")
    op.drop_table("clinic_integration_sync_failures")
    op.drop_table("clinic_integration_sync_checkpoints")
    op.drop_index("ix_clinic_integration_sync_runs_workspace_domain_started", table_name="clinic_integration_sync_runs")
    op.drop_index("ix_clinic_integration_sync_runs_workspace_id", table_name="clinic_integration_sync_runs")
    op.drop_table("clinic_integration_sync_runs")
