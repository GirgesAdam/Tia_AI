"""Add Tia AI agent action audit trail.

Revision ID: 0007_agent_foundation
Revises: 0006_booking_engine
Create Date: 2026-08-12
"""

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision: str = "0007_agent_foundation"
down_revision: str | Sequence[str] | None = "0006_booking_engine"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "agent_actions",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("workspace_id", sa.Uuid(), nullable=False),
        sa.Column("conversation_id", sa.Uuid(), nullable=False),
        sa.Column("patient_id", sa.Uuid(), nullable=False),
        sa.Column("appointment_id", sa.Uuid(), nullable=True),
        sa.Column("run_id", sa.Uuid(), nullable=False),
        sa.Column("tool_name", sa.String(length=100), nullable=False),
        sa.Column("action_type", sa.String(length=100), nullable=False),
        sa.Column("status", sa.String(length=20), nullable=False),
        sa.Column(
            "input_json",
            postgresql.JSONB(astext_type=sa.Text()),
            server_default=sa.text("'{}'::jsonb"),
            nullable=False,
        ),
        sa.Column(
            "output_json",
            postgresql.JSONB(astext_type=sa.Text()),
            server_default=sa.text("'{}'::jsonb"),
            nullable=False,
        ),
        sa.Column("error_message", sa.Text(), nullable=True),
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
            "status IN ('success', 'error', 'blocked')",
            name="agent_action_status_valid",
        ),
        sa.ForeignKeyConstraint(
            ["workspace_id"],
            ["workspaces.id"],
            ondelete="CASCADE",
            name="fk_agent_actions_workspace",
        ),
        sa.ForeignKeyConstraint(
            ["workspace_id", "conversation_id"],
            ["conversations.workspace_id", "conversations.id"],
            ondelete="CASCADE",
            name="fk_agent_actions_conversation",
        ),
        sa.ForeignKeyConstraint(
            ["workspace_id", "patient_id"],
            ["patients.workspace_id", "patients.id"],
            ondelete="CASCADE",
            name="fk_agent_actions_patient",
        ),
        sa.ForeignKeyConstraint(
            ["workspace_id", "appointment_id"],
            ["appointments.workspace_id", "appointments.id"],
            ondelete="SET NULL",
            name="fk_agent_actions_appointment",
        ),
        sa.PrimaryKeyConstraint("id", name="pk_agent_actions"),
    )
    op.create_index("ix_agent_actions_workspace_id", "agent_actions", ["workspace_id"])
    op.create_index("ix_agent_actions_conversation_id", "agent_actions", ["conversation_id"])
    op.create_index("ix_agent_actions_patient_id", "agent_actions", ["patient_id"])
    op.create_index("ix_agent_actions_appointment_id", "agent_actions", ["appointment_id"])
    op.create_index("ix_agent_actions_run_id", "agent_actions", ["run_id"])
    op.create_index(
        "ix_agent_actions_workspace_created",
        "agent_actions",
        ["workspace_id", "created_at"],
    )
    op.create_index(
        "ix_agent_actions_conversation_created",
        "agent_actions",
        ["conversation_id", "created_at"],
    )

    op.execute("ALTER TABLE public.agent_actions ENABLE ROW LEVEL SECURITY")
    op.execute("REVOKE ALL ON TABLE public.agent_actions FROM anon")
    op.execute("REVOKE ALL ON TABLE public.agent_actions FROM authenticated")


def downgrade() -> None:
    op.drop_index("ix_agent_actions_conversation_created", table_name="agent_actions")
    op.drop_index("ix_agent_actions_workspace_created", table_name="agent_actions")
    op.drop_index("ix_agent_actions_run_id", table_name="agent_actions")
    op.drop_index("ix_agent_actions_appointment_id", table_name="agent_actions")
    op.drop_index("ix_agent_actions_patient_id", table_name="agent_actions")
    op.drop_index("ix_agent_actions_conversation_id", table_name="agent_actions")
    op.drop_index("ix_agent_actions_workspace_id", table_name="agent_actions")
    op.drop_table("agent_actions")
