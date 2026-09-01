"""Add persisted conversation workflow state and audit events.

Revision ID: 0012_conversation_workflows
Revises: 0011_automation_engine
Create Date: 2026-08-13
"""

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision: str = "0012_conversation_workflows"
down_revision: str | Sequence[str] | None = "0011_automation_engine"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "conversation_flow_states",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("workspace_id", sa.Uuid(), nullable=False),
        sa.Column("conversation_id", sa.Uuid(), nullable=False),
        sa.Column("patient_id", sa.Uuid(), nullable=False),
        sa.Column("flow_type", sa.String(length=40), nullable=False),
        sa.Column(
            "status",
            sa.String(length=40),
            server_default="collecting_requirements",
            nullable=False,
        ),
        sa.Column(
            "is_active",
            sa.Boolean(),
            server_default=sa.text("true"),
            nullable=False,
        ),
        sa.Column(
            "capabilities",
            postgresql.JSONB(astext_type=sa.Text()),
            server_default=sa.text("'[]'::jsonb"),
            nullable=False,
        ),
        sa.Column(
            "entity_state",
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
            "pending_action",
            postgresql.JSONB(astext_type=sa.Text()),
            server_default=sa.text("'{}'::jsonb"),
            nullable=False,
        ),
        sa.Column(
            "option_snapshot",
            postgresql.JSONB(astext_type=sa.Text()),
            server_default=sa.text("'{}'::jsonb"),
            nullable=False,
        ),
        sa.Column(
            "last_decision",
            postgresql.JSONB(astext_type=sa.Text()),
            server_default=sa.text("'{}'::jsonb"),
            nullable=False,
        ),
        sa.Column("version", sa.Integer(), server_default="1", nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("last_turn_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("interrupted_at", sa.DateTime(timezone=True), nullable=True),
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
            "flow_type IN ('booking', 'appointment_reschedule')",
            name="conversation_flow_state_type_valid",
        ),
        sa.CheckConstraint(
            "status IN ('collecting_requirements', 'awaiting_option_selection', "
            "'ready_to_execute', 'completed', 'cancelled', 'interrupted', 'expired')",
            name="conversation_flow_state_status_valid",
        ),
        sa.CheckConstraint(
            "version >= 1",
            name="conversation_flow_state_version_positive",
        ),
        sa.ForeignKeyConstraint(
            ["workspace_id", "conversation_id"],
            ["conversations.workspace_id", "conversations.id"],
            ondelete="CASCADE",
            name="fk_conversation_flow_states_conversation",
        ),
        sa.ForeignKeyConstraint(
            ["workspace_id", "patient_id"],
            ["patients.workspace_id", "patients.id"],
            ondelete="CASCADE",
            name="fk_conversation_flow_states_patient",
        ),
        sa.PrimaryKeyConstraint("id", name="pk_conversation_flow_states"),
        sa.UniqueConstraint(
            "workspace_id",
            "id",
            name="uq_conversation_flow_states_workspace_id_id",
        ),
    )
    op.create_index(
        "ix_conversation_flow_states_workspace_id",
        "conversation_flow_states",
        ["workspace_id"],
    )
    op.create_index(
        "ix_conversation_flow_states_conversation_id",
        "conversation_flow_states",
        ["conversation_id"],
    )
    op.create_index(
        "ix_conversation_flow_states_patient_id",
        "conversation_flow_states",
        ["patient_id"],
    )
    op.create_index(
        "ix_conversation_flow_states_expires_at",
        "conversation_flow_states",
        ["expires_at"],
    )
    op.create_index(
        "uq_conversation_flow_states_active_conversation",
        "conversation_flow_states",
        ["workspace_id", "conversation_id"],
        unique=True,
        postgresql_where=sa.text("is_active = true"),
    )
    op.create_index(
        "ix_conversation_flow_states_workspace_active",
        "conversation_flow_states",
        ["workspace_id", "is_active", "expires_at"],
    )
    op.create_index(
        "ix_conversation_flow_states_conversation_created",
        "conversation_flow_states",
        ["conversation_id", "created_at"],
    )

    op.create_table(
        "conversation_flow_events",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("workspace_id", sa.Uuid(), nullable=False),
        sa.Column("flow_state_id", sa.Uuid(), nullable=False),
        sa.Column("conversation_id", sa.Uuid(), nullable=False),
        sa.Column("run_id", sa.Uuid(), nullable=True),
        sa.Column("event_type", sa.String(length=40), nullable=False),
        sa.Column("actor_type", sa.String(length=30), nullable=False),
        sa.Column("state_version", sa.Integer(), nullable=False),
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
            "event_type IN ('started', 'updated', 'options_presented', "
            "'write_authorized', 'write_completed', 'completed', 'cancelled', "
            "'interrupted', 'expired', 'conflict')",
            name="conversation_flow_event_type_valid",
        ),
        sa.CheckConstraint(
            "actor_type IN ('router', 'flow_interpreter', 'agent', 'tool', 'system')",
            name="conversation_flow_event_actor_valid",
        ),
        sa.ForeignKeyConstraint(
            ["workspace_id", "flow_state_id"],
            ["conversation_flow_states.workspace_id", "conversation_flow_states.id"],
            ondelete="CASCADE",
            name="fk_conversation_flow_events_flow_state",
        ),
        sa.ForeignKeyConstraint(
            ["workspace_id", "conversation_id"],
            ["conversations.workspace_id", "conversations.id"],
            ondelete="CASCADE",
            name="fk_conversation_flow_events_conversation",
        ),
        sa.PrimaryKeyConstraint("id", name="pk_conversation_flow_events"),
    )
    op.create_index(
        "ix_conversation_flow_events_workspace_id",
        "conversation_flow_events",
        ["workspace_id"],
    )
    op.create_index(
        "ix_conversation_flow_events_flow_state_id",
        "conversation_flow_events",
        ["flow_state_id"],
    )
    op.create_index(
        "ix_conversation_flow_events_conversation_id",
        "conversation_flow_events",
        ["conversation_id"],
    )
    op.create_index(
        "ix_conversation_flow_events_run_id",
        "conversation_flow_events",
        ["run_id"],
    )
    op.create_index(
        "ix_conversation_flow_events_flow_created",
        "conversation_flow_events",
        ["flow_state_id", "created_at"],
    )
    op.create_index(
        "ix_conversation_flow_events_conversation_created",
        "conversation_flow_events",
        ["conversation_id", "created_at"],
    )

    for table in ("conversation_flow_states", "conversation_flow_events"):
        op.execute(sa.text(f'ALTER TABLE public."{table}" ENABLE ROW LEVEL SECURITY'))
        op.execute(sa.text(f'REVOKE ALL ON TABLE public."{table}" FROM anon, authenticated'))


