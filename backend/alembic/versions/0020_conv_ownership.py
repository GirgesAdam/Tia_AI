"""Add first-class conversation ownership and unread state.

Revision ID: 0020_conv_ownership
Revises: 0019_appt_payments
Create Date: 2026-08-24
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "0020_conv_ownership"
down_revision: str | Sequence[str] | None = "0019_appt_payments"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "conversations",
        sa.Column("owner_type", sa.String(length=16), server_default="ai", nullable=False),
    )
    op.add_column(
        "conversations",
        sa.Column("unread_count", sa.Integer(), server_default="0", nullable=False),
    )
    op.add_column(
        "conversations",
        sa.Column(
            "ownership_changed_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
    )

    # Preserve the existing handoff semantics. Conversations that were already
    # pending/assigned or have an active handoff must start as human-owned.
    op.execute(
        sa.text(
            """
            UPDATE conversations AS c
            SET owner_type = 'human',
                ownership_changed_at = COALESCE(c.updated_at, c.started_at, now())
            WHERE c.status = 'pending'
               OR c.assigned_user_id IS NOT NULL
               OR EXISTS (
                    SELECT 1
                    FROM handoff_requests AS h
                    WHERE h.workspace_id = c.workspace_id
                      AND h.conversation_id = c.id
                      AND h.status IN ('pending', 'claimed')
               )
            """
        )
    )
    op.execute(
        sa.text(
            """
            UPDATE conversations AS c
            SET ownership_changed_at = COALESCE(c.updated_at, c.started_at, now())
            WHERE c.owner_type = 'ai'
            """
        )
    )

    op.create_check_constraint(
        "conversation_owner_type_valid",
        "conversations",
        "owner_type IN ('ai', 'human')",
    )
    op.create_check_constraint(
        "conversation_unread_count_non_negative",
        "conversations",
        "unread_count >= 0",
    )
    op.create_index(
        "ix_conversations_workspace_owner_status",
        "conversations",
        ["workspace_id", "owner_type", "status", "last_message_at"],
    )


def downgrade() -> None:
    op.drop_index("ix_conversations_workspace_owner_status", table_name="conversations")
    op.drop_constraint(
        "conversation_unread_count_non_negative",
        "conversations",
        type_="check",
    )
    op.drop_constraint("conversation_owner_type_valid", "conversations", type_="check")
    op.drop_column("conversations", "ownership_changed_at")
    op.drop_column("conversations", "unread_count")
    op.drop_column("conversations", "owner_type")
