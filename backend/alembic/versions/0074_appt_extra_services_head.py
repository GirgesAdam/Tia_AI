"""Normalize the appointment-commerce migration head.

Revision ID: 0074_appt_extra_services_head
Revises: 0073_appointment_additional_services

The 0073 migration was already applied in production using its original
revision identifier before the repository-side identifier was shortened.
Keep that historical identifier intact and advance with a no-op revision so
both clean databases and the existing production database share one head.
"""

from collections.abc import Sequence

revision: str = "0074_appt_extra_services_head"
down_revision: str | Sequence[str] | None = "0073_appointment_additional_services"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    pass


def downgrade() -> None:
    pass
