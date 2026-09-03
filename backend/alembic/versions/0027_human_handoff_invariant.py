"""Repair human-owned conversations that are missing an active handoff.

Revision ID: 0027_human_handoff_invariant
Revises: 0026_appointment_reminder_6h
Create Date: 2026-08-25
"""

from collections.abc import Sequence
from uuid import uuid4

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision: str = "0027_human_handoff_invariant"
down_revision: str | Sequence[str] | None = "0026_appointment_reminder_6h"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    bind = op.get_bind()
    rows = list(
        bind.execute(
            sa.text(
                """
                SELECT
                    c.id AS conversation_id,
                    c.workspace_id,
                    c.patient_id,
                    c.assigned_user_id,
                    COALESCE(c.ownership_changed_at, c.updated_at, c.started_at, now()) AS changed_at
                FROM conversations AS c
                WHERE c.owner_type = 'human'
                  AND c.status <> 'closed'
                  AND NOT EXISTS (
                      SELECT 1
                      FROM handoff_requests AS h
                      WHERE h.workspace_id = c.workspace_id
                        AND h.conversation_id = c.id
                        AND h.status IN ('pending', 'claimed')
                  )
                """
            )
        ).mappings()
    )
    if not rows:
        return

    handoff_requests = sa.table(
        "handoff_requests",
        sa.column("id", sa.Uuid()),
        sa.column("workspace_id", sa.Uuid()),
        sa.column("conversation_id", sa.Uuid()),
        sa.column("patient_id", sa.Uuid()),
        sa.column("status", sa.String()),
        sa.column("category", sa.String()),
        sa.column("priority", sa.String()),
        sa.column("source", sa.String()),
        sa.column("reason", sa.Text()),
        sa.column("context", postgresql.JSONB()),
        sa.column("assigned_user_id", sa.Uuid()),
        sa.column("created_by_user_id", sa.Uuid()),
        sa.column("claimed_at", sa.DateTime(timezone=True)),
    )
    handoff_events = sa.table(
        "handoff_events",
        sa.column("id", sa.Uuid()),
        sa.column("workspace_id", sa.Uuid()),
        sa.column("handoff_request_id", sa.Uuid()),
        sa.column("conversation_id", sa.Uuid()),
        sa.column("event_type", sa.String()),
        sa.column("actor_type", sa.String()),
        sa.column("actor_user_id", sa.Uuid()),
        sa.column("metadata", postgresql.JSONB()),
    )

    handoff_rows: list[dict] = []
    event_rows: list[dict] = []
    for row in rows:
        handoff_id = uuid4()
        assigned_user_id = row["assigned_user_id"]
        status = "claimed" if assigned_user_id is not None else "pending"
        context = {
            "trigger": "ownership_invariant_repair",
            "migration": revision,
        }
        handoff_rows.append(
            {
                "id": handoff_id,
                "workspace_id": row["workspace_id"],
                "conversation_id": row["conversation_id"],
                "patient_id": row["patient_id"],
                "status": status,
                "category": "other",
                "priority": "normal",
                "source": "system",
                "reason": "Recovered a human-owned conversation that had no active handoff.",
                "context": context,
                "assigned_user_id": assigned_user_id,
                "created_by_user_id": None,
                "claimed_at": row["changed_at"] if assigned_user_id is not None else None,
            }
        )
        event_rows.append(
            {
                "id": uuid4(),
                "workspace_id": row["workspace_id"],
                "handoff_request_id": handoff_id,
                "conversation_id": row["conversation_id"],
                "event_type": "created",
                "actor_type": "system",
                "actor_user_id": None,
                "metadata": {
                    "repair": True,
                    "migration": revision,
                    "status": status,
                },
            }
        )
        if assigned_user_id is not None:
            event_rows.append(
                {
                    "id": uuid4(),
                    "workspace_id": row["workspace_id"],
                    "handoff_request_id": handoff_id,
                    "conversation_id": row["conversation_id"],
                    "event_type": "assigned",
                    "actor_type": "system",
                    "actor_user_id": None,
                    "metadata": {
                        "repair": True,
                        "migration": revision,
                        "assigned_user_id": str(assigned_user_id),
                    },
                }
            )

    op.bulk_insert(handoff_requests, handoff_rows)
    op.bulk_insert(handoff_events, event_rows)


def downgrade() -> None:
    # Repair rows represent real ownership state once materialized. Removing
    # them on downgrade would recreate the broken human-without-handoff state.
    pass
