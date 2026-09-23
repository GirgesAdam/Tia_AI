"""Support pulse billing for appointment additional services.

Revision ID: 0084_extra_service_pulses
Revises: 0083_pulse_device_pricing
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision: str = "0084_extra_service_pulses"
down_revision: str | Sequence[str] | None = "0083_pulse_device_pricing"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "appointment_additional_services",
        sa.Column(
            "billing_context",
            sa.String(length=24),
            nullable=False,
            server_default="standard",
        ),
    )
    op.add_column(
        "appointment_additional_services",
        sa.Column("laser_pulses_used", sa.Integer(), nullable=True),
    )
    op.add_column(
        "appointment_additional_services",
        sa.Column("pulse_resolution", sa.String(length=16), nullable=True),
    )
    op.add_column(
        "appointment_additional_services",
        sa.Column(
            "pulse_resolution_pulse_pack_id",
            postgresql.UUID(as_uuid=True),
            nullable=True,
        ),
    )
    op.add_column(
        "appointment_additional_services",
        sa.Column("pulse_overage_unit_price_minor", sa.Integer(), nullable=True),
    )
    op.add_column(
        "appointment_additional_services",
        sa.Column(
            "pulse_overage_charge_minor",
            sa.Integer(),
            nullable=False,
            server_default="0",
        ),
    )
    op.execute(
        """
        UPDATE appointment_additional_services
        SET billing_context = 'package_prepaid'
        WHERE patient_package_id IS NOT NULL
        """
    )
    op.create_check_constraint(
        "appointment_additional_service_billing_context_valid",
        "appointment_additional_services",
        "billing_context IN ('standard', 'package_prepaid', 'pulse_prepaid')",
    )
    op.create_check_constraint(
        "appointment_additional_service_pulses_non_negative",
        "appointment_additional_services",
        "laser_pulses_used IS NULL OR laser_pulses_used >= 0",
    )
    op.create_check_constraint(
        "appointment_additional_service_pulse_resolution_valid",
        "appointment_additional_services",
        "pulse_resolution IS NULL OR pulse_resolution IN ('balance', 'new_pack', 'overage')",
    )
    op.create_check_constraint(
        "appointment_additional_service_pulse_overage_price_positive",
        "appointment_additional_services",
        "pulse_overage_unit_price_minor IS NULL OR pulse_overage_unit_price_minor > 0",
    )
    op.create_check_constraint(
        "appointment_additional_service_pulse_overage_non_negative",
        "appointment_additional_services",
        "pulse_overage_charge_minor >= 0",
    )
    op.create_foreign_key(
        "fk_additional_service_pulse_resolution_pack",
        "appointment_additional_services",
        "patient_pulse_packs",
        ["workspace_id", "pulse_resolution_pulse_pack_id"],
        ["workspace_id", "id"],
        ondelete="RESTRICT",
    )
    op.create_index(
        "ix_additional_service_pulse_resolution_pack",
        "appointment_additional_services",
        ["pulse_resolution_pulse_pack_id"],
    )

    op.add_column(
        "pulse_usages",
        sa.Column(
            "appointment_additional_service_id",
            postgresql.UUID(as_uuid=True),
            nullable=True,
        ),
    )
    op.create_foreign_key(
        "fk_pulse_usages_additional_service",
        "pulse_usages",
        "appointment_additional_services",
        ["workspace_id", "appointment_additional_service_id"],
        ["workspace_id", "id"],
        ondelete="RESTRICT",
    )
    op.create_index(
        "ix_pulse_usages_workspace_additional_service",
        "pulse_usages",
        ["workspace_id", "appointment_additional_service_id"],
    )


def downgrade() -> None:
    op.drop_index(
        "ix_pulse_usages_workspace_additional_service",
        table_name="pulse_usages",
    )
    op.drop_constraint(
        "fk_pulse_usages_additional_service",
        "pulse_usages",
        type_="foreignkey",
    )
    op.drop_column("pulse_usages", "appointment_additional_service_id")

    op.drop_index(
        "ix_additional_service_pulse_resolution_pack",
        table_name="appointment_additional_services",
    )
    op.drop_constraint(
        "fk_additional_service_pulse_resolution_pack",
        "appointment_additional_services",
        type_="foreignkey",
    )
    op.drop_constraint(
        "appointment_additional_service_pulse_overage_non_negative",
        "appointment_additional_services",
        type_="check",
    )
    op.drop_constraint(
        "appointment_additional_service_pulse_overage_price_positive",
        "appointment_additional_services",
        type_="check",
    )
    op.drop_constraint(
        "appointment_additional_service_pulse_resolution_valid",
        "appointment_additional_services",
        type_="check",
    )
    op.drop_constraint(
        "appointment_additional_service_pulses_non_negative",
        "appointment_additional_services",
        type_="check",
    )
    op.drop_constraint(
        "appointment_additional_service_billing_context_valid",
        "appointment_additional_services",
        type_="check",
    )
    op.drop_column("appointment_additional_services", "pulse_overage_charge_minor")
    op.drop_column("appointment_additional_services", "pulse_overage_unit_price_minor")
    op.drop_column("appointment_additional_services", "pulse_resolution_pulse_pack_id")
    op.drop_column("appointment_additional_services", "pulse_resolution")
    op.drop_column("appointment_additional_services", "laser_pulses_used")
    op.drop_column("appointment_additional_services", "billing_context")
