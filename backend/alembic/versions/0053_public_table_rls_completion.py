"""Complete RLS hardening for remaining public tables.

Revision ID: 0053_public_table_rls_completion
Revises: 0052_payment_reference_constraint_repair
Create Date: 2026-09-02
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0053_public_table_rls_completion"
down_revision: str | Sequence[str] | None = "0052_payment_reference_constraint_repair"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_TABLES = (
    "alembic_version",
    "clinic_data_issues",
    "doctor_availability_windows",
)


def upgrade() -> None:
    for table in _TABLES:
        op.execute(sa.text(f'ALTER TABLE public."{table}" ENABLE ROW LEVEL SECURITY'))
        op.execute(sa.text(f'REVOKE ALL ON TABLE public."{table}" FROM anon, authenticated'))


def downgrade() -> None:
    for table in reversed(_TABLES):
        op.execute(sa.text(f'GRANT ALL ON TABLE public."{table}" TO authenticated'))
        op.execute(sa.text(f'ALTER TABLE public."{table}" DISABLE ROW LEVEL SECURITY'))
