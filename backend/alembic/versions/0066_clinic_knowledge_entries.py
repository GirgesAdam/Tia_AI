"""Add structured clinic knowledge entries.

Revision ID: 0066_clinic_knowledge_entries
Revises: 0065_laser_package_offers
Create Date: 2026-09-10
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "0066_clinic_knowledge_entries"
down_revision: str | Sequence[str] | None = "0065_laser_package_offers"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "clinic_knowledge_entries",
        sa.Column("workspace_id", sa.Uuid(), nullable=False),
        sa.Column("scope_type", sa.String(length=24), nullable=False),
        sa.Column("service_id", sa.Uuid(), nullable=True),
        sa.Column("device_key", sa.String(length=40), nullable=True),
        sa.Column("title", sa.String(length=200), nullable=False),
        sa.Column("content", sa.Text(), nullable=False),
        sa.Column("sort_order", sa.Integer(), server_default="0", nullable=False),
        sa.Column("is_active", sa.Boolean(), server_default=sa.text("true"), nullable=False),
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.CheckConstraint(
            "scope_type IN ('clinic', 'service', 'laser_device')",
            name="clinic_knowledge_scope_valid",
        ),
        sa.CheckConstraint(
            "(scope_type = 'clinic' AND service_id IS NULL AND device_key IS NULL) OR "
            "(scope_type = 'service' AND service_id IS NOT NULL AND device_key IS NULL) OR "
            "(scope_type = 'laser_device' AND service_id IS NULL AND device_key IS NOT NULL)",
            name="clinic_knowledge_scope_fields_valid",
        ),
        sa.ForeignKeyConstraint(["workspace_id"], ["workspaces.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(
            ["workspace_id", "service_id"],
            ["services.workspace_id", "services.id"],
            name="fk_clinic_knowledge_entries_service",
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name="pk_clinic_knowledge_entries"),
    )
    op.create_index("ix_clinic_knowledge_entries_workspace_id", "clinic_knowledge_entries", ["workspace_id"])
    op.create_index("ix_clinic_knowledge_entries_scope_type", "clinic_knowledge_entries", ["scope_type"])
    op.create_index("ix_clinic_knowledge_entries_service_id", "clinic_knowledge_entries", ["service_id"])
    op.create_index("ix_clinic_knowledge_entries_device_key", "clinic_knowledge_entries", ["device_key"])


def downgrade() -> None:
    op.drop_index("ix_clinic_knowledge_entries_device_key", table_name="clinic_knowledge_entries")
    op.drop_index("ix_clinic_knowledge_entries_service_id", table_name="clinic_knowledge_entries")
    op.drop_index("ix_clinic_knowledge_entries_scope_type", table_name="clinic_knowledge_entries")
    op.drop_index("ix_clinic_knowledge_entries_workspace_id", table_name="clinic_knowledge_entries")
    op.drop_table("clinic_knowledge_entries")
