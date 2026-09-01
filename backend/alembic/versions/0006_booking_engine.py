"""Booking engine tables and concurrency protection.

Revision ID: 0006_booking_engine
Revises: 0005_crm_core
Create Date: 2026-08-12
"""

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB, ExcludeConstraint

from alembic import op

revision: str = "0006_booking_engine"
down_revision: str | Sequence[str] | None = "0005_crm_core"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

BOOKING_TABLES = (
    "appointments",
    "appointment_status_history",
)


def upgrade() -> None:
    # UUID equality operators need btree_gist so the GiST exclusion constraint can
    # combine workspace/doctor equality with timestamp-range overlap.
    op.execute("CREATE EXTENSION IF NOT EXISTS btree_gist")
    op.create_unique_constraint(
        "uq_leads_workspace_id_id",
        "leads",
        ["workspace_id", "id"],
    )

    op.create_table(
        "appointments",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("workspace_id", sa.Uuid(), nullable=False),
        sa.Column("patient_id", sa.Uuid(), nullable=False),
        sa.Column("branch_id", sa.Uuid(), nullable=False),
        sa.Column("doctor_id", sa.Uuid(), nullable=False),
        sa.Column("service_id", sa.Uuid(), nullable=False),
        sa.Column("lead_id", sa.Uuid(), nullable=True),
        sa.Column("created_by_user_id", sa.Uuid(), nullable=True),
        sa.Column("rescheduled_from_appointment_id", sa.Uuid(), nullable=True),
        sa.Column("status", sa.String(length=20), server_default="pending", nullable=False),
        sa.Column("source", sa.String(length=20), server_default="staff", nullable=False),
        sa.Column("start_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("end_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("busy_start_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("busy_end_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("duration_minutes", sa.Integer(), nullable=False),
        sa.Column("price_minor", sa.Integer(), server_default="0", nullable=False),
        sa.Column("currency", sa.String(length=3), server_default="EGP", nullable=False),
        sa.Column("customer_note", sa.Text(), nullable=True),
        sa.Column("cancellation_reason", sa.Text(), nullable=True),
        sa.Column("idempotency_key", sa.String(length=128), nullable=True),
        sa.Column("confirmed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("cancelled_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("no_show_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.CheckConstraint(
            "status IN ('pending', 'confirmed', 'checked_in', 'in_progress', "
            "'completed', 'cancelled', 'no_show', 'rescheduled')",
            name=op.f("ck_appointments_appointment_status_valid"),
        ),
        sa.CheckConstraint(
            "source IN ('ai', 'staff', 'whatsapp', 'instagram', 'website', "
            "'phone', 'walk_in', 'facebook', 'email', 'other')",
            name=op.f("ck_appointments_appointment_source_valid"),
        ),
        sa.CheckConstraint(
            "end_at > start_at", name=op.f("ck_appointments_appointment_interval_valid")
        ),
        sa.CheckConstraint(
            "busy_end_at > busy_start_at",
            name=op.f("ck_appointments_appointment_busy_interval_valid"),
        ),
        sa.CheckConstraint(
            "busy_start_at <= start_at",
            name=op.f("ck_appointments_appointment_busy_start_valid"),
        ),
        sa.CheckConstraint(
            "busy_end_at >= end_at",
            name=op.f("ck_appointments_appointment_busy_end_valid"),
        ),
        sa.CheckConstraint(
            "duration_minutes > 0",
            name=op.f("ck_appointments_appointment_duration_positive"),
        ),
        sa.CheckConstraint(
            "price_minor >= 0",
            name=op.f("ck_appointments_appointment_price_non_negative"),
        ),
        sa.ForeignKeyConstraint(
            ["workspace_id"],
            ["workspaces.id"],
            ondelete="CASCADE",
            name="fk_appointments_workspace",
        ),
        sa.ForeignKeyConstraint(
            ["workspace_id", "patient_id"],
            ["patients.workspace_id", "patients.id"],
            ondelete="RESTRICT",
            name="fk_appointments_patient",
        ),
        sa.ForeignKeyConstraint(
            ["workspace_id", "branch_id"],
            ["branches.workspace_id", "branches.id"],
            ondelete="RESTRICT",
            name="fk_appointments_branch",
        ),
        sa.ForeignKeyConstraint(
            ["workspace_id", "doctor_id"],
            ["doctors.workspace_id", "doctors.id"],
            ondelete="RESTRICT",
            name="fk_appointments_doctor",
        ),
        sa.ForeignKeyConstraint(
            ["workspace_id", "service_id"],
            ["services.workspace_id", "services.id"],
            ondelete="RESTRICT",
            name="fk_appointments_service",
        ),
        sa.ForeignKeyConstraint(
            ["workspace_id", "lead_id"],
            ["leads.workspace_id", "leads.id"],
            ondelete="RESTRICT",
            name="fk_appointments_lead",
        ),
        sa.ForeignKeyConstraint(["created_by_user_id"], ["users.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(
            ["rescheduled_from_appointment_id"],
            ["appointments.id"],
            ondelete="SET NULL",
            name=op.f("fk_appointments_rescheduled_from_appointment_id_appointments"),
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("workspace_id", "id", name="uq_appointments_workspace_id_id"),
        ExcludeConstraint(
            ("workspace_id", "="),
            ("doctor_id", "="),
            (sa.text("tstzrange(busy_start_at, busy_end_at, '[)')"), "&&"),
            where=sa.text("status IN ('pending', 'confirmed', 'checked_in', 'in_progress')"),
            using="gist",
            name="excl_appointments_doctor_busy_time",
        ),
    )
    op.create_index("ix_appointments_workspace_id", "appointments", ["workspace_id"])
    op.create_index("ix_appointments_patient_id", "appointments", ["patient_id"])
    op.create_index("ix_appointments_branch_id", "appointments", ["branch_id"])
    op.create_index("ix_appointments_doctor_id", "appointments", ["doctor_id"])
    op.create_index("ix_appointments_service_id", "appointments", ["service_id"])
    op.create_index("ix_appointments_lead_id", "appointments", ["lead_id"])
    op.create_index("ix_appointments_created_by_user_id", "appointments", ["created_by_user_id"])
    op.create_index(
        "ix_appointments_rescheduled_from_appointment_id",
        "appointments",
        ["rescheduled_from_appointment_id"],
    )
    op.create_index(
        "ix_appointments_workspace_start",
        "appointments",
        ["workspace_id", "start_at"],
    )
    op.create_index(
        "ix_appointments_patient_start",
        "appointments",
        ["patient_id", "start_at"],
    )
    op.create_index(
        "ix_appointments_doctor_start",
        "appointments",
        ["doctor_id", "start_at"],
    )
    op.create_index(
        "ix_appointments_branch_start",
        "appointments",
        ["branch_id", "start_at"],
    )
    op.create_index(
        "ix_appointments_workspace_status",
        "appointments",
        ["workspace_id", "status"],
    )
    op.create_index(
        "uq_appointments_workspace_idempotency_key",
        "appointments",
        ["workspace_id", "idempotency_key"],
        unique=True,
        postgresql_where=sa.text("idempotency_key IS NOT NULL"),
    )

    op.create_table(
        "appointment_status_history",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("workspace_id", sa.Uuid(), nullable=False),
        sa.Column("appointment_id", sa.Uuid(), nullable=False),
        sa.Column("changed_by_user_id", sa.Uuid(), nullable=True),
        sa.Column("from_status", sa.String(length=20), nullable=True),
        sa.Column("to_status", sa.String(length=20), nullable=False),
        sa.Column("reason", sa.Text(), nullable=True),
        sa.Column("metadata", JSONB(astext_type=sa.Text()), server_default="{}", nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.CheckConstraint(
            "from_status IS NULL OR from_status IN ('pending', 'confirmed', 'checked_in', "
            "'in_progress', 'completed', 'cancelled', 'no_show', 'rescheduled')",
            name=op.f("ck_appointment_status_history_appointment_history_from_status_valid"),
        ),
        sa.CheckConstraint(
            "to_status IN ('pending', 'confirmed', 'checked_in', 'in_progress', "
            "'completed', 'cancelled', 'no_show', 'rescheduled')",
            name=op.f("ck_appointment_status_history_appointment_history_to_status_valid"),
        ),
        sa.ForeignKeyConstraint(
            ["workspace_id", "appointment_id"],
            ["appointments.workspace_id", "appointments.id"],
            ondelete="CASCADE",
            name="fk_appointment_status_history_appointment",
        ),
        sa.ForeignKeyConstraint(["changed_by_user_id"], ["users.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_appointment_status_history_workspace_id",
        "appointment_status_history",
        ["workspace_id"],
    )
    op.create_index(
        "ix_appointment_status_history_appointment_id",
        "appointment_status_history",
        ["appointment_id"],
    )
    op.create_index(
        "ix_appointment_status_history_changed_by_user_id",
        "appointment_status_history",
        ["changed_by_user_id"],
    )
    op.create_index(
        "ix_appointment_status_history_created_at",
        "appointment_status_history",
        ["created_at"],
    )

    for table in BOOKING_TABLES:
        op.execute(sa.text(f'ALTER TABLE public."{table}" ENABLE ROW LEVEL SECURITY'))
        op.execute(sa.text(f'REVOKE ALL ON TABLE public."{table}" FROM anon, authenticated'))


def downgrade() -> None:
    op.drop_index(
        "ix_appointment_status_history_created_at", table_name="appointment_status_history"
    )
    op.drop_index(
        "ix_appointment_status_history_changed_by_user_id",
        table_name="appointment_status_history",
    )
    op.drop_index(
        "ix_appointment_status_history_appointment_id",
        table_name="appointment_status_history",
    )
    op.drop_index(
        "ix_appointment_status_history_workspace_id",
        table_name="appointment_status_history",
    )
    op.drop_table("appointment_status_history")

    op.drop_index("uq_appointments_workspace_idempotency_key", table_name="appointments")
    op.drop_index("ix_appointments_workspace_status", table_name="appointments")
    op.drop_index("ix_appointments_branch_start", table_name="appointments")
    op.drop_index("ix_appointments_doctor_start", table_name="appointments")
    op.drop_index("ix_appointments_patient_start", table_name="appointments")
    op.drop_index("ix_appointments_workspace_start", table_name="appointments")
    op.drop_index("ix_appointments_rescheduled_from_appointment_id", table_name="appointments")
    op.drop_index("ix_appointments_created_by_user_id", table_name="appointments")
    op.drop_index("ix_appointments_lead_id", table_name="appointments")
    op.drop_index("ix_appointments_service_id", table_name="appointments")
    op.drop_index("ix_appointments_doctor_id", table_name="appointments")
    op.drop_index("ix_appointments_branch_id", table_name="appointments")
    op.drop_index("ix_appointments_patient_id", table_name="appointments")
    op.drop_index("ix_appointments_workspace_id", table_name="appointments")
    op.drop_table("appointments")
    op.drop_constraint("uq_leads_workspace_id_id", "leads", type_="unique")
