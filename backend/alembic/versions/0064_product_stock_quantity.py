"""Track current clinic product stock.

Revision ID: 0064_product_stock_quantity
Revises: 0063_retire_booking_confirmation
Create Date: 2026-09-09
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "0064_product_stock_quantity"
down_revision: str | Sequence[str] | None = "0063_retire_booking_confirmation"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "clinic_products",
        sa.Column("quantity_on_hand", sa.Integer(), server_default="0", nullable=False),
    )
    op.create_check_constraint(
        "clinic_product_quantity_non_negative",
        "clinic_products",
        "quantity_on_hand >= 0",
    )


def downgrade() -> None:
    op.drop_constraint("clinic_product_quantity_non_negative", "clinic_products", type_="check")
    op.drop_column("clinic_products", "quantity_on_hand")
