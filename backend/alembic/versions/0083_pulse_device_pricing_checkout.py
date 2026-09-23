"""Make pulse overage pricing device-specific and support checkout settlement.

Revision ID: 0083_pulse_device_pricing
Revises: 0082_pulse_wallet_billing
"""

from __future__ import annotations

from collections.abc import Sequence
from uuid import uuid4

import sqlalchemy as sa

from alembic import op

revision: str = "0083_pulse_device_pricing"
down_revision: str | Sequence[str] | None = "0082_pulse_wallet_billing"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_DEVICE_KEYS = ("candela_gentle", "prime_lase")


def upgrade() -> None:
    op.add_column(
        "pulse_billing_settings",
        sa.Column("device_key", sa.String(length=40), nullable=True),
    )
    op.drop_constraint(
        "uq_pulse_billing_settings_workspace",
        "pulse_billing_settings",
        type_="unique",
    )

    bind = op.get_bind()
    rows = bind.execute(
        sa.text(
            """
            SELECT id, workspace_id, overage_price_minor, currency, created_at, updated_at
            FROM pulse_billing_settings
            """
        )
    ).mappings().all()
    for row in rows:
        bind.execute(
            sa.text(
                """
                UPDATE pulse_billing_settings
                SET device_key = :device_key
                WHERE id = :id
                """
            ),
            {"device_key": _DEVICE_KEYS[0], "id": row["id"]},
        )
        bind.execute(
            sa.text(
                """
                INSERT INTO pulse_billing_settings
                    (id, workspace_id, device_key, overage_price_minor, currency, created_at, updated_at)
                VALUES
                    (:id, :workspace_id, :device_key, :overage_price_minor, :currency, :created_at, :updated_at)
                """
            ),
            {
                "id": uuid4(),
                "workspace_id": row["workspace_id"],
                "device_key": _DEVICE_KEYS[1],
                "overage_price_minor": row["overage_price_minor"],
                "currency": row["currency"],
                "created_at": row["created_at"],
                "updated_at": row["updated_at"],
            },
        )

    op.alter_column(
        "pulse_billing_settings",
        "device_key",
        existing_type=sa.String(length=40),
        nullable=False,
    )
    op.create_check_constraint(
        "pulse_billing_settings_device_valid",
        "pulse_billing_settings",
        "device_key IN ('prime_lase', 'candela_gentle')",
    )
    op.create_unique_constraint(
        "uq_pulse_billing_settings_workspace_device",
        "pulse_billing_settings",
        ["workspace_id", "device_key"],
    )


def downgrade() -> None:
    bind = op.get_bind()
    bind.execute(
        sa.text(
            """
            DELETE FROM pulse_billing_settings
            WHERE device_key <> 'candela_gentle'
            """
        )
    )
    op.drop_constraint(
        "uq_pulse_billing_settings_workspace_device",
        "pulse_billing_settings",
        type_="unique",
    )
    op.drop_constraint(
        "pulse_billing_settings_device_valid",
        "pulse_billing_settings",
        type_="check",
    )
    op.drop_column("pulse_billing_settings", "device_key")
    op.create_unique_constraint(
        "uq_pulse_billing_settings_workspace",
        "pulse_billing_settings",
        ["workspace_id"],
    )
