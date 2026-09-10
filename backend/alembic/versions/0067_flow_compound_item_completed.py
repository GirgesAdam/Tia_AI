"""Allow compound item completion audit events in conversation flows.

Revision ID: 0067_flow_compound_item_completed
Revises: 0066_clinic_knowledge_entries
Create Date: 2026-09-10
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "0067_flow_compound_item_completed"
down_revision: str | Sequence[str] | None = "0066_clinic_knowledge_entries"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_CONSTRAINT_NAME = "ck_conversation_flow_events_conversation_flow_event_type_valid"

_PREVIOUS_EVENT_TYPES = (
    "started",
    "updated",
    "options_presented",
    "requirement_selected",
    "write_authorized",
    "write_completed",
    "completed",
    "cancelled",
    "interrupted",
    "expired",
    "conflict",
)

_UPGRADED_EVENT_TYPES = (*_PREVIOUS_EVENT_TYPES, "compound_item_completed")


def _check_sql(values: tuple[str, ...]) -> str:
    quoted = ", ".join(f"'{value}'" for value in values)
    return f"event_type IN ({quoted})"


def upgrade() -> None:
    op.drop_constraint(
        op.f(_CONSTRAINT_NAME),
        "conversation_flow_events",
        type_="check",
    )
    op.create_check_constraint(
        op.f(_CONSTRAINT_NAME),
        "conversation_flow_events",
        _check_sql(_UPGRADED_EVENT_TYPES),
    )


def downgrade() -> None:
    op.execute(
        sa.text(
            """
            UPDATE conversation_flow_events
            SET event_type = 'updated',
                metadata = COALESCE(metadata, '{}'::jsonb)
                    || jsonb_build_object(
                        'downgraded_from_event_type', 'compound_item_completed'
                    ),
                updated_at = now()
            WHERE event_type = 'compound_item_completed'
            """
        )
    )
    op.drop_constraint(
        op.f(_CONSTRAINT_NAME),
        "conversation_flow_events",
        type_="check",
    )
    op.create_check_constraint(
        op.f(_CONSTRAINT_NAME),
        "conversation_flow_events",
        _check_sql(_PREVIOUS_EVENT_TYPES),
    )