def downgrade() -> None:
    op.drop_index(
        "ix_conversation_flow_events_conversation_created",
        table_name="conversation_flow_events",
    )
    op.drop_index(
        "ix_conversation_flow_events_flow_created",
        table_name="conversation_flow_events",
    )
    op.drop_index(
        "ix_conversation_flow_events_run_id",
        table_name="conversation_flow_events",
    )
    op.drop_index(
        "ix_conversation_flow_events_conversation_id",
        table_name="conversation_flow_events",
    )
    op.drop_index(
        "ix_conversation_flow_events_flow_state_id",
        table_name="conversation_flow_events",
    )
    op.drop_index(
        "ix_conversation_flow_events_workspace_id",
        table_name="conversation_flow_events",
    )
    op.drop_table("conversation_flow_events")

    op.drop_index(
        "ix_conversation_flow_states_conversation_created",
        table_name="conversation_flow_states",
    )
    op.drop_index(
        "ix_conversation_flow_states_workspace_active",
        table_name="conversation_flow_states",
    )
    op.drop_index(
        "uq_conversation_flow_states_active_conversation",
        table_name="conversation_flow_states",
    )
    op.drop_index(
        "ix_conversation_flow_states_expires_at",
        table_name="conversation_flow_states",
    )
    op.drop_index(
        "ix_conversation_flow_states_patient_id",
        table_name="conversation_flow_states",
    )
    op.drop_index(
        "ix_conversation_flow_states_conversation_id",
        table_name="conversation_flow_states",
    )
    op.drop_index(
        "ix_conversation_flow_states_workspace_id",
        table_name="conversation_flow_states",
    )
    op.drop_table("conversation_flow_states")
