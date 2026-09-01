"""Extend clinic integration entity links for payment transactions.

Revision ID: 0030_external_system_contract
Revises: 0029_payment_ledger
Create Date: 2026-08-25
"""

from collections.abc import Sequence

from alembic import op

revision: str = "0030_external_system_contract"
down_revision: str | Sequence[str] | None = "0029_payment_ledger"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


_CONSTRAINT = "clinic_integration_entity_link_type_valid"
_TABLE = "clinic_integration_entity_links"


def upgrade() -> None:
    op.drop_constraint(_CONSTRAINT, _TABLE, type_="check")
    op.create_check_constraint(
        _CONSTRAINT,
        _TABLE,
        "entity_type IN ('service', 'branch', 'doctor', 'patient', 'appointment', 'payment')",
    )


def downgrade() -> None:
    # Downgrade is intentionally fail-closed when payment links exist. PostgreSQL
    # will reject recreating the narrower constraint until those rows are removed.
    op.drop_constraint(_CONSTRAINT, _TABLE, type_="check")
    op.create_check_constraint(
        _CONSTRAINT,
        _TABLE,
        "entity_type IN ('service', 'branch', 'doctor', 'patient', 'appointment')",
    )
