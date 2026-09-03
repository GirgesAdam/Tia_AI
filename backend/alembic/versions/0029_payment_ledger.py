"""Add canonical appointment payment ledger.

Revision ID: 0029_payment_ledger
Revises: 0028_activity_audit_trail
Create Date: 2026-08-25
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "0029_payment_ledger"
down_revision: str | Sequence[str] | None = "0028_activity_audit_trail"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "payment_transactions",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("workspace_id", sa.Uuid(), nullable=False),
        sa.Column("appointment_id", sa.Uuid(), nullable=False),
        sa.Column("origin_appointment_id", sa.Uuid(), nullable=False),
        sa.Column("patient_id", sa.Uuid(), nullable=False),
        sa.Column("created_by_user_id", sa.Uuid(), nullable=True),
        sa.Column("reference_transaction_id", sa.Uuid(), nullable=True),
        sa.Column("transaction_type", sa.String(length=16), nullable=False),
        sa.Column("amount_minor", sa.Integer(), nullable=False),
        sa.Column("currency", sa.String(length=3), nullable=False),
        sa.Column("payment_method", sa.String(length=24), nullable=False),
        sa.Column("source", sa.String(length=24), nullable=False),
        sa.Column("external_reference", sa.String(length=128), nullable=True),
        sa.Column("reason", sa.Text(), nullable=True),
        sa.Column("idempotency_key", sa.String(length=128), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.CheckConstraint(
            "transaction_type IN ('payment', 'refund')",
            name="ck_payment_transactions_payment_transaction_type_valid",
        ),
        sa.CheckConstraint(
            "amount_minor > 0",
            name="ck_payment_transactions_payment_transaction_amount_positive",
        ),
        sa.CheckConstraint(
            "payment_method IN ('unknown', 'cash', 'card', 'bank_transfer', 'wallet', 'online', 'other')",
            name="ck_payment_transactions_payment_transaction_method_valid",
        ),
        sa.CheckConstraint(
            "source IN ('staff', 'legacy_backfill', 'integration', 'system')",
            name="ck_payment_transactions_payment_transaction_source_valid",
        ),
        sa.CheckConstraint(
            "(transaction_type = 'payment' AND reference_transaction_id IS NULL) OR "
            "(transaction_type = 'refund' AND reference_transaction_id IS NOT NULL)",
            name="ck_payment_transactions_payment_transaction_reference_valid",
        ),
        sa.ForeignKeyConstraint(
            ["created_by_user_id"],
            ["users.id"],
            name="fk_payment_transactions_created_by_user_id_users",
            ondelete="SET NULL",
        ),
        sa.ForeignKeyConstraint(
            ["workspace_id"],
            ["workspaces.id"],
            name="fk_payment_transactions_workspace",
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["workspace_id", "appointment_id"],
            ["appointments.workspace_id", "appointments.id"],
            name="fk_payment_transactions_appointment",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["workspace_id", "origin_appointment_id"],
            ["appointments.workspace_id", "appointments.id"],
            name="fk_payment_transactions_origin_appointment",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["workspace_id", "patient_id"],
            ["patients.workspace_id", "patients.id"],
            name="fk_payment_transactions_patient",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["workspace_id", "reference_transaction_id"],
            ["payment_transactions.workspace_id", "payment_transactions.id"],
            name="fk_payment_transactions_reference",
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id", name="pk_payment_transactions"),
        sa.UniqueConstraint(
            "workspace_id",
            "id",
            name="uq_payment_transactions_workspace_id_id",
        ),
    )
    op.create_index("ix_payment_transactions_workspace_id", "payment_transactions", ["workspace_id"])
    op.create_index("ix_payment_transactions_appointment_id", "payment_transactions", ["appointment_id"])
    op.create_index("ix_payment_transactions_origin_appointment_id", "payment_transactions", ["origin_appointment_id"])
    op.create_index("ix_payment_transactions_patient_id", "payment_transactions", ["patient_id"])
    op.create_index("ix_payment_transactions_created_by_user_id", "payment_transactions", ["created_by_user_id"])
    op.create_index("ix_payment_transactions_reference_transaction_id", "payment_transactions", ["reference_transaction_id"])
    op.create_index(
        "uq_payment_transactions_workspace_idempotency_key",
        "payment_transactions",
        ["workspace_id", "idempotency_key"],
        unique=True,
        postgresql_where=sa.text("idempotency_key IS NOT NULL"),
    )
    op.create_index(
        "ix_payment_transactions_workspace_appointment_created",
        "payment_transactions",
        ["workspace_id", "appointment_id", "created_at"],
    )
    op.create_index(
        "ix_payment_transactions_workspace_patient_created",
        "payment_transactions",
        ["workspace_id", "patient_id", "created_at"],
    )
    op.create_index(
        "ix_payment_transactions_workspace_reference",
        "payment_transactions",
        ["workspace_id", "reference_transaction_id"],
    )

    # Preserve existing payment snapshots as explicit ledger facts. We cannot
    # infer anything when amount_paid_minor is missing, so those rows remain
    # legacy snapshots until a real payment is recorded or imported later.
    op.execute(
        """
        INSERT INTO payment_transactions (
            id, workspace_id, appointment_id, origin_appointment_id, patient_id,
            created_by_user_id, reference_transaction_id, transaction_type,
            amount_minor, currency, payment_method, source, external_reference,
            reason, idempotency_key, created_at
        )
        SELECT
            md5(a.id::text || chr(58) || 'legacy-payment')::uuid,
            a.workspace_id,
            a.id,
            a.id,
            a.patient_id,
            NULL,
            NULL,
            'payment',
            a.amount_paid_minor,
            a.currency,
            CASE
                WHEN a.payment_method IN ('cash','card','bank_transfer','wallet','other')
                    THEN a.payment_method
                ELSE 'unknown'
            END,
            'legacy_backfill',
            NULL,
            NULL,
            NULL,
            COALESCE(a.updated_at, a.created_at, now())
        FROM appointments a
        WHERE a.amount_paid_minor IS NOT NULL
          AND a.amount_paid_minor > 0
          AND a.payment_status IN ('paid', 'partial', 'refunded')
        """
    )
    op.execute(
        """
        INSERT INTO payment_transactions (
            id, workspace_id, appointment_id, origin_appointment_id, patient_id,
            created_by_user_id, reference_transaction_id, transaction_type,
            amount_minor, currency, payment_method, source, external_reference,
            reason, idempotency_key, created_at
        )
        SELECT
            md5(a.id::text || chr(58) || 'legacy-refund')::uuid,
            a.workspace_id,
            a.id,
            a.id,
            a.patient_id,
            NULL,
            md5(a.id::text || chr(58) || 'legacy-payment')::uuid,
            'refund',
            a.amount_paid_minor,
            a.currency,
            CASE
                WHEN a.payment_method IN ('cash','card','bank_transfer','wallet','other')
                    THEN a.payment_method
                ELSE 'unknown'
            END,
            'legacy_backfill',
            NULL,
            'Legacy refunded appointment backfill',
            NULL,
            COALESCE(a.updated_at, a.created_at, now())
        FROM appointments a
        WHERE a.amount_paid_minor IS NOT NULL
          AND a.amount_paid_minor > 0
          AND a.payment_status = 'refunded'
        """
    )


def downgrade() -> None:
    op.drop_index("ix_payment_transactions_workspace_reference", table_name="payment_transactions")
    op.drop_index("ix_payment_transactions_workspace_patient_created", table_name="payment_transactions")
    op.drop_index("ix_payment_transactions_workspace_appointment_created", table_name="payment_transactions")
    op.drop_index("uq_payment_transactions_workspace_idempotency_key", table_name="payment_transactions")
    op.drop_index("ix_payment_transactions_reference_transaction_id", table_name="payment_transactions")
    op.drop_index("ix_payment_transactions_created_by_user_id", table_name="payment_transactions")
    op.drop_index("ix_payment_transactions_patient_id", table_name="payment_transactions")
    op.drop_index("ix_payment_transactions_origin_appointment_id", table_name="payment_transactions")
    op.drop_index("ix_payment_transactions_appointment_id", table_name="payment_transactions")
    op.drop_index("ix_payment_transactions_workspace_id", table_name="payment_transactions")
    op.drop_table("payment_transactions")
