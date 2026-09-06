"""Recognize the legacy clinic-expenses revision.

Revision ID: 0054_clinic_expenses
Revises: 0053_public_table_rls_completion
Create Date: 2026-09-06

Some existing non-production databases were migrated with the historical
``0054_clinic_expenses`` revision before the finance schema was consolidated
into ``0054_core_expenses``. Keeping this no-op compatibility node lets
Alembic traverse those databases without rewriting their version table.
The merge revision migrates any legacy expense rows into the canonical table.
"""

from collections.abc import Sequence

revision: str = "0054_clinic_expenses"
down_revision: str | Sequence[str] | None = "0053_public_table_rls_completion"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    pass


def downgrade() -> None:
    pass
