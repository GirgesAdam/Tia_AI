"""Persist bounded handoff intelligence context and escalation audit events.

Revision ID: 0022_handoff_intelligence
Revises: 0021_msg_cancelled
Create Date: 2026-08-24
"""

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision: str = "0022_handoff_intelligence"
down_revision: str | Sequence[str] | None = "0021_msg_cancelled"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "handoff_requests",
        sa.Column(
            "context",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
            server_default=sa.text("'{}'::jsonb"),
        ),
    )

    op.drop_constraint("handoff_event_type_valid", "handoff_events", type_="check")
    op.create_check_constraint(
        "handoff_event_type_valid",
        "handoff_events",
        "event_type IN ('created', 'escalated', 'claimed', 'assigned', "
        "'staff_replied', 'resolved', 'reopened')",
    )


def downgrade() -> None:
    # Preserve the audit row while mapping the newer event label to an older
    # event type that satisfies the pre-4.5 check constraint.
    op.execute(
        sa.text(
            """
            UPDATE handoff_events
            SET event_type = 'created'
            WHERE event_type = 'escalated'
            """
        )
    )
    op.drop_constraint("handoff_event_type_valid", "handoff_events", type_="check")
    op.create_check_constraint(
        "handoff_event_type_valid",
        "handoff_events",
        "event_type IN ('created', 'claimed', 'assigned', 'staff_replied', "
        "'resolved', 'reopened')",
    )
    op.drop_column("handoff_requests", "context")
