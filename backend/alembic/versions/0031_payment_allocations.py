"""Add patient-level payments and explicit appointment allocations.

Revision ID: 0031_payment_allocations
Revises: 0030_external_system_contract
Create Date: 2026-08-26
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "0031_payment_allocations"
down_revision: str | Sequence[str] | None = "0030_external_system_contract"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "payment_allocations",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("workspace_id", sa.Uuid(), nullable=False),
        sa.Column("transaction_id", sa.Uuid(), nullable=False),
        sa.Column("appointment_id", sa.Uuid(), nullable=False),
        sa.Column("amount_minor", sa.Integer(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.CheckConstraint(
            "amount_minor > 0",
            name="ck_payment_allocations_payment_allocation_amount_positive",
        ),
        sa.ForeignKeyConstraint(
            ["workspace_id"],
            ["workspaces.id"],
            name="fk_payment_allocations_workspace",
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["workspace_id", "transaction_id"],
            ["payment_transactions.workspace_id", "payment_transactions.id"],
            name="fk_payment_allocations_transaction",
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["workspace_id", "appointment_id"],
            ["appointments.workspace_id", "appointments.id"],
            name="fk_payment_allocations_appointment",
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id", name="pk_payment_allocations"),
        sa.UniqueConstraint(
            "workspace_id",
            "id",
            name="uq_payment_allocations_workspace_id_id",
        ),
        sa.UniqueConstraint(
            "workspace_id",
            "transaction_id",
            "appointment_id",
            name="uq_payment_allocations_workspace_transaction_appointment",
        ),
    )
    op.create_index("ix_payment_allocations_workspace_id", "payment_allocations", ["workspace_id"])
    op.create_index("ix_payment_allocations_transaction_id", "payment_allocations", ["transaction_id"])
    op.create_index("ix_payment_allocations_appointment_id", "payment_allocations", ["appointment_id"])
    op.create_index(
        "ix_payment_allocations_workspace_transaction",
        "payment_allocations",
        ["workspace_id", "transaction_id"],
    )
    op.create_index(
        "ix_payment_allocations_workspace_appointment",
        "payment_allocations",
        ["workspace_id", "appointment_id"],
    )

    # Every v0.36/v0.37 ledger fact was appointment-scoped. Preserve that exact
    # meaning as one explicit allocation before making appointment linkage
    # optional on the financial transaction itself.
    op.execute(
        """
        INSERT INTO payment_allocations (
            id, workspace_id, transaction_id, appointment_id, amount_minor, created_at
        )
        SELECT
            md5(pt.id::text || chr(58) || 'allocation')::uuid,
            pt.workspace_id,
            pt.id,
            pt.appointment_id,
            pt.amount_minor,
            pt.created_at
        FROM payment_transactions pt
        WHERE pt.appointment_id IS NOT NULL
        """
    )

    op.alter_column(
        "payment_transactions",
        "appointment_id",
        existing_type=sa.Uuid(),
        nullable=True,
    )
    op.alter_column(
        "payment_transactions",
        "origin_appointment_id",
        existing_type=sa.Uuid(),
        nullable=True,
    )


def downgrade() -> None:
    # The old ledger can represent exactly one fully allocated appointment per
    # transaction. Never guess how to collapse patient-level or multi-allocation
    # facts during downgrade.
    op.execute(
        """
        DO $$
        BEGIN
            IF EXISTS (
                SELECT 1
                FROM payment_transactions pt
                WHERE pt.appointment_id IS NULL
                   OR pt.origin_appointment_id IS NULL
                   OR (SELECT count(*) FROM payment_allocations pa
                       WHERE pa.workspace_id = pt.workspace_id
                         AND pa.transaction_id = pt.id) <> 1
                   OR NOT EXISTS (
                       SELECT 1
                       FROM payment_allocations pa
                       WHERE pa.workspace_id = pt.workspace_id
                         AND pa.transaction_id = pt.id
                         AND pa.appointment_id = pt.appointment_id
                         AND pa.amount_minor = pt.amount_minor
                   )
            ) THEN
                RAISE EXCEPTION 'Cannot downgrade: payment ledger contains patient-level or multi-allocation facts.';
            END IF;
        END $$;
        """
    )

    op.alter_column(
        "payment_transactions",
        "origin_appointment_id",
        existing_type=sa.Uuid(),
        nullable=False,
    )
    op.alter_column(
        "payment_transactions",
        "appointment_id",
        existing_type=sa.Uuid(),
        nullable=False,
    )

    op.drop_index("ix_payment_allocations_workspace_appointment", table_name="payment_allocations")
    op.drop_index("ix_payment_allocations_workspace_transaction", table_name="payment_allocations")
    op.drop_index("ix_payment_allocations_appointment_id", table_name="payment_allocations")
    op.drop_index("ix_payment_allocations_transaction_id", table_name="payment_allocations")
    op.drop_index("ix_payment_allocations_workspace_id", table_name="payment_allocations")
    op.drop_table("payment_allocations")
