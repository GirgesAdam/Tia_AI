"""Add human handoff queue and team inbox audit trail.

Revision ID: 0008_team_inbox
Revises: 0007_agent_foundation
Create Date: 2026-08-13
"""

from collections.abc import Sequence
from uuid import uuid4

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision: str = "0008_team_inbox"
down_revision: str | Sequence[str] | None = "0007_agent_foundation"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "handoff_requests",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("workspace_id", sa.Uuid(), nullable=False),
        sa.Column("conversation_id", sa.Uuid(), nullable=False),
        sa.Column("patient_id", sa.Uuid(), nullable=False),
        sa.Column("status", sa.String(length=20), server_default="pending", nullable=False),
        sa.Column("category", sa.String(length=40), server_default="other", nullable=False),
        sa.Column("priority", sa.String(length=20), server_default="normal", nullable=False),
        sa.Column("source", sa.String(length=20), server_default="ai", nullable=False),
        sa.Column("reason", sa.Text(), nullable=False),
        sa.Column("assigned_user_id", sa.Uuid(), nullable=True),
        sa.Column("created_by_user_id", sa.Uuid(), nullable=True),
        sa.Column("claimed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("resolved_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("resolved_by_user_id", sa.Uuid(), nullable=True),
        sa.Column("resolution_note", sa.Text(), nullable=True),
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
            "status IN ('pending', 'claimed', 'resolved')",
            name="handoff_request_status_valid",
        ),
        sa.CheckConstraint(
            "category IN ('medical', 'complaint', 'payment', 'customer_request', "
            "'booking_exception', 'agent_uncertain', 'other')",
            name="handoff_request_category_valid",
        ),
        sa.CheckConstraint(
            "priority IN ('low', 'normal', 'high', 'urgent')",
            name="handoff_request_priority_valid",
        ),
        sa.CheckConstraint(
            "source IN ('ai', 'staff', 'system', 'customer')",
            name="handoff_request_source_valid",
        ),
        sa.ForeignKeyConstraint(
            ["workspace_id", "conversation_id"],
            ["conversations.workspace_id", "conversations.id"],
            ondelete="CASCADE",
            name="fk_handoff_requests_conversation",
        ),
        sa.ForeignKeyConstraint(
            ["workspace_id", "patient_id"],
            ["patients.workspace_id", "patients.id"],
            ondelete="CASCADE",
            name="fk_handoff_requests_patient",
        ),
        sa.ForeignKeyConstraint(
            ["assigned_user_id"],
            ["users.id"],
            ondelete="SET NULL",
            name="fk_handoff_requests_assigned_user_id_users",
        ),
        sa.ForeignKeyConstraint(
            ["created_by_user_id"],
            ["users.id"],
            ondelete="SET NULL",
            name="fk_handoff_requests_created_by_user_id_users",
        ),
        sa.ForeignKeyConstraint(
            ["resolved_by_user_id"],
            ["users.id"],
            ondelete="SET NULL",
            name="fk_handoff_requests_resolved_by_user_id_users",
        ),
        sa.PrimaryKeyConstraint("id", name="pk_handoff_requests"),
        sa.UniqueConstraint(
            "workspace_id",
            "id",
            name="uq_handoff_requests_workspace_id_id",
        ),
    )
    op.create_index("ix_handoff_requests_workspace_id", "handoff_requests", ["workspace_id"])
    op.create_index("ix_handoff_requests_conversation_id", "handoff_requests", ["conversation_id"])
    op.create_index("ix_handoff_requests_patient_id", "handoff_requests", ["patient_id"])
    op.create_index(
        "ix_handoff_requests_assigned_user_id", "handoff_requests", ["assigned_user_id"]
    )
    op.create_index(
        "uq_handoff_requests_active_conversation",
        "handoff_requests",
        ["workspace_id", "conversation_id"],
        unique=True,
        postgresql_where=sa.text("status IN ('pending', 'claimed')"),
    )
    op.create_index(
        "ix_handoff_requests_workspace_queue",
        "handoff_requests",
        ["workspace_id", "status", "priority", "created_at"],
    )
    op.create_index(
        "ix_handoff_requests_workspace_assignee",
        "handoff_requests",
        ["workspace_id", "assigned_user_id", "status"],
    )

    op.create_table(
        "handoff_events",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("workspace_id", sa.Uuid(), nullable=False),
        sa.Column("handoff_request_id", sa.Uuid(), nullable=False),
        sa.Column("conversation_id", sa.Uuid(), nullable=False),
        sa.Column("event_type", sa.String(length=32), nullable=False),
        sa.Column("actor_type", sa.String(length=20), nullable=False),
        sa.Column("actor_user_id", sa.Uuid(), nullable=True),
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
            "event_type IN ('created', 'claimed', 'assigned', 'staff_replied', "
            "'resolved', 'reopened')",
            name="handoff_event_type_valid",
        ),
        sa.CheckConstraint(
            "actor_type IN ('ai', 'staff', 'system')",
            name="handoff_event_actor_type_valid",
        ),
        sa.ForeignKeyConstraint(
            ["workspace_id", "handoff_request_id"],
            ["handoff_requests.workspace_id", "handoff_requests.id"],
            ondelete="CASCADE",
            name="fk_handoff_events_handoff",
        ),
        sa.ForeignKeyConstraint(
            ["workspace_id", "conversation_id"],
            ["conversations.workspace_id", "conversations.id"],
            ondelete="CASCADE",
            name="fk_handoff_events_conversation",
        ),
        sa.ForeignKeyConstraint(
            ["actor_user_id"],
            ["users.id"],
            ondelete="SET NULL",
            name="fk_handoff_events_actor_user_id_users",
        ),
        sa.PrimaryKeyConstraint("id", name="pk_handoff_events"),
    )
    op.create_index("ix_handoff_events_workspace_id", "handoff_events", ["workspace_id"])
    op.create_index(
        "ix_handoff_events_handoff_request_id", "handoff_events", ["handoff_request_id"]
    )
    op.create_index("ix_handoff_events_conversation_id", "handoff_events", ["conversation_id"])
    op.create_index("ix_handoff_events_actor_user_id", "handoff_events", ["actor_user_id"])
    op.create_index(
        "ix_handoff_events_handoff_created",
        "handoff_events",
        ["handoff_request_id", "created_at"],
    )
    op.create_index(
        "ix_handoff_events_workspace_created",
        "handoff_events",
        ["workspace_id", "created_at"],
    )

    # Preserve any staging/production conversations that were already marked pending
    # by the earlier agent implementation before a first-class handoff table existed.
    bind = op.get_bind()
    pending_rows = bind.execute(
        sa.text(
            "SELECT workspace_id, id AS conversation_id, patient_id "
            "FROM conversations WHERE status = 'pending'"
        )
    ).mappings()
    for row in pending_rows:
        handoff_id = uuid4()
        bind.execute(
            sa.text(
                "INSERT INTO handoff_requests "
                "(id, workspace_id, conversation_id, patient_id, status, category, "
                "priority, source, reason) "
                "VALUES (:id, :workspace_id, :conversation_id, :patient_id, "
                "'pending', 'other', 'normal', 'system', :reason)"
            ),
            {
                "id": handoff_id,
                "workspace_id": row["workspace_id"],
                "conversation_id": row["conversation_id"],
                "patient_id": row["patient_id"],
                "reason": "Migrated from an existing pending conversation.",
            },
        )
        bind.execute(
            sa.text(
                "INSERT INTO handoff_events "
                "(id, workspace_id, handoff_request_id, conversation_id, "
                "event_type, actor_type, metadata) "
                "VALUES (:id, :workspace_id, :handoff_request_id, :conversation_id, "
                "'created', 'system', CAST(:metadata AS jsonb))"
            ),
            {
                "id": uuid4(),
                "workspace_id": row["workspace_id"],
                "handoff_request_id": handoff_id,
                "conversation_id": row["conversation_id"],
                "metadata": '{"migration":"0008_team_inbox"}',
            },
        )

    for table in ("handoff_requests", "handoff_events"):
        op.execute(sa.text(f'ALTER TABLE public."{table}" ENABLE ROW LEVEL SECURITY'))
        op.execute(sa.text(f'REVOKE ALL ON TABLE public."{table}" FROM anon, authenticated'))


def downgrade() -> None:
    op.drop_index("ix_handoff_events_workspace_created", table_name="handoff_events")
    op.drop_index("ix_handoff_events_handoff_created", table_name="handoff_events")
    op.drop_index("ix_handoff_events_actor_user_id", table_name="handoff_events")
    op.drop_index("ix_handoff_events_conversation_id", table_name="handoff_events")
    op.drop_index("ix_handoff_events_handoff_request_id", table_name="handoff_events")
    op.drop_index("ix_handoff_events_workspace_id", table_name="handoff_events")
    op.drop_table("handoff_events")

    op.drop_index("ix_handoff_requests_workspace_assignee", table_name="handoff_requests")
    op.drop_index("ix_handoff_requests_workspace_queue", table_name="handoff_requests")
    op.drop_index("uq_handoff_requests_active_conversation", table_name="handoff_requests")
    op.drop_index("ix_handoff_requests_assigned_user_id", table_name="handoff_requests")
    op.drop_index("ix_handoff_requests_patient_id", table_name="handoff_requests")
    op.drop_index("ix_handoff_requests_conversation_id", table_name="handoff_requests")
    op.drop_index("ix_handoff_requests_workspace_id", table_name="handoff_requests")
    op.drop_table("handoff_requests")
