"""Add billing-only additional services to appointments.

Revision ID: 0073_appointment_additional_services
Revises: 0072_workspace_demo_policy
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "0073_appointment_additional_services"
down_revision: str | Sequence[str] | None = "0072_workspace_demo_policy"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "appointment_additional_services",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("workspace_id", sa.Uuid(), nullable=False),
        sa.Column("appointment_id", sa.Uuid(), nullable=False),
        sa.Column("service_id", sa.Uuid(), nullable=False),
        sa.Column("service_name", sa.String(length=200), nullable=False),
        sa.Column("unit_price_minor", sa.Integer(), nullable=False),
        sa.Column("currency", sa.String(length=3), server_default="EGP", nullable=False),
        sa.Column("laser_device_key", sa.String(length=40), nullable=True),
        sa.Column("laser_device_name", sa.String(length=120), nullable=True),
        sa.Column("created_by_user_id", sa.Uuid(), nullable=True),
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
            "unit_price_minor >= 0",
            name="appointment_additional_service_price_non_negative",
        ),
        sa.CheckConstraint(
            "laser_device_key IS NULL OR "
            "laser_device_key IN ('prime_lase', 'candela_gentle')",
            name="appointment_additional_service_device_valid",
        ),
        sa.ForeignKeyConstraint(
            ["workspace_id", "appointment_id"],
            ["appointments.workspace_id", "appointments.id"],
            ondelete="CASCADE",
            name="fk_appointment_additional_services_appointment",
        ),
        sa.ForeignKeyConstraint(
            ["workspace_id", "service_id"],
            ["services.workspace_id", "services.id"],
            ondelete="RESTRICT",
            name="fk_appointment_additional_services_service",
        ),
        sa.ForeignKeyConstraint(
            ["created_by_user_id"], ["users.id"], ondelete="SET NULL"
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "workspace_id",
            "id",
            name="uq_appointment_additional_services_workspace_id_id",
        ),
        sa.UniqueConstraint(
            "workspace_id",
            "appointment_id",
            "service_id",
            name="uq_appointment_additional_services_appointment_service",
        ),
    )
    op.create_index(
        "ix_appointment_additional_services_workspace_appointment",
        "appointment_additional_services",
        ["workspace_id", "appointment_id"],
    )
    op.create_index(
        "ix_appointment_additional_services_service_id",
        "appointment_additional_services",
        ["service_id"],
    )
    op.execute(
        sa.text(
            "ALTER TABLE public.appointment_additional_services "
            "ENABLE ROW LEVEL SECURITY"
        )
    )
    op.execute(
        sa.text(
            "REVOKE ALL ON TABLE public.appointment_additional_services "
            "FROM anon, authenticated"
        )
    )


def downgrade() -> None:
    op.drop_table("appointment_additional_services")
