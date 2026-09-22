"""Add billing discounts and canonical service/doctor categories.

Revision ID: 0077_schedule_billing_categories
Revises: 0076_laser_device_duration
"""

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

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

    op.execute(
        sa.text(
            """
            UPDATE services
            SET category = CASE
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
    op.alter_column(
        "services",
        "category",
        existing_type=sa.String(length=120),
        nullable=False,
        server_default="dermatology",
    )
    op.create_check_constraint(
        "service_category_valid",
        "services",
        "category IN ('laser', 'dermatology', 'slimming')",
    )

    op.add_column(
        "doctors",
        sa.Column(
            "service_categories",
            postgresql.ARRAY(sa.String(length=20)),
            nullable=False,
            server_default=sa.text("'{}'::varchar[]"),
        ),
    )
    op.execute(
        sa.text(
            """
            UPDATE doctors AS doctor
            SET service_categories = COALESCE(
                (
                    SELECT array_agg(DISTINCT service.category ORDER BY service.category)
                    FROM doctor_services AS assignment
                    JOIN services AS service
                      ON service.workspace_id = assignment.workspace_id
                     AND service.id = assignment.service_id
                    WHERE assignment.workspace_id = doctor.workspace_id
                      AND assignment.doctor_id = doctor.id
                      AND assignment.is_active
                      AND service.is_active
                ),
                ARRAY[]::varchar[]
            )
            """
        )
    )


def downgrade() -> None:
    op.drop_column("doctors", "service_categories")
    op.drop_constraint("service_category_valid", "services", type_="check")
    op.alter_column(
        "services",
        "category",
        existing_type=sa.String(length=120),
        nullable=True,
        server_default=None,
    )
    op.drop_constraint(
        "appointment_discount_non_negative",
        "appointments",
        type_="check",
    )
    op.drop_column("appointments", "discount_minor")
