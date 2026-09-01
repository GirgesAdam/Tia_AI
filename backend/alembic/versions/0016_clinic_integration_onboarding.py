"""Add persistent clinic integration onboarding sessions and audit events.

Revision ID: 0016_clinic_onboarding
Revises: 0015_clinic_integrations
Create Date: 2026-08-22
"""

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision: str = "0016_clinic_onboarding"
down_revision: str | Sequence[str] | None = "0015_clinic_integrations"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "clinic_integration_onboarding_sessions",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("workspace_id", sa.Uuid(), nullable=False),
        sa.Column("created_by_user_id", sa.Uuid(), nullable=False),
        sa.Column("status", sa.String(length=24), server_default="active", nullable=False),
        sa.Column(
            "stage",
            sa.String(length=48),
            server_default="source_selection",
            nullable=False,
        ),
        sa.Column(
            "is_active",
            sa.Boolean(),
            server_default=sa.text("true"),
            nullable=False,
        ),
        sa.Column("source_type", sa.String(length=32), nullable=True),
        sa.Column("target_mode", sa.String(length=32), nullable=True),
        sa.Column(
            "source_config",
            postgresql.JSONB(astext_type=sa.Text()),
            server_default=sa.text("'{}'::jsonb"),
            nullable=False,
        ),
        sa.Column(
            "document_manifest",
            postgresql.JSONB(astext_type=sa.Text()),
            server_default=sa.text("'[]'::jsonb"),
            nullable=False,
        ),
        sa.Column(
            "mapping",
            postgresql.JSONB(astext_type=sa.Text()),
            server_default=sa.text("'{}'::jsonb"),
            nullable=False,
        ),
        sa.Column(
            "preview_summary",
            postgresql.JSONB(astext_type=sa.Text()),
            server_default=sa.text("'{}'::jsonb"),
            nullable=False,
        ),
        sa.Column(
            "missing_information",
            postgresql.JSONB(astext_type=sa.Text()),
            server_default=sa.text("'[]'::jsonb"),
            nullable=False,
        ),
        sa.Column(
            "readiness",
            postgresql.JSONB(astext_type=sa.Text()),
            server_default=sa.text("'{}'::jsonb"),
            nullable=False,
        ),
        sa.Column(
            "import_result",
            postgresql.JSONB(astext_type=sa.Text()),
            server_default=sa.text("'{}'::jsonb"),
            nullable=False,
        ),
        sa.Column(
            "error_details",
            postgresql.JSONB(astext_type=sa.Text()),
            server_default=sa.text("'{}'::jsonb"),
            nullable=False,
        ),
        sa.Column("version", sa.Integer(), server_default="1", nullable=False),
        sa.Column("last_activity_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("cancelled_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.CheckConstraint(
            "status IN ('active', 'completed', 'cancelled', 'failed')",
            name="clinic_integration_onboarding_session_status_valid",
        ),
        sa.CheckConstraint(
            "stage IN ('source_selection', 'source_selected', 'data_uploaded', "
            "'mapping_proposed', 'mapping_confirmed', 'missing_data_collection', "
            "'validation', 'ready_to_import', 'imported', 'activated', "
            "'cancelled', 'failed')",
            name="clinic_integration_onboarding_session_stage_valid",
        ),
        sa.CheckConstraint(
            "source_type IS NULL OR source_type IN "
            "('tia_native', 'tabular_import', 'external_api', 'hybrid')",
            name="clinic_integration_onboarding_session_source_type_valid",
        ),
        sa.CheckConstraint(
            "target_mode IS NULL OR target_mode IN "
            "('tia_native', 'external_api', 'hybrid', 'imported')",
            name="clinic_integration_onboarding_session_target_mode_valid",
        ),
        sa.CheckConstraint(
            "version >= 1",
            name="clinic_integration_onboarding_session_version_positive",
        ),
        sa.ForeignKeyConstraint(
            ["workspace_id"],
            ["workspaces.id"],
            ondelete="CASCADE",
            name="fk_clinic_integration_onboarding_sessions_workspace",
        ),
        sa.ForeignKeyConstraint(
            ["created_by_user_id"],
            ["users.id"],
            ondelete="RESTRICT",
            name="fk_clinic_integration_onboarding_sessions_created_by_user",
        ),
        sa.PrimaryKeyConstraint(
            "id", name="pk_clinic_integration_onboarding_sessions"
        ),
        sa.UniqueConstraint(
            "workspace_id",
            "id",
            name="uq_clinic_integration_onboarding_sessions_workspace_id_id",
        ),
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
    op.create_index(
        "uq_clinic_integration_onboarding_sessions_active_workspace",
        "clinic_integration_onboarding_sessions",
        ["workspace_id"],
        unique=True,
        postgresql_where=sa.text("is_active = true"),
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
        sa.Column(
            "metadata",
            postgresql.JSONB(astext_type=sa.Text()),
            server_default=sa.text("'{}'::jsonb"),
            nullable=False,
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.CheckConstraint(
            "event_type IN ('started', 'source_selected', 'data_uploaded', "
            "'mapping_proposed', 'mapping_confirmed', 'validation_updated', "
            "'missing_information_updated', 'ready_to_import', 'imported', "
            "'activated', 'cancelled', 'failed')",
            name="clinic_integration_onboarding_event_type_valid",
        ),
        sa.CheckConstraint(
            "actor_type IN ('admin', 'ai', 'system')",
            name="clinic_integration_onboarding_event_actor_valid",
        ),
        sa.ForeignKeyConstraint(
            ["workspace_id", "session_id"],
            [
                "clinic_integration_onboarding_sessions.workspace_id",
                "clinic_integration_onboarding_sessions.id",
            ],
            ondelete="CASCADE",
            name="fk_clinic_integration_onboarding_events_session",
        ),
        sa.ForeignKeyConstraint(
            ["user_id"],
            ["users.id"],
            ondelete="SET NULL",
            name="fk_clinic_integration_onboarding_events_user",
        ),
        sa.PrimaryKeyConstraint("id", name="pk_clinic_integration_onboarding_events"),
    )
    op.create_index(
        "ix_clinic_integration_onboarding_events_workspace_id",
        "clinic_integration_onboarding_events",
        ["workspace_id"],
    )
    op.create_index(
        "ix_clinic_integration_onboarding_events_session_id",
        "clinic_integration_onboarding_events",
        ["session_id"],
    )
    op.create_index(
        "ix_clinic_integration_onboarding_events_session_created",
        "clinic_integration_onboarding_events",
        ["session_id", "created_at"],
    )

    # These tables are backend-only state. Supabase client roles must not read
    # integration manifests, mappings, or audit metadata directly.
    for table in (
        "clinic_integration_onboarding_sessions",
        "clinic_integration_onboarding_events",
    ):
        op.execute(sa.text(f'ALTER TABLE public."{table}" ENABLE ROW LEVEL SECURITY'))
        op.execute(sa.text(f'REVOKE ALL ON TABLE public."{table}" FROM anon, authenticated'))


def downgrade() -> None:
    op.drop_index(
        "ix_clinic_integration_onboarding_events_session_created",
        table_name="clinic_integration_onboarding_events",
    )
    op.drop_index(
        "ix_clinic_integration_onboarding_events_session_id",
        table_name="clinic_integration_onboarding_events",
    )
    op.drop_index(
        "ix_clinic_integration_onboarding_events_workspace_id",
        table_name="clinic_integration_onboarding_events",
    )
    op.drop_table("clinic_integration_onboarding_events")

    op.drop_index(
        "uq_clinic_integration_onboarding_sessions_active_workspace",
        table_name="clinic_integration_onboarding_sessions",
    )
    op.drop_index(
        "ix_clinic_integration_onboarding_sessions_created_by_user_id",
        table_name="clinic_integration_onboarding_sessions",
    )
    op.drop_index(
        "ix_clinic_integration_onboarding_sessions_workspace_id",
        table_name="clinic_integration_onboarding_sessions",
    )
    op.drop_table("clinic_integration_onboarding_sessions")
