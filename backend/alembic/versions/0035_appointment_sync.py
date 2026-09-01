"""Allow appointments in durable external sync domains.

Revision ID: 0035_appointment_sync
Revises: 0034_drop_customer_email
Create Date: 2026-08-26
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import context, op

revision: str = "0035_appointment_sync"
down_revision: str | Sequence[str] | None = "0034_drop_customer_email"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


# Migration 0032 created these CHECK constraints with already-prefixed names while
# the project naming convention also prefixes CHECK constraints. PostgreSQL then
# stored SQLAlchemy's deterministic truncated names below. Online migrations do
# not rely on the names: we inspect the live table and find its domain CHECK by
# expression. These constants exist only so ``--sql`` offline rendering remains
# deterministic for databases created by the 0032 migration.
_LEGACY_DOMAIN_CHECK_NAMES = {
    "clinic_integration_sync_runs": (
        "ck_clinic_integration_sync_runs_ck_clinic_integration_s_7aa7"
    ),
    "clinic_integration_sync_checkpoints": (
        "ck_clinic_integration_sync_checkpoints_ck_clinic_integr_ac8f"
    ),
    "clinic_integration_sync_failures": (
        "ck_clinic_integration_sync_failures_ck_clinic_integrati_6817"
    ),
}

_NEW_DOMAIN_CHECK_NAMES = {
    "clinic_integration_sync_runs": "ck_clinic_integration_sync_runs_domain_valid",
    "clinic_integration_sync_checkpoints": "ck_clinic_integration_sync_checkpoints_domain_valid",
    "clinic_integration_sync_failures": "ck_clinic_integration_sync_failures_domain_valid",
}


def _live_domain_check_name(table_name: str) -> str:
    inspector = sa.inspect(op.get_bind())
    matches: list[str] = []
    for check in inspector.get_check_constraints(table_name):
        sqltext = str(check.get("sqltext") or "").lower()
        name = check.get("name")
        if name and "domain" in sqltext:
            matches.append(str(name))

    if len(matches) != 1:
        raise RuntimeError(
            f"Expected exactly one domain CHECK constraint on {table_name}; found {matches!r}."
        )
    return matches[0]


def _drop_domain_check(table_name: str) -> None:
    if context.is_offline_mode():
        name = _LEGACY_DOMAIN_CHECK_NAMES[table_name]
    else:
        name = _live_domain_check_name(table_name)

    # ``conv`` marks this as the database's already-converted constraint name so
    # SQLAlchemy's naming convention cannot prefix it a second time.
    op.drop_constraint(sa.schema.conv(name), table_name, type_="check")


def _create_domain_check(table_name: str, *, include_appointments: bool) -> None:
    values = "'patients', 'payments', 'appointments'" if include_appointments else "'patients', 'payments'"
    op.create_check_constraint(
        op.f(_NEW_DOMAIN_CHECK_NAMES[table_name]),
        table_name,
        f"domain IN ({values})",
    )


def upgrade() -> None:
    for table_name in _LEGACY_DOMAIN_CHECK_NAMES:
        _drop_domain_check(table_name)
        _create_domain_check(table_name, include_appointments=True)


def downgrade() -> None:
    op.execute("DELETE FROM clinic_integration_sync_failures WHERE domain = 'appointments'")
    op.execute("DELETE FROM clinic_integration_sync_checkpoints WHERE domain = 'appointments'")
    op.execute("DELETE FROM clinic_integration_sync_runs WHERE domain = 'appointments'")

    for table_name in _LEGACY_DOMAIN_CHECK_NAMES:
        _drop_domain_check(table_name)
        _create_domain_check(table_name, include_appointments=False)
