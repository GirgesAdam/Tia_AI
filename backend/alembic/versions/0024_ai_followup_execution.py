"""Make CRM follow-ups executable by Tia through the automation worker.

Revision ID: 0024_ai_followup_execution
Revises: 0023_crm_followup_tasks
Create Date: 2026-08-25
"""

from collections.abc import Sequence
from uuid import uuid4

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision: str = "0024_ai_followup_execution"
down_revision: str | Sequence[str] | None = "0023_crm_followup_tasks"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "crm_tasks",
        sa.Column("execution_mode", sa.String(length=16), server_default="human", nullable=False),
    )
    op.create_check_constraint(
        "crm_task_execution_mode_valid",
        "crm_tasks",
        "execution_mode IN ('human', 'ai')",
    )

    # Tasks created by Tia in v0.31.0 were intended as follow-ups but still had
    # to be carried out by staff. Preserve them and make them executable by Tia.
    op.execute(
        sa.text(
            """
            UPDATE crm_tasks
            SET execution_mode = 'ai'
            WHERE source = 'ai'
              AND task_type = 'follow_up'
              AND status IN ('pending', 'in_progress')
            """
        )
    )

    op.add_column(
        "automation_jobs",
        sa.Column(
            "job_kind",
            sa.String(length=24),
            server_default="appointment_rule",
            nullable=False,
        ),
    )
    op.add_column("automation_jobs", sa.Column("crm_task_id", sa.Uuid(), nullable=True))
    op.create_foreign_key(
        "fk_automation_jobs_crm_task",
        "automation_jobs",
        "crm_tasks",
        ["workspace_id", "crm_task_id"],
        ["workspace_id", "id"],
        ondelete="CASCADE",
    )
    op.create_index(
        "ix_automation_jobs_crm_task",
        "automation_jobs",
        ["crm_task_id", "status"],
    )

    op.alter_column("automation_jobs", "rule_id", existing_type=sa.Uuid(), nullable=True)
    op.alter_column("automation_jobs", "appointment_id", existing_type=sa.Uuid(), nullable=True)
    op.create_check_constraint(
        "automation_job_kind_valid",
        "automation_jobs",
        "job_kind IN ('appointment_rule', 'crm_follow_up')",
    )
    op.create_check_constraint(
        "automation_job_target_valid",
        "automation_jobs",
        "(job_kind = 'appointment_rule' AND rule_id IS NOT NULL AND appointment_id IS NOT NULL AND crm_task_id IS NULL) "
        "OR (job_kind = 'crm_follow_up' AND rule_id IS NULL AND appointment_id IS NULL AND crm_task_id IS NOT NULL)",
    )

    # Materialize jobs for active AI follow-ups created before this migration.
    # Generate UUIDs in Python so this migration does not depend on a PostgreSQL
    # UUID extension being enabled in a clinic environment.
    bind = op.get_bind()
    task_rows = bind.execute(
        sa.text(
            """
            SELECT t.id, t.workspace_id, t.patient_id, t.due_at
            FROM crm_tasks t
            WHERE t.execution_mode = 'ai'
              AND t.task_type = 'follow_up'
              AND t.status IN ('pending', 'in_progress')
              AND NOT EXISTS (
                  SELECT 1
                  FROM automation_jobs j
                  WHERE j.workspace_id = t.workspace_id
                    AND j.dedupe_key = 'crm-followup:' || t.id::text
              )
            """
        )
    ).mappings().all()
    jobs_table = sa.table(
        "automation_jobs",
        sa.column("id", sa.Uuid()),
        sa.column("workspace_id", sa.Uuid()),
        sa.column("rule_id", sa.Uuid()),
        sa.column("appointment_id", sa.Uuid()),
        sa.column("crm_task_id", sa.Uuid()),
        sa.column("patient_id", sa.Uuid()),
        sa.column("job_kind", sa.String()),
        sa.column("status", sa.String()),
        sa.column("scheduled_for", sa.DateTime(timezone=True)),
        sa.column("dedupe_key", sa.String()),
        sa.column("attempts", sa.Integer()),
        sa.column("payload", postgresql.JSONB()),
        sa.column("result", postgresql.JSONB()),
    )
    if task_rows:
        op.bulk_insert(
            jobs_table,
            [
                {
                    "id": uuid4(),
                    "workspace_id": row["workspace_id"],
                    "rule_id": None,
                    "appointment_id": None,
                    "crm_task_id": row["id"],
                    "patient_id": row["patient_id"],
                    "job_kind": "crm_follow_up",
                    "status": "queued",
                    "scheduled_for": row["due_at"],
                    "dedupe_key": f"crm-followup:{row['id']}",
                    "attempts": 0,
                    "payload": {"crm_task_id": str(row["id"])},
                    "result": {},
                }
                for row in task_rows
            ],
        )


def downgrade() -> None:
    op.execute(sa.text("DELETE FROM automation_jobs WHERE job_kind = 'crm_follow_up'"))
    op.drop_constraint("automation_job_target_valid", "automation_jobs", type_="check")
    op.drop_constraint("automation_job_kind_valid", "automation_jobs", type_="check")
    op.drop_index("ix_automation_jobs_crm_task", table_name="automation_jobs")
    op.drop_constraint("fk_automation_jobs_crm_task", "automation_jobs", type_="foreignkey")
    op.drop_column("automation_jobs", "crm_task_id")
    op.drop_column("automation_jobs", "job_kind")
    op.alter_column("automation_jobs", "appointment_id", existing_type=sa.Uuid(), nullable=False)
    op.alter_column("automation_jobs", "rule_id", existing_type=sa.Uuid(), nullable=False)
    op.drop_constraint("crm_task_execution_mode_valid", "crm_tasks", type_="check")
    op.drop_column("crm_tasks", "execution_mode")
