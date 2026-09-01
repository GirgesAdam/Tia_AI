"""Repair historical payment reference check constraints.

Revision ID: 0052_payment_reference_constraint_repair
Revises: 0051_clinic_setup_v2
Create Date: 2026-09-01
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0052_payment_reference_constraint_repair"
down_revision: str | Sequence[str] | None = "0051_clinic_setup_v2"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def _drop_reference_checks() -> None:
    """Drop every legacy CHECK that constrains reference_transaction_id.

    Patch-era databases have carried several physical names for the same
    logical check because older migrations supplied an already-prefixed name
    while SQLAlchemy's naming convention prefixed it again. PostgreSQL then
    truncated the doubled name and appended a hash. Looking up by expression
    makes the repair independent of those historical physical names.
    """

    op.execute(
        sa.text(
            r"""
DO $$
DECLARE
    constraint_row record;
BEGIN
    FOR constraint_row IN
        SELECT con.conname
        FROM pg_constraint AS con
        JOIN pg_class AS rel ON rel.oid = con.conrelid
        JOIN pg_namespace AS nsp ON nsp.oid = rel.relnamespace
        WHERE con.contype = 'c'
          AND rel.relname = 'payment_transactions'
          AND nsp.nspname = current_schema()
          AND pg_get_constraintdef(con.oid) ILIKE '%reference_transaction_id%'
    LOOP
        EXECUTE format(
            'ALTER TABLE %I.%I DROP CONSTRAINT %I',
            current_schema(),
            'payment_transactions',
            constraint_row.conname
        );
    END LOOP;
END $$;
"""
        )
    )


def _widen_alembic_version_column() -> None:
    """Allow descriptive Alembic revision IDs longer than the legacy 32 chars."""

    op.execute(
        sa.text(
            "ALTER TABLE alembic_version "
            "ALTER COLUMN version_num TYPE VARCHAR(255)"
        )
    )


def upgrade() -> None:
    # Alembic updates alembic_version only after this function returns. Widening
    # the column here therefore happens before it writes this descriptive
    # revision ID, and prevents the same failure for future long revision IDs.
    _widen_alembic_version_column()
    _drop_reference_checks()
    op.execute(
        sa.text(
            "ALTER TABLE payment_transactions "
            "ADD CONSTRAINT ck_payment_transactions_reference_valid_v2 "
            "CHECK (transaction_type = 'refund' OR reference_transaction_id IS NULL)"
        )
    )


def downgrade() -> None:
    _drop_reference_checks()
    op.execute(
        sa.text(
            "ALTER TABLE payment_transactions "
            "ADD CONSTRAINT ck_payment_transactions_reference_valid_legacy "
            "CHECK ((transaction_type = 'payment' AND reference_transaction_id IS NULL) OR "
            "(transaction_type = 'refund' AND reference_transaction_id IS NOT NULL))"
        )
    )
