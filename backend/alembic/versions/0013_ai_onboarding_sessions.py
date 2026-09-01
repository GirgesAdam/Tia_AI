"""Add persisted AI-assisted onboarding sessions and audit events.

Revision ID: 0013_ai_onboarding_sessions
Revises: 0012_conversation_workflows
Create Date: 2026-08-14
"""

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision: str = "0013_ai_onboarding_sessions"
down_revision: str | Sequence[str] | None = "0012_conversation_workflows"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "onboarding_ai_sessions",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("workspace_id", sa.Uuid(), nullable=False),
        sa.Column("created_by_user_id", sa.Uuid(), nullable=False),
        sa.Column(
            "status",
            sa.String(length=40),
            server_default="drafting",
            nullable=False,
        ),
        sa.Column(
            "is_active",
            sa.Boolean(),
            server_default=sa.text("true"),
            nullable=False,
        ),
        sa.Column(
            "plan",
            postgresql.JSONB(astext_type=sa.Text()),
            server_default=sa.text("'{}'::jsonb"),
            nullable=False,
        ),
        sa.Column(
            "plan_summary",
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
            "last_decision",
            postgresql.JSONB(astext_type=sa.Text()),
            server_default=sa.text("'{}'::jsonb"),
            nullable=False,
        ),
        sa.Column(
            "execution_result",
            postgresql.JSONB(astext_type=sa.Text()),
            server_default=sa.text("'{}'::jsonb"),
            nullable=False,
        ),
        sa.Column("version", sa.Integer(), server_default="1", nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("last_turn_at", sa.DateTime(timezone=True), nullable=False),
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
            "status IN ('drafting', 'awaiting_confirmation', 'executing', "
            "'completed', 'cancelled', 'expired', 'failed')",
            name="onboarding_ai_session_status_valid",
        ),
        sa.CheckConstraint(
            "version >= 1",
            name="onboarding_ai_session_version_positive",
        ),
        sa.ForeignKeyConstraint(
            ["workspace_id"],
            ["workspaces.id"],
            ondelete="CASCADE",
            name="fk_onboarding_ai_sessions_workspace",
        ),
        sa.ForeignKeyConstraint(
            ["created_by_user_id"],
            ["users.id"],
            ondelete="CASCADE",
            name="fk_onboarding_ai_sessions_created_by_user",
        ),
        sa.PrimaryKeyConstraint("id", name="pk_onboarding_ai_sessions"),
        sa.UniqueConstraint(
            "workspace_id",
            "id",
            name="uq_onboarding_ai_sessions_workspace_id_id",
        ),
    )
    op.create_index(
        "ix_onboarding_ai_sessions_workspace_id",
        "onboarding_ai_sessions",
        ["workspace_id"],
    )
    op.create_index(
        "ix_onboarding_ai_sessions_created_by_user_id",
        "onboarding_ai_sessions",
        ["created_by_user_id"],
    )
    op.create_index(
        "ix_onboarding_ai_sessions_expires_at",
        "onboarding_ai_sessions",
        ["expires_at"],
    )
    op.create_index(
        "uq_onboarding_ai_sessions_active_admin",
        "onboarding_ai_sessions",
        ["workspace_id", "created_by_user_id"],
        unique=True,
        postgresql_where=sa.text("is_active = true"),
    )

    op.create_table(
        "onboarding_ai_events",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("workspace_id", sa.Uuid(), nullable=False),
        sa.Column("session_id", sa.Uuid(), nullable=False),
        sa.Column("user_id", sa.Uuid(), nullable=True),
        sa.Column("event_type", sa.String(length=40), nullable=False),
        sa.Column("actor_type", sa.String(length=30), nullable=False),
        sa.Column("state_version", sa.Integer(), nullable=False),
        sa.Column("content", sa.Text(), nullable=True),
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
            "event_type IN ('started', 'message', 'plan_proposed', "
            "'plan_revised', 'confirmed', 'write_completed', 'cancelled', "
            "'expired', 'failed')",
            name="onboarding_ai_event_type_valid",
        ),
        sa.CheckConstraint(
            "actor_type IN ('admin', 'planner', 'system')",
            name="onboarding_ai_event_actor_valid",
        ),
        sa.ForeignKeyConstraint(
            ["workspace_id", "session_id"],
            ["onboarding_ai_sessions.workspace_id", "onboarding_ai_sessions.id"],
            ondelete="CASCADE",
            name="fk_onboarding_ai_events_session",
        ),
        sa.ForeignKeyConstraint(
            ["user_id"],
            ["users.id"],
            ondelete="SET NULL",
            name="fk_onboarding_ai_events_user",
        ),
        sa.PrimaryKeyConstraint("id", name="pk_onboarding_ai_events"),
    )
    op.create_index(
        "ix_onboarding_ai_events_workspace_id",
        "onboarding_ai_events",
        ["workspace_id"],
    )
    op.create_index(
        "ix_onboarding_ai_events_session_id",
        "onboarding_ai_events",
        ["session_id"],
    )
    op.create_index(
        "ix_onboarding_ai_events_session_created",
        "onboarding_ai_events",
        ["session_id", "created_at"],
    )

    for table in ("onboarding_ai_sessions", "onboarding_ai_events"):
        op.execute(sa.text(f'ALTER TABLE public."{table}" ENABLE ROW LEVEL SECURITY'))
        op.execute(sa.text(f'REVOKE ALL ON TABLE public."{table}" FROM anon, authenticated'))


def downgrade() -> None:
    op.drop_index(
        "ix_onboarding_ai_events_session_created",
        table_name="onboarding_ai_events",
    )
    op.drop_index(
        "ix_onboarding_ai_events_session_id",
        table_name="onboarding_ai_events",
    )
    op.drop_index(
        "ix_onboarding_ai_events_workspace_id",
        table_name="onboarding_ai_events",
    )
    op.drop_table("onboarding_ai_events")

    op.drop_index(
        "uq_onboarding_ai_sessions_active_admin",
        table_name="onboarding_ai_sessions",
    )
    op.drop_index(
        "ix_onboarding_ai_sessions_expires_at",
        table_name="onboarding_ai_sessions",
    )
    op.drop_index(
        "ix_onboarding_ai_sessions_created_by_user_id",
        table_name="onboarding_ai_sessions",
    )
    op.drop_index(
        "ix_onboarding_ai_sessions_workspace_id",
        table_name="onboarding_ai_sessions",
    )
    op.drop_table("onboarding_ai_sessions")
