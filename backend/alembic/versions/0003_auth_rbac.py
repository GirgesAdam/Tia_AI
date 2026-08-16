"""Supabase Auth mapping, workspace RBAC, and public-schema RLS hardening.

Revision ID: 0003_auth_rbac
Revises: 0002_clinic_core
Create Date: 2026-08-12
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0003_auth_rbac"
down_revision: Union[str, Sequence[str], None] = "0002_clinic_core"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

PUBLIC_TABLES = (
    "users",
    "workspaces",
    "workspace_members",
    "branches",
    "staff",
    "services",
    "doctors",
    "doctor_branches",
    "doctor_services",
    "branch_working_hours",
    "doctor_working_hours",
    "booking_settings",
)


def upgrade() -> None:
    op.add_column("users", sa.Column("auth_user_id", sa.Uuid(), nullable=True))
    op.create_index("ix_users_auth_user_id", "users", ["auth_user_id"], unique=True)

    op.create_check_constraint(
        op.f("ck_workspace_members_role"),
        "workspace_members",
        "role IN ('owner', 'admin', 'member')",
    )

    # These tables are deliberately backend-only for now. The FastAPI backend connects
    # directly to Postgres and enforces workspace membership. We enable RLS and revoke
    # Data API privileges so browser clients cannot bypass FastAPI authorization.
    for table in PUBLIC_TABLES:
        op.execute(sa.text(f'ALTER TABLE public."{table}" ENABLE ROW LEVEL SECURITY'))
        op.execute(sa.text(f'REVOKE ALL ON TABLE public."{table}" FROM anon, authenticated'))


def downgrade() -> None:
    for table in PUBLIC_TABLES:
        op.execute(sa.text(f'ALTER TABLE public."{table}" DISABLE ROW LEVEL SECURITY'))

    op.drop_constraint(op.f("ck_workspace_members_role"), "workspace_members", type_="check")
    op.drop_index("ix_users_auth_user_id", table_name="users")
    op.drop_column("users", "auth_user_id")
