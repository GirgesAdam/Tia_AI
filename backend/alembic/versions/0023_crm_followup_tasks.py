"""Add durable CRM follow-up and task queue.

Revision ID: 0023_crm_followup_tasks
Revises: 0022_handoff_intelligence
Create Date: 2026-08-25
"""

from collections.abc import Sequence
from uuid import uuid4

import sqlalchemy as sa

from alembic import op

revision: str = "0023_crm_followup_tasks"
down_revision: str | Sequence[str] | None = "0022_handoff_intelligence"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "crm_tasks",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("workspace_id", sa.Uuid(), nullable=False),
        sa.Column("patient_id", sa.Uuid(), nullable=False),
        sa.Column("lead_id", sa.Uuid(), nullable=True),
        sa.Column("conversation_id", sa.Uuid(), nullable=True),
        sa.Column("assigned_user_id", sa.Uuid(), nullable=True),
        sa.Column("created_by_user_id", sa.Uuid(), nullable=True),
        sa.Column("completed_by_user_id", sa.Uuid(), nullable=True),
        sa.Column("task_type", sa.String(length=24), server_default="follow_up", nullable=False),
        sa.Column("source", sa.String(length=20), server_default="manual", nullable=False),
        sa.Column("status", sa.String(length=20), server_default="pending", nullable=False),
        sa.Column("priority", sa.String(length=20), server_default="normal", nullable=False),
        sa.Column("title", sa.String(length=200), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("due_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("dedupe_key", sa.String(length=255), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.CheckConstraint("task_type IN ('follow_up', 'general')", name="crm_task_type_valid"),
        sa.CheckConstraint(
            "status IN ('pending', 'in_progress', 'completed', 'cancelled')",
            name="crm_task_status_valid",
        ),
        sa.CheckConstraint(
            "priority IN ('low', 'normal', 'high', 'urgent')",
            name="crm_task_priority_valid",
        ),
        sa.CheckConstraint(
            "source IN ('manual', 'ai', 'system')",
            name="crm_task_source_valid",
        ),
        sa.ForeignKeyConstraint(["workspace_id"], ["workspaces.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(
            ["workspace_id", "patient_id"],
            ["patients.workspace_id", "patients.id"],
            ondelete="CASCADE",
            name="fk_crm_tasks_patient",
        ),
        sa.ForeignKeyConstraint(
            ["workspace_id", "lead_id"],
            ["leads.workspace_id", "leads.id"],
            name="fk_crm_tasks_lead",
        ),
        sa.ForeignKeyConstraint(
            ["workspace_id", "conversation_id"],
            ["conversations.workspace_id", "conversations.id"],
            name="fk_crm_tasks_conversation",
        ),
        sa.ForeignKeyConstraint(["assigned_user_id"], ["users.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["created_by_user_id"], ["users.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["completed_by_user_id"], ["users.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("workspace_id", "id", name="uq_crm_tasks_workspace_id_id"),
    )
    op.create_index("ix_crm_tasks_workspace_id", "crm_tasks", ["workspace_id"])
    op.create_index("ix_crm_tasks_patient_id", "crm_tasks", ["patient_id"])
    op.create_index("ix_crm_tasks_lead_id", "crm_tasks", ["lead_id"])
    op.create_index("ix_crm_tasks_conversation_id", "crm_tasks", ["conversation_id"])
    op.create_index("ix_crm_tasks_assigned_user_id", "crm_tasks", ["assigned_user_id"])
    op.create_index("ix_crm_tasks_due_at", "crm_tasks", ["due_at"])
    op.create_index(
        "ix_crm_tasks_workspace_queue",
        "crm_tasks",
        ["workspace_id", "status", "due_at", "assigned_user_id"],
    )
    op.create_index(
        "ix_crm_tasks_workspace_patient_status",
        "crm_tasks",
        ["workspace_id", "patient_id", "status"],
    )
    op.create_index(
        "uq_crm_tasks_workspace_dedupe",
        "crm_tasks",
        ["workspace_id", "dedupe_key"],
        unique=True,
    )

    # Preserve pre-5.2 lead follow-ups by materializing them into the new
    # canonical task queue. The legacy Lead.next_follow_up_at field remains
    # for compatibility and is synchronized by the application thereafter.
    bind = op.get_bind()
    rows = bind.execute(
        sa.text(
            """
            SELECT id, workspace_id, patient_id, assigned_user_id, next_follow_up_at
            FROM leads
            WHERE next_follow_up_at IS NOT NULL
            """
        )
    ).mappings()
    for row in rows:
        bind.execute(
            sa.text(
                """
                INSERT INTO crm_tasks (
                    id, workspace_id, patient_id, lead_id, assigned_user_id,
                    created_by_user_id, completed_by_user_id, task_type, source,
                    status, priority, title, description, due_at, completed_at,
                    dedupe_key
                ) VALUES (
                    :id, :workspace_id, :patient_id, :lead_id, :assigned_user_id,
                    NULL, NULL, 'follow_up', 'system', 'pending', 'normal',
                    'Lead follow-up', NULL, :due_at, NULL, :dedupe_key
                )
                """
            ),
            {
                "id": uuid4(),
                "workspace_id": row["workspace_id"],
                "patient_id": row["patient_id"],
                "lead_id": row["id"],
                "assigned_user_id": row["assigned_user_id"],
                "due_at": row["next_follow_up_at"],
                "dedupe_key": f"lead-backfill:{row['id']}",
            },
        )


def downgrade() -> None:
    op.drop_table("crm_tasks")
