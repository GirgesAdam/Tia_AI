"""Add workspace clinic integration configuration and external entity links.

Revision ID: 0015_clinic_integrations
Revises: 0014_flow_requirement_selected
Create Date: 2026-08-22
"""

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision: str = "0015_clinic_integrations"
down_revision: str | Sequence[str] | None = "0014_flow_requirement_selected"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "clinic_integrations",
        sa.Column("workspace_id", sa.Uuid(), nullable=False),
        sa.Column(
            "mode",
            sa.String(length=32),
            server_default="tia_native",
            nullable=False,
        ),
        sa.Column(
            "adapter_key",
            sa.String(length=80),
            server_default="tia_database",
            nullable=False,
        ),
        sa.Column(
            "status",
            sa.String(length=24),
            server_default="active",
            nullable=False,
        ),
        sa.Column("external_clinic_id", sa.String(length=255), nullable=True),
        sa.Column("secret_ref", sa.String(length=512), nullable=True),
        sa.Column(
            "config",
            postgresql.JSONB(astext_type=sa.Text()),
            server_default=sa.text("'{}'::jsonb"),
            nullable=False,
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.CheckConstraint(
            "mode IN ('tia_native', 'external_api', 'hybrid', 'imported')",
            name="clinic_integration_mode_valid",
        ),
        sa.CheckConstraint(
            "status IN ('active', 'setup_required', 'paused', 'error')",
            name="clinic_integration_status_valid",
        ),
        sa.ForeignKeyConstraint(
            ["workspace_id"],
            ["workspaces.id"],
            ondelete="CASCADE",
            name="fk_clinic_integrations_workspace",
        ),
        sa.PrimaryKeyConstraint("workspace_id", name="pk_clinic_integrations"),
    )
    op.create_index(
        "ix_clinic_integrations_adapter_status",
        "clinic_integrations",
        ["adapter_key", "status"],
    )

    # Preserve current behavior for every existing tenant. New deployments start
    # with the same Tia-native source of truth until an admin explicitly changes
    # the workspace integration configuration.
    op.execute(
        sa.text(
            """
            INSERT INTO clinic_integrations (
                workspace_id, mode, adapter_key, status, config
            )
            SELECT id, 'tia_native', 'tia_database', 'active', '{}'::jsonb
            FROM workspaces
            ON CONFLICT (workspace_id) DO NOTHING
            """
        )
    )

    op.create_table(
        "clinic_integration_entity_links",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("workspace_id", sa.Uuid(), nullable=False),
        sa.Column("entity_type", sa.String(length=32), nullable=False),
        sa.Column("canonical_id", sa.String(length=255), nullable=False),
        sa.Column("external_id", sa.String(length=512), nullable=False),
        sa.Column(
            "metadata",
            postgresql.JSONB(astext_type=sa.Text()),
            server_default=sa.text("'{}'::jsonb"),
            nullable=False,
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.CheckConstraint(
            "entity_type IN ('service', 'branch', 'doctor', 'patient', 'appointment')",
            name="clinic_integration_entity_link_type_valid",
        ),
        sa.ForeignKeyConstraint(
            ["workspace_id"],
            ["clinic_integrations.workspace_id"],
            ondelete="CASCADE",
            name="fk_clinic_integration_entity_links_workspace",
        ),
        sa.PrimaryKeyConstraint("id", name="pk_clinic_integration_entity_links"),
        sa.UniqueConstraint(
            "workspace_id",
            "entity_type",
            "canonical_id",
            name="uq_clinic_integration_entity_links_canonical",
        ),
        sa.UniqueConstraint(
            "workspace_id",
            "entity_type",
            "external_id",
            name="uq_clinic_integration_entity_links_external",
        ),
    )
    op.create_index(
        "ix_clinic_integration_entity_links_workspace_type",
        "clinic_integration_entity_links",
        ["workspace_id", "entity_type"],
    )


def downgrade() -> None:
    op.drop_index(
        "ix_clinic_integration_entity_links_workspace_type",
        table_name="clinic_integration_entity_links",
    )
    op.drop_table("clinic_integration_entity_links")
    op.drop_index(
        "ix_clinic_integrations_adapter_status",
        table_name="clinic_integrations",
    )
    op.drop_table("clinic_integrations")
