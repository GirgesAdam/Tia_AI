"""Support package purchases inside multi-service visits.

Revision ID: 0075_visit_package_billing
Revises: 0074_appt_extra_services_head
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "0075_visit_package_billing"
down_revision: str | Sequence[str] | None = "0074_appt_extra_services_head"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("patient_packages", sa.Column("origin_appointment_id", sa.Uuid(), nullable=True))
    op.create_foreign_key(
        "fk_patient_packages_origin_appointment",
        "patient_packages",
        "appointments",
        ["workspace_id", "origin_appointment_id"],
        ["workspace_id", "id"],
        ondelete="RESTRICT",
    )
    op.create_index(
        "ix_patient_packages_workspace_origin_appointment",
        "patient_packages",
        ["workspace_id", "origin_appointment_id"],
    )

    op.add_column(
        "appointment_additional_services",
        sa.Column("patient_package_id", sa.Uuid(), nullable=True),
    )
    op.create_foreign_key(
        "fk_appointment_additional_services_patient_package",
        "appointment_additional_services",
        "patient_packages",
        ["workspace_id", "patient_package_id"],
        ["workspace_id", "id"],
        ondelete="RESTRICT",
    )
    op.create_index(
        "ix_appointment_additional_services_patient_package_id",
        "appointment_additional_services",
        ["patient_package_id"],
    )

    op.add_column(
        "package_usages",
        sa.Column("appointment_additional_service_id", sa.Uuid(), nullable=True),
    )
    op.create_foreign_key(
        "fk_package_usages_additional_service",
        "package_usages",
        "appointment_additional_services",
        ["workspace_id", "appointment_additional_service_id"],
        ["workspace_id", "id"],
        ondelete="CASCADE",
    )
    op.create_index(
        "ix_package_usages_appointment_additional_service_id",
        "package_usages",
        ["appointment_additional_service_id"],
    )
    op.drop_constraint(
        "uq_package_usages_workspace_appointment",
        "package_usages",
        type_="unique",
    )
    op.create_index(
        "uq_package_usages_workspace_primary_appointment",
        "package_usages",
        ["workspace_id", "appointment_id"],
        unique=True,
        postgresql_where=sa.text("appointment_additional_service_id IS NULL"),
    )
    op.create_index(
        "uq_package_usages_workspace_additional_service",
        "package_usages",
        ["workspace_id", "appointment_additional_service_id"],
        unique=True,
        postgresql_where=sa.text("appointment_additional_service_id IS NOT NULL"),
    )


def downgrade() -> None:
    op.drop_index("uq_package_usages_workspace_additional_service", table_name="package_usages")
    op.drop_index("uq_package_usages_workspace_primary_appointment", table_name="package_usages")
    op.create_unique_constraint(
        "uq_package_usages_workspace_appointment",
        "package_usages",
        ["workspace_id", "appointment_id"],
    )
    op.drop_index("ix_package_usages_appointment_additional_service_id", table_name="package_usages")
    op.drop_constraint("fk_package_usages_additional_service", "package_usages", type_="foreignkey")
    op.drop_column("package_usages", "appointment_additional_service_id")

    op.drop_index("ix_appointment_additional_services_patient_package_id", table_name="appointment_additional_services")
    op.drop_constraint(
        "fk_appointment_additional_services_patient_package",
        "appointment_additional_services",
        type_="foreignkey",
    )
    op.drop_column("appointment_additional_services", "patient_package_id")

    op.drop_index("ix_patient_packages_workspace_origin_appointment", table_name="patient_packages")
    op.drop_constraint("fk_patient_packages_origin_appointment", "patient_packages", type_="foreignkey")
    op.drop_column("patient_packages", "origin_appointment_id")
