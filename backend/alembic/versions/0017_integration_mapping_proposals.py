"""Store AI mapping proposals separately from confirmed integration mappings.

Revision ID: 0017_mapping_proposals
Revises: 0016_clinic_onboarding
Create Date: 2026-08-23
"""

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision: str = "0017_mapping_proposals"
down_revision: str | Sequence[str] | None = "0016_clinic_onboarding"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "clinic_integration_onboarding_sessions",
        sa.Column(
            "mapping_proposal",
            postgresql.JSONB(astext_type=sa.Text()),
            server_default=sa.text("'{}'::jsonb"),
            nullable=False,
        ),
    )


def downgrade() -> None:
    op.drop_column("clinic_integration_onboarding_sessions", "mapping_proposal")
