"""Add explicit source authority policy for clinic integrations.

Revision ID: 0033_sync_authority
Revises: 0032_external_sync_engine
Create Date: 2026-08-26
"""

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision: str = "0033_sync_authority"
down_revision: str | Sequence[str] | None = "0032_external_sync_engine"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


_TIA_POLICY = (
    '{"patients":{"owner":"tia","fields":{}},'
    '"payments":{"owner":"tia","fields":{}},'
    '"appointments":{"owner":"tia","fields":{}}}'
)
_EXTERNAL_POLICY = (
    '{"patients":{"owner":"external","fields":{}},'
    '"payments":{"owner":"external","fields":{}},'
    '"appointments":{"owner":"tia","fields":{}}}'
)


def upgrade() -> None:
    op.add_column(
        "clinic_integrations",
        sa.Column(
            "authority_policy",
            postgresql.JSONB(astext_type=sa.Text()),
            server_default=sa.text("'{}'::jsonb"),
            nullable=False,
        ),
    )
    op.execute(
        sa.text(
            """
            UPDATE clinic_integrations
            SET authority_policy = CAST(:external_policy AS jsonb)
            WHERE mode IN ('external_api', 'hybrid')
            """
        ).bindparams(external_policy=_EXTERNAL_POLICY)
    )
    op.execute(
        sa.text(
            """
            UPDATE clinic_integrations
            SET authority_policy = CAST(:tia_policy AS jsonb)
            WHERE mode NOT IN ('external_api', 'hybrid')
            """
        ).bindparams(tia_policy=_TIA_POLICY)
    )


def downgrade() -> None:
    op.drop_column("clinic_integrations", "authority_policy")
