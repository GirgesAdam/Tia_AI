"""Allow ownership-suppressed outbound messages to be marked cancelled.

Revision ID: 0021_msg_cancelled
Revises: 0020_conv_ownership
Create Date: 2026-08-24
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "0021_msg_cancelled"
down_revision: str | Sequence[str] | None = "0020_conv_ownership"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.drop_constraint("message_delivery_status_valid", "messages", type_="check")
    op.create_check_constraint(
        "message_delivery_status_valid",
        "messages",
        "delivery_status IN ('received', 'queued', 'sent', 'delivered', 'read', 'failed', 'cancelled')",
    )


def downgrade() -> None:
    # A cancelled row cannot satisfy the older check constraint. Preserve the
    # fact that it was not delivered by mapping it to failed before downgrade.
    op.execute(
        sa.text(
            """
            UPDATE messages
            SET delivery_status = 'failed'
            WHERE delivery_status = 'cancelled'
            """
        )
    )
    op.drop_constraint("message_delivery_status_valid", "messages", type_="check")
    op.create_check_constraint(
        "message_delivery_status_valid",
        "messages",
        "delivery_status IN ('received', 'queued', 'sent', 'delivered', 'read', 'failed')",
    )
