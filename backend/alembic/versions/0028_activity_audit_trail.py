"""Add immutable workspace activity audit trail.

Revision ID: 0028_activity_audit_trail
Revises: 0027_human_handoff_invariant
Create Date: 2026-08-25
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0028_activity_audit_trail"
down_revision: str | Sequence[str] | None = "0027_human_handoff_invariant"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "activity_events",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("workspace_id", sa.Uuid(), nullable=False),
        sa.Column("actor_type", sa.String(length=20), nullable=False),
        sa.Column("actor_user_id", sa.Uuid(), nullable=True),
        sa.Column("action", sa.String(length=80), nullable=False),
        sa.Column("entity_type", sa.String(length=40), nullable=False),
        sa.Column("entity_id", sa.Uuid(), nullable=True),
        sa.Column("summary", sa.Text(), nullable=False),
        sa.Column(
            "metadata",
            postgresql.JSONB(astext_type=sa.Text()),
            server_default=sa.text("'{}'::jsonb"),
            nullable=False,
        ),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.CheckConstraint(
            "actor_type IN ('staff', 'ai', 'system')",
            name="ck_activity_events_activity_event_actor_type_valid",
        ),
        sa.ForeignKeyConstraint(
            ["actor_user_id"],
            ["users.id"],
            name="fk_activity_events_actor_user_id_users",
            ondelete="SET NULL",
        ),
        sa.ForeignKeyConstraint(
            ["workspace_id"],
            ["workspaces.id"],
            name="fk_activity_events_workspace_id_workspaces",
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name="pk_activity_events"),
    )
    op.create_index("ix_activity_events_action", "activity_events", ["action"], unique=False)
    op.create_index("ix_activity_events_actor_user_id", "activity_events", ["actor_user_id"], unique=False)
    op.create_index("ix_activity_events_created_at", "activity_events", ["created_at"], unique=False)
    op.create_index("ix_activity_events_entity_id", "activity_events", ["entity_id"], unique=False)
    op.create_index("ix_activity_events_entity_type", "activity_events", ["entity_type"], unique=False)
    op.create_index("ix_activity_events_workspace_id", "activity_events", ["workspace_id"], unique=False)
    op.create_index(
        "ix_activity_events_workspace_created",
        "activity_events",
        ["workspace_id", "created_at"],
        unique=False,
    )
    op.create_index(
        "ix_activity_events_workspace_actor_created",
        "activity_events",
        ["workspace_id", "actor_type", "created_at"],
        unique=False,
    )
    op.create_index(
        "ix_activity_events_workspace_entity_created",
        "activity_events",
        ["workspace_id", "entity_type", "created_at"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index("ix_activity_events_workspace_entity_created", table_name="activity_events")
    op.drop_index("ix_activity_events_workspace_actor_created", table_name="activity_events")
    op.drop_index("ix_activity_events_workspace_created", table_name="activity_events")
    op.drop_index("ix_activity_events_workspace_id", table_name="activity_events")
    op.drop_index("ix_activity_events_entity_type", table_name="activity_events")
    op.drop_index("ix_activity_events_entity_id", table_name="activity_events")
    op.drop_index("ix_activity_events_created_at", table_name="activity_events")
    op.drop_index("ix_activity_events_actor_user_id", table_name="activity_events")
    op.drop_index("ix_activity_events_action", table_name="activity_events")
    op.drop_table("activity_events")
