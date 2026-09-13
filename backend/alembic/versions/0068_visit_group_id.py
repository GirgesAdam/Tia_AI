"""Add grouped-visit identity to appointments.

Revision ID: 0068_visit_group_id
Revises: 0067_compound_item_completed
"""

from __future__ import annotations

from alembic import op

revision = "0068_visit_group_id"
down_revision = "0067_compound_item_completed"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Intentionally idempotent: the additive column may be staged ahead of the
    # runtime deploy so Railway never races application code against the schema.
    op.execute("ALTER TABLE appointments ADD COLUMN IF NOT EXISTS visit_group_id UUID NULL")
    op.execute(
        "CREATE INDEX IF NOT EXISTS ix_appointments_workspace_visit_group "
        "ON appointments (workspace_id, visit_group_id) "
        "WHERE visit_group_id IS NOT NULL"
    )


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS ix_appointments_workspace_visit_group")
    op.execute("ALTER TABLE appointments DROP COLUMN IF EXISTS visit_group_id")
