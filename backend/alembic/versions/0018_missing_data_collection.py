"""Store structured AI missing-data collection state.

Revision ID: 0018_missing_data
Revises: 0017_mapping_proposals
Create Date: 2026-08-23
"""

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision: str = "0018_missing_data"
down_revision: str | Sequence[str] | None = "0017_mapping_proposals"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "clinic_integration_onboarding_sessions",
        sa.Column(
            "missing_data_state",
            postgresql.JSONB(astext_type=sa.Text()),
            server_default=sa.text("'{}'::jsonb"),
            nullable=False,
        ),
    )


def downgrade() -> None:
    op.drop_column("clinic_integration_onboarding_sessions", "missing_data_state")
