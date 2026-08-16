"""Clinic core tables.

Revision ID: 0002_clinic_core
Revises: 0001_foundation
Create Date: 2026-08-12
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0002_clinic_core"
down_revision: Union[str, Sequence[str], None] = "0001_foundation"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "branches",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("workspace_id", sa.Uuid(), nullable=False),
        sa.Column("name", sa.String(length=200), nullable=False),
        sa.Column("code", sa.String(length=50), nullable=False),
        sa.Column("phone", sa.String(length=40), nullable=True),
        sa.Column("email", sa.String(length=320), nullable=True),
        sa.Column("address_line1", sa.String(length=300), nullable=True),
        sa.Column("address_line2", sa.String(length=300), nullable=True),
        sa.Column("city", sa.String(length=120), nullable=True),
        sa.Column("state", sa.String(length=120), nullable=True),
        sa.Column("country_code", sa.String(length=2), server_default="EG", nullable=False),
        sa.Column("timezone", sa.String(length=64), nullable=True),
        sa.Column("is_active", sa.Boolean(), server_default=sa.true(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.ForeignKeyConstraint(["workspace_id"], ["workspaces.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("workspace_id", "id", name="uq_branches_workspace_id_id"),
        sa.UniqueConstraint("workspace_id", "code", name="uq_branches_workspace_code"),
    )
    op.create_index("ix_branches_workspace_id", "branches", ["workspace_id"])

    op.create_table(
        "staff",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("workspace_id", sa.Uuid(), nullable=False),
        sa.Column("user_id", sa.Uuid(), nullable=True),
        sa.Column("first_name", sa.String(length=120), nullable=False),
        sa.Column("last_name", sa.String(length=120), nullable=False),
        sa.Column("email", sa.String(length=320), nullable=True),
        sa.Column("phone", sa.String(length=40), nullable=True),
        sa.Column("job_title", sa.String(length=120), nullable=True),
        sa.Column("is_active", sa.Boolean(), server_default=sa.true(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.ForeignKeyConstraint(["workspace_id"], ["workspaces.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("workspace_id", "id", name="uq_staff_workspace_id_id"),
        sa.UniqueConstraint("workspace_id", "email", name="uq_staff_workspace_email"),
    )
    op.create_index("ix_staff_workspace_id", "staff", ["workspace_id"])
    op.create_index("ix_staff_user_id", "staff", ["user_id"])

    op.create_table(
        "services",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("workspace_id", sa.Uuid(), nullable=False),
        sa.Column("name", sa.String(length=200), nullable=False),
        sa.Column("slug", sa.String(length=160), nullable=False),
        sa.Column("category", sa.String(length=120), nullable=True),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("duration_minutes", sa.Integer(), nullable=False),
        sa.Column("buffer_before_minutes", sa.Integer(), server_default="0", nullable=False),
        sa.Column("buffer_after_minutes", sa.Integer(), server_default="0", nullable=False),
        sa.Column("price_minor", sa.Integer(), server_default="0", nullable=False),
        sa.Column("currency", sa.String(length=3), server_default="EGP", nullable=False),
        sa.Column("requires_medical_review", sa.Boolean(), server_default=sa.false(), nullable=False),
        sa.Column("is_active", sa.Boolean(), server_default=sa.true(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.CheckConstraint("duration_minutes > 0 AND duration_minutes <= 1440", name="ck_services_service_duration_valid"),
        sa.CheckConstraint("price_minor >= 0", name="ck_services_service_price_non_negative"),
        sa.CheckConstraint("buffer_before_minutes >= 0", name="ck_services_service_buffer_before_non_negative"),
        sa.CheckConstraint("buffer_after_minutes >= 0", name="ck_services_service_buffer_after_non_negative"),
        sa.ForeignKeyConstraint(["workspace_id"], ["workspaces.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("workspace_id", "id", name="uq_services_workspace_id_id"),
        sa.UniqueConstraint("workspace_id", "slug", name="uq_services_workspace_slug"),
    )
    op.create_index("ix_services_workspace_id", "services", ["workspace_id"])

    op.create_table(
        "doctors",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("workspace_id", sa.Uuid(), nullable=False),
        sa.Column("staff_id", sa.Uuid(), nullable=False),
        sa.Column("specialization", sa.String(length=200), nullable=True),
        sa.Column("license_number", sa.String(length=120), nullable=True),
        sa.Column("bio", sa.String(length=2000), nullable=True),
        sa.Column("booking_enabled", sa.Boolean(), server_default=sa.true(), nullable=False),
        sa.Column("is_active", sa.Boolean(), server_default=sa.true(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.ForeignKeyConstraint(
            ["workspace_id", "staff_id"], ["staff.workspace_id", "staff.id"],
            ondelete="CASCADE", name="fk_doctors_workspace_staff"
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("workspace_id", "id", name="uq_doctors_workspace_id_id"),
        sa.UniqueConstraint("workspace_id", "staff_id", name="uq_doctors_workspace_staff"),
    )
    op.create_index("ix_doctors_workspace_id", "doctors", ["workspace_id"])
    op.create_index("ix_doctors_staff_id", "doctors", ["staff_id"])

    op.create_table(
        "doctor_branches",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("workspace_id", sa.Uuid(), nullable=False),
        sa.Column("doctor_id", sa.Uuid(), nullable=False),
        sa.Column("branch_id", sa.Uuid(), nullable=False),
        sa.Column("is_primary", sa.Boolean(), server_default=sa.false(), nullable=False),
        sa.Column("is_active", sa.Boolean(), server_default=sa.true(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.ForeignKeyConstraint(
            ["workspace_id", "doctor_id"], ["doctors.workspace_id", "doctors.id"],
            ondelete="CASCADE", name="fk_doctor_branches_doctor"
        ),
        sa.ForeignKeyConstraint(
            ["workspace_id", "branch_id"], ["branches.workspace_id", "branches.id"],
            ondelete="CASCADE", name="fk_doctor_branches_branch"
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("workspace_id", "doctor_id", "branch_id", name="uq_doctor_branches_assignment"),
    )
    op.create_index("ix_doctor_branches_workspace_id", "doctor_branches", ["workspace_id"])
    op.create_index("ix_doctor_branches_doctor_id", "doctor_branches", ["doctor_id"])
    op.create_index("ix_doctor_branches_branch_id", "doctor_branches", ["branch_id"])

    op.create_table(
        "doctor_services",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("workspace_id", sa.Uuid(), nullable=False),
        sa.Column("doctor_id", sa.Uuid(), nullable=False),
        sa.Column("service_id", sa.Uuid(), nullable=False),
        sa.Column("custom_duration_minutes", sa.Integer(), nullable=True),
        sa.Column("custom_price_minor", sa.Integer(), nullable=True),
        sa.Column("is_active", sa.Boolean(), server_default=sa.true(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.CheckConstraint("custom_duration_minutes IS NULL OR custom_duration_minutes > 0", name="ck_doctor_services_doctor_service_duration_valid"),
        sa.CheckConstraint("custom_price_minor IS NULL OR custom_price_minor >= 0", name="ck_doctor_services_doctor_service_price_non_negative"),
        sa.ForeignKeyConstraint(
            ["workspace_id", "doctor_id"], ["doctors.workspace_id", "doctors.id"],
            ondelete="CASCADE", name="fk_doctor_services_doctor"
        ),
        sa.ForeignKeyConstraint(
            ["workspace_id", "service_id"], ["services.workspace_id", "services.id"],
            ondelete="CASCADE", name="fk_doctor_services_service"
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("workspace_id", "doctor_id", "service_id", name="uq_doctor_services_assignment"),
    )
    op.create_index("ix_doctor_services_workspace_id", "doctor_services", ["workspace_id"])
    op.create_index("ix_doctor_services_doctor_id", "doctor_services", ["doctor_id"])
    op.create_index("ix_doctor_services_service_id", "doctor_services", ["service_id"])

    op.create_table(
        "branch_working_hours",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("workspace_id", sa.Uuid(), nullable=False),
        sa.Column("branch_id", sa.Uuid(), nullable=False),
        sa.Column("weekday", sa.Integer(), nullable=False),
        sa.Column("start_time", sa.Time(), nullable=False),
        sa.Column("end_time", sa.Time(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.CheckConstraint("weekday >= 0 AND weekday <= 6", name="ck_branch_working_hours_branch_working_hours_weekday_valid"),
        sa.CheckConstraint("end_time > start_time", name="ck_branch_working_hours_branch_working_hours_interval_valid"),
        sa.ForeignKeyConstraint(
            ["workspace_id", "branch_id"], ["branches.workspace_id", "branches.id"],
            ondelete="CASCADE", name="fk_branch_working_hours_branch"
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("workspace_id", "branch_id", "weekday", "start_time", "end_time", name="uq_branch_working_hours_interval"),
    )
    op.create_index("ix_branch_working_hours_workspace_id", "branch_working_hours", ["workspace_id"])
    op.create_index("ix_branch_working_hours_branch_id", "branch_working_hours", ["branch_id"])

    op.create_table(
        "doctor_working_hours",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("workspace_id", sa.Uuid(), nullable=False),
        sa.Column("doctor_id", sa.Uuid(), nullable=False),
        sa.Column("branch_id", sa.Uuid(), nullable=False),
        sa.Column("weekday", sa.Integer(), nullable=False),
        sa.Column("start_time", sa.Time(), nullable=False),
        sa.Column("end_time", sa.Time(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.CheckConstraint("weekday >= 0 AND weekday <= 6", name="ck_doctor_working_hours_doctor_working_hours_weekday_valid"),
        sa.CheckConstraint("end_time > start_time", name="ck_doctor_working_hours_doctor_working_hours_interval_valid"),
        sa.ForeignKeyConstraint(
            ["workspace_id", "doctor_id", "branch_id"],
            ["doctor_branches.workspace_id", "doctor_branches.doctor_id", "doctor_branches.branch_id"],
            ondelete="CASCADE", name="fk_doctor_working_hours_assignment"
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("workspace_id", "doctor_id", "branch_id", "weekday", "start_time", "end_time", name="uq_doctor_working_hours_interval"),
    )
    op.create_index("ix_doctor_working_hours_workspace_id", "doctor_working_hours", ["workspace_id"])
    op.create_index("ix_doctor_working_hours_doctor_id", "doctor_working_hours", ["doctor_id"])
    op.create_index("ix_doctor_working_hours_branch_id", "doctor_working_hours", ["branch_id"])

    op.create_table(
        "booking_settings",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("workspace_id", sa.Uuid(), nullable=False),
        sa.Column("slot_interval_minutes", sa.Integer(), server_default="15", nullable=False),
        sa.Column("minimum_notice_minutes", sa.Integer(), server_default="60", nullable=False),
        sa.Column("booking_horizon_days", sa.Integer(), server_default="90", nullable=False),
        sa.Column("cancellation_notice_minutes", sa.Integer(), server_default="720", nullable=False),
        sa.Column("allow_same_day_booking", sa.Boolean(), server_default=sa.true(), nullable=False),
        sa.Column("require_confirmation", sa.Boolean(), server_default=sa.true(), nullable=False),
        sa.Column("default_currency", sa.String(length=3), server_default="EGP", nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.CheckConstraint("slot_interval_minutes > 0 AND slot_interval_minutes <= 240", name="ck_booking_settings_booking_slot_interval_valid"),
        sa.CheckConstraint("minimum_notice_minutes >= 0", name="ck_booking_settings_booking_minimum_notice_non_negative"),
        sa.CheckConstraint("booking_horizon_days > 0 AND booking_horizon_days <= 730", name="ck_booking_settings_booking_horizon_valid"),
        sa.CheckConstraint("cancellation_notice_minutes >= 0", name="ck_booking_settings_booking_cancellation_notice_non_negative"),
        sa.ForeignKeyConstraint(["workspace_id"], ["workspaces.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_booking_settings_workspace_id", "booking_settings", ["workspace_id"], unique=True)


def downgrade() -> None:
    op.drop_index("ix_booking_settings_workspace_id", table_name="booking_settings")
    op.drop_table("booking_settings")
    op.drop_index("ix_doctor_working_hours_branch_id", table_name="doctor_working_hours")
    op.drop_index("ix_doctor_working_hours_doctor_id", table_name="doctor_working_hours")
    op.drop_index("ix_doctor_working_hours_workspace_id", table_name="doctor_working_hours")
    op.drop_table("doctor_working_hours")
    op.drop_index("ix_branch_working_hours_branch_id", table_name="branch_working_hours")
    op.drop_index("ix_branch_working_hours_workspace_id", table_name="branch_working_hours")
    op.drop_table("branch_working_hours")
    op.drop_index("ix_doctor_services_service_id", table_name="doctor_services")
    op.drop_index("ix_doctor_services_doctor_id", table_name="doctor_services")
    op.drop_index("ix_doctor_services_workspace_id", table_name="doctor_services")
    op.drop_table("doctor_services")
    op.drop_index("ix_doctor_branches_branch_id", table_name="doctor_branches")
    op.drop_index("ix_doctor_branches_doctor_id", table_name="doctor_branches")
    op.drop_index("ix_doctor_branches_workspace_id", table_name="doctor_branches")
    op.drop_table("doctor_branches")
    op.drop_index("ix_doctors_staff_id", table_name="doctors")
    op.drop_index("ix_doctors_workspace_id", table_name="doctors")
    op.drop_table("doctors")
    op.drop_index("ix_services_workspace_id", table_name="services")
    op.drop_table("services")
    op.drop_index("ix_staff_user_id", table_name="staff")
    op.drop_index("ix_staff_workspace_id", table_name="staff")
    op.drop_table("staff")
    op.drop_index("ix_branches_workspace_id", table_name="branches")
    op.drop_table("branches")
