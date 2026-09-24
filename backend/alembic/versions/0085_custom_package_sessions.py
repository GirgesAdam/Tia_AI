"""Allow custom positive session counts for service package offers.

Revision ID: 0085_custom_package_sessions
Revises: 0084_extra_service_pulses
Create Date: 2026-09-24
"""

from collections.abc import Sequence

from alembic import op

revision: str = "0085_custom_package_sessions"
down_revision: str | Sequence[str] | None = "0084_extra_service_pulses"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.drop_constraint(
        "service_package_offer_sessions_valid",
        "service_package_offers",
        type_="check",
    )
    op.create_check_constraint(
        "service_package_offer_sessions_valid",
        "service_package_offers",
        "sessions_count > 0",
    )


def downgrade() -> None:
    op.drop_constraint(
        "service_package_offer_sessions_valid",
        "service_package_offers",
        type_="check",
    )
    op.create_check_constraint(
        "service_package_offer_sessions_valid",
        "service_package_offers",
        "sessions_count IN (3, 6, 9)",
    )
