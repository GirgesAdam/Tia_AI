"""Allow requirement selection audit events in conversation flows.

Revision ID: 0014_flow_requirement_selected
Revises: 0013_ai_onboarding_sessions
Create Date: 2026-08-19
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "0014_flow_requirement_selected"
down_revision: str | Sequence[str] | None = "0013_ai_onboarding_sessions"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_CONSTRAINT_NAME = "ck_conversation_flow_events_conversation_flow_event_type_valid"

_BASE_EVENT_TYPES = (
    "started",
    "updated",
    "options_presented",
    "write_authorized",
    "write_completed",
    "completed",
    "cancelled",
    "interrupted",
    "expired",
    "conflict",
)

_UPGRADED_EVENT_TYPES = (
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
    # Preserve audit meaning before restoring the older constraint. A database that
    # already contains requirement_selected rows cannot accept the old constraint
    # until those rows are mapped back to the legacy generic event type.
    op.execute(
        sa.text(
            """
            UPDATE conversation_flow_events
            SET event_type = 'updated',
                metadata = COALESCE(metadata, '{}'::jsonb)
                    || jsonb_build_object(
                        'downgraded_from_event_type', 'requirement_selected'
                    ),
                updated_at = now()
            WHERE event_type = 'requirement_selected'
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
        _check_sql(_BASE_EVENT_TYPES),
    )
