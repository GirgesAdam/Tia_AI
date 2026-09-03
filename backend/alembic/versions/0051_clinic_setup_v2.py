"""Replace legacy clinic onboarding with simple setup + historical import staging.

Revision ID: 0051_clinic_setup_v2
Revises: 0050_clinic_data_issues
Create Date: 2026-09-01
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision: str = "0051_clinic_setup_v2"
down_revision: str | None = "0050_clinic_data_issues"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # Clinic Setup v2 is single-branch at the product layer. The existing branch
    # table remains because the booking engine uses branch_id internally.
    op.add_column("workspaces", sa.Column("primary_branch_id", sa.Uuid(), nullable=True))
    op.create_foreign_key(
        "fk_workspaces_primary_branch",
        "workspaces",
        "branches",
        ["primary_branch_id"],
        ["id"],
        ondelete="SET NULL",
    )
    op.create_index(
        "ix_workspaces_primary_branch_id",
        "workspaces",
        ["primary_branch_id"],
        unique=False,
    )
    op.execute(
        sa.text(
            """
            UPDATE workspaces AS w
            SET primary_branch_id = (
                SELECT b.id
                FROM branches AS b
                WHERE b.workspace_id = w.id AND b.is_active = true
                ORDER BY b.created_at ASC, b.id ASC
                LIMIT 1
            )
            WHERE w.primary_branch_id IS NULL
            """
        )
    )

    op.add_column(
        "doctors",
        sa.Column("doctor_type", sa.String(length=16), server_default="regular", nullable=False),
    )
    op.create_check_constraint(
        "doctor_type_valid",
        "doctors",
        "doctor_type IN ('regular', 'visiting')",
    )

    # Imported active packages need a trustworthy opening balance without
    # reconstructing every historical package usage row.
    op.add_column(
        "patient_packages",
        sa.Column("opening_sessions_remaining", sa.Integer(), nullable=True),
    )
    op.add_column(
        "patient_packages",
        sa.Column("sessions_total_known", sa.Boolean(), server_default=sa.text("true"), nullable=False),
    )
    op.create_check_constraint(
        "patient_package_opening_remaining_non_negative",
        "patient_packages",
        "opening_sessions_remaining IS NULL OR opening_sessions_remaining >= 0",
    )
    op.create_check_constraint(
        "patient_package_opening_remaining_within_total",
        "patient_packages",
        "opening_sessions_remaining IS NULL OR opening_sessions_remaining <= sessions_purchased",
    )

    # Runtime-created refunds still provide a reference. Historical imports may
    # contain a negative refund without enough source data to identify the
    # original payment. Keep the fact but do not invent the relationship.
    # Historical installations have carried more than one physical name for
    # this check constraint (and a few patch-era databases no longer have it).
    # Never make the v2 rebuild depend on one legacy constraint name.
    for constraint_name in (
        "ck_payment_transactions_payment_transaction_reference_valid",
        "payment_transaction_reference_valid",
    ):
        op.execute(
            sa.text(
                f'ALTER TABLE payment_transactions DROP CONSTRAINT IF EXISTS "{constraint_name}"'
            )
        )
    op.execute(
        sa.text(
            "ALTER TABLE payment_transactions "
            "ADD CONSTRAINT ck_payment_transactions_payment_transaction_reference_valid "
            "CHECK (transaction_type = 'refund' OR reference_transaction_id IS NULL)"
        )
    )

    op.create_table(
        "doctor_availability_windows",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("workspace_id", sa.Uuid(), nullable=False),
        sa.Column("doctor_id", sa.Uuid(), nullable=False),
        sa.Column("branch_id", sa.Uuid(), nullable=False),
        sa.Column("start_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("end_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.CheckConstraint("end_at > start_at", name="doctor_availability_window_interval_valid"),
        sa.ForeignKeyConstraint(
            ["workspace_id", "doctor_id", "branch_id"],
            ["doctor_branches.workspace_id", "doctor_branches.doctor_id", "doctor_branches.branch_id"],
            ondelete="CASCADE",
            name="fk_doctor_availability_windows_assignment",
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "workspace_id", "doctor_id", "branch_id", "start_at", "end_at",
            name="uq_doctor_availability_windows_interval",
        ),
    )
    op.create_index(
        "ix_doctor_availability_windows_workspace_time",
        "doctor_availability_windows",
        ["workspace_id", "start_at", "end_at"],
    )

    op.create_table(
        "clinic_historical_import_batches",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("workspace_id", sa.Uuid(), nullable=False),
        sa.Column("created_by_user_id", sa.Uuid(), nullable=True),
        sa.Column("mode", sa.String(length=32), nullable=False),
        sa.Column("status", sa.String(length=24), server_default="preview_ready", nullable=False),
        sa.Column("schema_version", sa.String(length=32), server_default="tia_history_v1", nullable=False),
        sa.Column("source_name", sa.String(length=255), nullable=False),
        sa.Column("source_fingerprint", sa.String(length=64), nullable=False),
        sa.Column("summary", postgresql.JSONB(astext_type=sa.Text()), server_default=sa.text("'{}'::jsonb"), nullable=False),
        sa.Column("error_message", sa.String(length=1200), nullable=True),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.CheckConstraint(
            "mode IN ('append', 'replace_previous_imports')",
            name="clinic_historical_import_batch_mode_valid",
        ),
        sa.CheckConstraint(
            "status IN ('preview_ready', 'importing', 'imported', 'failed')",
            name="clinic_historical_import_batch_status_valid",
        ),
        sa.ForeignKeyConstraint(["workspace_id"], ["workspaces.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["created_by_user_id"], ["users.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("workspace_id", "id", name="uq_clinic_historical_import_batches_workspace_id_id"),
    )
    op.create_index(
        "ix_clinic_historical_import_batches_workspace_created",
        "clinic_historical_import_batches",
        ["workspace_id", "created_at"],
    )

    op.create_table(
        "clinic_historical_import_rows",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("workspace_id", sa.Uuid(), nullable=False),
        sa.Column("batch_id", sa.Uuid(), nullable=False),
        sa.Column("entity_type", sa.String(length=32), nullable=False),
        sa.Column("source_sheet", sa.String(length=64), nullable=False),
        sa.Column("row_number", sa.Integer(), nullable=False),
        sa.Column("source_record_id", sa.String(length=255), nullable=False),
        sa.Column("payload_hash", sa.String(length=64), nullable=False),
        sa.Column("row_status", sa.String(length=16), nullable=False),
        sa.Column("normalized", postgresql.JSONB(astext_type=sa.Text()), server_default=sa.text("'{}'::jsonb"), nullable=False),
        sa.Column("issue_code", sa.String(length=120), nullable=True),
        sa.Column("issue_message", sa.String(length=1200), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.CheckConstraint(
            "entity_type IN ('patient', 'appointment', 'payment', 'payment_allocation', 'package')",
            name="clinic_historical_import_row_entity_type_valid",
        ),
        sa.CheckConstraint(
            "row_status IN ('ready', 'rejected')",
            name="clinic_historical_import_row_status_valid",
        ),
        sa.ForeignKeyConstraint(
            ["workspace_id", "batch_id"],
            ["clinic_historical_import_batches.workspace_id", "clinic_historical_import_batches.id"],
            ondelete="CASCADE",
            name="fk_clinic_historical_import_rows_batch",
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "batch_id", "entity_type", "source_record_id",
            name="uq_clinic_historical_import_rows_batch_entity_source",
        ),
    )
    op.create_index(
        "ix_clinic_historical_import_rows_batch_status",
        "clinic_historical_import_rows",
        ["batch_id", "row_status"],
    )
    op.create_index(
        "ix_clinic_historical_import_rows_workspace_entity",
        "clinic_historical_import_rows",
        ["workspace_id", "entity_type"],
    )

    op.create_table(
        "clinic_historical_import_links",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("workspace_id", sa.Uuid(), nullable=False),
        sa.Column("batch_id", sa.Uuid(), nullable=False),
        sa.Column("entity_type", sa.String(length=32), nullable=False),
        sa.Column("canonical_id", sa.Uuid(), nullable=False),
        sa.Column("source_record_id", sa.String(length=255), nullable=False),
        sa.Column("payload_hash", sa.String(length=64), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.CheckConstraint(
            "entity_type IN ('patient', 'appointment', 'payment', 'package')",
            name="clinic_historical_import_link_entity_type_valid",
        ),
        sa.ForeignKeyConstraint(
            ["workspace_id", "batch_id"],
            ["clinic_historical_import_batches.workspace_id", "clinic_historical_import_batches.id"],
            ondelete="CASCADE",
            name="fk_clinic_historical_import_links_batch",
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "workspace_id", "entity_type", "source_record_id",
            name="uq_clinic_historical_import_links_source",
        ),
    )
    op.create_index(
        "ix_clinic_historical_import_links_batch_entity",
        "clinic_historical_import_links",
        ["batch_id", "entity_type"],
    )
    op.create_index(
        "ix_clinic_historical_import_links_canonical",
        "clinic_historical_import_links",
        ["workspace_id", "entity_type", "canonical_id"],
    )

    # The old universal-mapping onboarding state is no longer part of the product.
    # Keep Alembic history intact, but remove the live tables and their direct issue FK.
    op.execute(sa.text("ALTER TABLE clinic_data_issues DROP COLUMN IF EXISTS onboarding_session_id"))
    op.execute(sa.text("DROP TABLE IF EXISTS clinic_integration_onboarding_events"))
    op.execute(sa.text("DROP TABLE IF EXISTS clinic_integration_onboarding_sessions"))

    for table in (
        "clinic_historical_import_batches",
        "clinic_historical_import_rows",
        "clinic_historical_import_links",
    ):
        op.execute(sa.text(f'ALTER TABLE public."{table}" ENABLE ROW LEVEL SECURITY'))
        op.execute(sa.text(f'REVOKE ALL ON TABLE public."{table}" FROM anon, authenticated'))


def downgrade() -> None:
    # Restore the legacy onboarding tables sufficiently for schema rollback.
    op.create_table(
        "clinic_integration_onboarding_sessions",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("workspace_id", sa.Uuid(), nullable=False),
        sa.Column("created_by_user_id", sa.Uuid(), nullable=False),
        sa.Column("status", sa.String(length=24), server_default="active", nullable=False),
        sa.Column("stage", sa.String(length=48), server_default="source_selection", nullable=False),
        sa.Column("is_active", sa.Boolean(), server_default=sa.text("true"), nullable=False),
        sa.Column("source_type", sa.String(length=32), nullable=True),
        sa.Column("target_mode", sa.String(length=32), nullable=True),
        sa.Column("source_config", postgresql.JSONB(astext_type=sa.Text()), server_default=sa.text("'{}'::jsonb"), nullable=False),
        sa.Column("document_manifest", postgresql.JSONB(astext_type=sa.Text()), server_default=sa.text("'[]'::jsonb"), nullable=False),
        sa.Column("mapping", postgresql.JSONB(astext_type=sa.Text()), server_default=sa.text("'{}'::jsonb"), nullable=False),
        sa.Column("mapping_proposal", postgresql.JSONB(astext_type=sa.Text()), server_default=sa.text("'{}'::jsonb"), nullable=False),
        sa.Column("preview_summary", postgresql.JSONB(astext_type=sa.Text()), server_default=sa.text("'{}'::jsonb"), nullable=False),
        sa.Column("missing_information", postgresql.JSONB(astext_type=sa.Text()), server_default=sa.text("'[]'::jsonb"), nullable=False),
        sa.Column("missing_data_state", postgresql.JSONB(astext_type=sa.Text()), server_default=sa.text("'{}'::jsonb"), nullable=False),
        sa.Column("readiness", postgresql.JSONB(astext_type=sa.Text()), server_default=sa.text("'{}'::jsonb"), nullable=False),
        sa.Column("import_result", postgresql.JSONB(astext_type=sa.Text()), server_default=sa.text("'{}'::jsonb"), nullable=False),
        sa.Column("error_details", postgresql.JSONB(astext_type=sa.Text()), server_default=sa.text("'{}'::jsonb"), nullable=False),
        sa.Column("version", sa.Integer(), server_default="1", nullable=False),
        sa.Column("last_activity_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("cancelled_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(["workspace_id"], ["workspaces.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["created_by_user_id"], ["users.id"], ondelete="RESTRICT"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("workspace_id", "id", name="uq_clinic_integration_onboarding_sessions_workspace_id_id"),
    )
    op.create_index(
        "uq_clinic_integration_onboarding_sessions_active_workspace",
        "clinic_integration_onboarding_sessions",
        ["workspace_id"],
        unique=True,
        postgresql_where=sa.text("is_active = true"),
    )
    op.create_index(
        "ix_clinic_integration_onboarding_sessions_workspace_id",
        "clinic_integration_onboarding_sessions",
        ["workspace_id"],
    )
    op.create_index(
        "ix_clinic_integration_onboarding_sessions_created_by_user_id",
        "clinic_integration_onboarding_sessions",
        ["created_by_user_id"],
    )

    op.create_table(
        "clinic_integration_onboarding_events",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("workspace_id", sa.Uuid(), nullable=False),
        sa.Column("session_id", sa.Uuid(), nullable=False),
        sa.Column("user_id", sa.Uuid(), nullable=True),
        sa.Column("event_type", sa.String(length=48), nullable=False),
        sa.Column("actor_type", sa.String(length=24), nullable=False),
        sa.Column("state_version", sa.Integer(), nullable=False),
        sa.Column("stage", sa.String(length=48), nullable=False),
        sa.Column("metadata", postgresql.JSONB(astext_type=sa.Text()), server_default=sa.text("'{}'::jsonb"), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(
            ["workspace_id", "session_id"],
            ["clinic_integration_onboarding_sessions.workspace_id", "clinic_integration_onboarding_sessions.id"],
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.add_column("clinic_data_issues", sa.Column("onboarding_session_id", sa.Uuid(), nullable=True))
    op.create_foreign_key(
        "fk_clinic_data_issues_onboarding_session",
        "clinic_data_issues",
        "clinic_integration_onboarding_sessions",
        ["onboarding_session_id"],
        ["id"],
        ondelete="SET NULL",
    )

    op.drop_index("ix_clinic_historical_import_links_canonical", table_name="clinic_historical_import_links")
    op.drop_index("ix_clinic_historical_import_links_batch_entity", table_name="clinic_historical_import_links")
    op.drop_table("clinic_historical_import_links")
    op.drop_index("ix_clinic_historical_import_rows_workspace_entity", table_name="clinic_historical_import_rows")
    op.drop_index("ix_clinic_historical_import_rows_batch_status", table_name="clinic_historical_import_rows")
    op.drop_table("clinic_historical_import_rows")
    op.drop_index("ix_clinic_historical_import_batches_workspace_created", table_name="clinic_historical_import_batches")
    op.drop_table("clinic_historical_import_batches")

    for constraint_name in (
        "ck_payment_transactions_payment_transaction_reference_valid",
        "payment_transaction_reference_valid",
    ):
        op.execute(
            sa.text(
                f'ALTER TABLE payment_transactions DROP CONSTRAINT IF EXISTS "{constraint_name}"'
            )
        )
    op.execute(
        sa.text(
            "ALTER TABLE payment_transactions "
            "ADD CONSTRAINT ck_payment_transactions_payment_transaction_reference_valid "
            "CHECK ((transaction_type = 'payment' AND reference_transaction_id IS NULL) OR "
            "(transaction_type = 'refund' AND reference_transaction_id IS NOT NULL))"
        )
    )

    op.drop_constraint("patient_package_opening_remaining_within_total", "patient_packages", type_="check")
    op.drop_constraint("patient_package_opening_remaining_non_negative", "patient_packages", type_="check")
    op.drop_column("patient_packages", "sessions_total_known")
    op.drop_column("patient_packages", "opening_sessions_remaining")

    op.drop_index("ix_doctor_availability_windows_workspace_time", table_name="doctor_availability_windows")
    op.drop_table("doctor_availability_windows")

    op.drop_constraint("doctor_type_valid", "doctors", type_="check")
    op.drop_column("doctors", "doctor_type")

    op.drop_index("ix_workspaces_primary_branch_id", table_name="workspaces")
    op.drop_constraint("fk_workspaces_primary_branch", "workspaces", type_="foreignkey")
    op.drop_column("workspaces", "primary_branch_id")
