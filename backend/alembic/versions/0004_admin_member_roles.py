"""Reduce workspace roles to admin and member only.

Revision ID: 0004_admin_member_roles
Revises: 0003_auth_rbac
Create Date: 2026-08-12
"""

from typing import Sequence, Union

from alembic import op

revision: str = "0004_admin_member_roles"
down_revision: Union[str, Sequence[str], None] = "0003_auth_rbac"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Preserve existing access if 0003 was already applied: any legacy owner becomes admin.
    op.execute("UPDATE workspace_members SET role = 'admin' WHERE role = 'owner'")

    op.drop_constraint(
        op.f("ck_workspace_members_role"),
        "workspace_members",
        type_="check",
    )
    op.create_check_constraint(
        op.f("ck_workspace_members_role"),
        "workspace_members",
        "role IN ('admin', 'member')",
    )


def downgrade() -> None:
    op.drop_constraint(
        op.f("ck_workspace_members_role"),
        "workspace_members",
        type_="check",
    )
    op.create_check_constraint(
        op.f("ck_workspace_members_role"),
        "workspace_members",
        "role IN ('owner', 'admin', 'member')",
    )
