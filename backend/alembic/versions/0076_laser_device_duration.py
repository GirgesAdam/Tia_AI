"""Store laser service duration per device.

Revision ID: 0076_laser_device_duration
Revises: 0075_visit_package_billing
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "0076_laser_device_duration"
down_revision: str | Sequence[str] | None = "0075_visit_package_billing"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "service_device_prices",
        sa.Column("duration_minutes", sa.Integer(), nullable=True),
    )
    op.execute(
        sa.text(
            """
            UPDATE service_device_prices AS device
            SET duration_minutes = service.duration_minutes
            FROM services AS service
            WHERE service.workspace_id = device.workspace_id
              AND service.id = device.service_id
              AND device.duration_minutes IS NULL
            """
        )
    )
    op.alter_column(
        "service_device_prices",
        "duration_minutes",
        existing_type=sa.Integer(),
        nullable=False,
    )
    op.create_check_constraint(
        "service_device_price_duration_valid",
        "service_device_prices",
        "duration_minutes > 0 AND duration_minutes <= 1440",
    )


def downgrade() -> None:
    op.drop_constraint(
        "service_device_price_duration_valid",
        "service_device_prices",
        type_="check",
    )
    op.drop_column("service_device_prices", "duration_minutes")
