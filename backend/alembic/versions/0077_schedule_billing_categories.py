"""Add appointment discounts and operational service categories.

Revision ID: 0077_schedule_billing_categories
Revises: 0076_laser_device_duration
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "0077_schedule_billing_categories"
down_revision: str | Sequence[str] | None = "0076_laser_device_duration"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "appointments",
        sa.Column("discount_minor", sa.Integer(), nullable=False, server_default="0"),
    )
    op.create_check_constraint(
        "appointment_discount_non_negative",
        "appointments",
        "discount_minor >= 0",
    )

    op.add_column(
        "services",
        sa.Column(
            "operational_category",
            sa.String(length=20),
            nullable=False,
            server_default="dermatology",
        ),
    )
    op.execute(
        sa.text(
            """
            UPDATE services
            SET operational_category = CASE
                WHEN requires_laser_device
                  OR lower(coalesce(category, '')) LIKE '%laser%'
                    THEN 'laser'
                WHEN lower(coalesce(category, '')) LIKE '%slim%'
                  OR lower(coalesce(category, '')) LIKE '%weight%'
                  OR lower(coalesce(category, '')) LIKE '%body contour%'
                    THEN 'slimming'
                ELSE 'dermatology'
            END
            """
        )
    )
    op.create_check_constraint(
        "service_operational_category_valid",
        "services",
        "operational_category IN ('laser', 'dermatology', 'slimming')",
    )

    op.create_table(
        "doctor_service_categories",
        sa.Column("workspace_id", sa.Uuid(), nullable=False),
        sa.Column("doctor_id", sa.Uuid(), nullable=False),
        sa.Column("category", sa.String(length=20), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.CheckConstraint(
            "category IN ('laser', 'dermatology', 'slimming')",
            name="doctor_service_category_valid",
        ),
        sa.ForeignKeyConstraint(
            ["workspace_id", "doctor_id"],
            ["doctors.workspace_id", "doctors.id"],
            ondelete="CASCADE",
            name="fk_doctor_service_categories_doctor",
        ),
        sa.PrimaryKeyConstraint(
            "workspace_id",
            "doctor_id",
            "category",
            name="pk_doctor_service_categories",
        ),
    )
    op.execute(
        sa.text(
            """
            INSERT INTO doctor_service_categories
                (workspace_id, doctor_id, category)
            SELECT DISTINCT
                assignment.workspace_id,
                assignment.doctor_id,
                service.operational_category
            FROM doctor_services AS assignment
            JOIN services AS service
              ON service.workspace_id = assignment.workspace_id
             AND service.id = assignment.service_id
            WHERE assignment.is_active
              AND service.is_active
            ON CONFLICT DO NOTHING
            """
        )
    )


def downgrade() -> None:
    op.drop_table("doctor_service_categories")
    op.drop_constraint(
        "service_operational_category_valid",
        "services",
        type_="check",
    )
    op.drop_column("services", "operational_category")
    op.drop_constraint(
        "appointment_discount_non_negative",
        "appointments",
        type_="check",
    )
    op.drop_column("appointments", "discount_minor")
