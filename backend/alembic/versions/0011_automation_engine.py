"""Add appointment automation engine.

Revision ID: 0011_automation_engine
Revises: 0010_whatsapp_n8n_bridge
Create Date: 2026-08-13
"""

from collections.abc import Sequence
from uuid import uuid4

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision: str = "0011_automation_engine"
down_revision: str | Sequence[str] | None = "0010_whatsapp_n8n_bridge"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


DEFAULT_RULES = (
    (
        "booking_confirmation",
        "Booking confirmation",
        "appointment_created",
        0,
        "tia_booking_confirmation_ar",
        "ar",
        60,
    ),
    (
        "appointment_reminder_24h",
        "Appointment reminder - 24 hours",
        "before_appointment",
        -1440,
        "tia_appointment_reminder_24h_ar",
        "ar",
        30,
    ),
    (
        "appointment_reminder_2h",
        "Appointment reminder - 2 hours",
        "before_appointment",
        -120,
        "tia_appointment_reminder_2h_ar",
        "ar",
        20,
    ),
    (
        "post_visit_followup",
        "Post-visit follow-up",
        "after_completed",
        1440,
        "tia_post_visit_followup_ar",
        "ar",
        1440,
    ),
    (
        "no_show_followup",
        "No-show recovery follow-up",
        "after_no_show",
        30,
        "tia_no_show_followup_ar",
        "ar",
        720,
    ),
)


def upgrade() -> None:
    op.create_table(
        "automation_rules",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("workspace_id", sa.Uuid(), nullable=False),
        sa.Column("key", sa.String(length=80), nullable=False),
        sa.Column("name", sa.String(length=160), nullable=False),
        sa.Column("enabled", sa.Boolean(), server_default=sa.text("false"), nullable=False),
        sa.Column("trigger_kind", sa.String(length=40), nullable=False),
        sa.Column("offset_minutes", sa.Integer(), server_default="0", nullable=False),
        sa.Column("channel", sa.String(length=20), server_default="whatsapp", nullable=False),
        sa.Column("template_name", sa.String(length=160), nullable=False),
        sa.Column("template_language", sa.String(length=20), server_default="ar", nullable=False),
        sa.Column("max_lateness_minutes", sa.Integer(), server_default="30", nullable=False),
        sa.Column(
            "config",
            postgresql.JSONB(astext_type=sa.Text()),
            server_default=sa.text("'{}'::jsonb"),
            nullable=False,
        ),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.CheckConstraint(
            "trigger_kind IN ('appointment_created', 'before_appointment', 'after_completed', 'after_no_show')",
            name="automation_rule_trigger_kind_valid",
        ),
        sa.CheckConstraint(
            "channel IN ('auto', 'whatsapp', 'email', 'sms')",
            name="automation_rule_channel_valid",
        ),
        sa.ForeignKeyConstraint(["workspace_id"], ["workspaces.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id", name="pk_automation_rules"),
        sa.UniqueConstraint("workspace_id", "key", name="uq_automation_rules_workspace_key"),
    )
    op.create_index("ix_automation_rules_workspace_id", "automation_rules", ["workspace_id"])
    op.create_index(
        "ix_automation_rules_workspace_enabled", "automation_rules", ["workspace_id", "enabled"]
    )

    op.create_table(
        "automation_workers",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("workspace_id", sa.Uuid(), nullable=False),
        sa.Column("name", sa.String(length=120), nullable=False),
        sa.Column("token_hash", sa.String(length=64), nullable=False),
        sa.Column("status", sa.String(length=20), server_default="active", nullable=False),
        sa.Column("created_by_user_id", sa.Uuid(), nullable=True),
        sa.Column("last_seen_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.CheckConstraint(
            "status IN ('active', 'paused', 'revoked')",
            name="automation_worker_status_valid",
        ),
        sa.ForeignKeyConstraint(["workspace_id"], ["workspaces.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["created_by_user_id"], ["users.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id", name="pk_automation_workers"),
        sa.UniqueConstraint("token_hash", name="uq_automation_workers_token_hash"),
    )
    op.create_index("ix_automation_workers_workspace_id", "automation_workers", ["workspace_id"])
    op.create_index(
        "ix_automation_workers_workspace_status", "automation_workers", ["workspace_id", "status"]
    )

    op.create_table(
        "automation_jobs",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("workspace_id", sa.Uuid(), nullable=False),
        sa.Column("rule_id", sa.Uuid(), nullable=False),
        sa.Column("appointment_id", sa.Uuid(), nullable=False),
        sa.Column("patient_id", sa.Uuid(), nullable=False),
        sa.Column("status", sa.String(length=20), server_default="queued", nullable=False),
        sa.Column("scheduled_for", sa.DateTime(timezone=True), nullable=False),
        sa.Column("dedupe_key", sa.String(length=255), nullable=False),
        sa.Column("attempts", sa.Integer(), server_default="0", nullable=False),
        sa.Column("locked_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("next_attempt_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("message_id", sa.Uuid(), nullable=True),
        sa.Column("dispatch_id", sa.Uuid(), nullable=True),
        sa.Column("last_error", sa.Text(), nullable=True),
        sa.Column(
            "payload",
            postgresql.JSONB(astext_type=sa.Text()),
            server_default=sa.text("'{}'::jsonb"),
            nullable=False,
        ),
        sa.Column(
            "result",
            postgresql.JSONB(astext_type=sa.Text()),
            server_default=sa.text("'{}'::jsonb"),
            nullable=False,
        ),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.CheckConstraint(
            "status IN ('queued', 'processing', 'dispatched', 'skipped', 'failed', 'cancelled')",
            name="automation_job_status_valid",
        ),
        sa.ForeignKeyConstraint(
            ["workspace_id", "appointment_id"],
            ["appointments.workspace_id", "appointments.id"],
            ondelete="CASCADE",
            name="fk_automation_jobs_appointment",
        ),
        sa.ForeignKeyConstraint(
            ["workspace_id", "patient_id"],
            ["patients.workspace_id", "patients.id"],
            ondelete="CASCADE",
            name="fk_automation_jobs_patient",
        ),
        sa.ForeignKeyConstraint(["rule_id"], ["automation_rules.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["message_id"], ["messages.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["dispatch_id"], ["message_dispatches.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id", name="pk_automation_jobs"),
    )
    op.create_index("ix_automation_jobs_workspace_id", "automation_jobs", ["workspace_id"])
    op.create_index("ix_automation_jobs_rule_id", "automation_jobs", ["rule_id"])
    op.create_index("ix_automation_jobs_appointment_id", "automation_jobs", ["appointment_id"])
    op.create_index("ix_automation_jobs_patient_id", "automation_jobs", ["patient_id"])
    op.create_index("ix_automation_jobs_message_id", "automation_jobs", ["message_id"])
    op.create_index("ix_automation_jobs_dispatch_id", "automation_jobs", ["dispatch_id"])
    op.create_index(
        "uq_automation_jobs_workspace_dedupe",
        "automation_jobs",
        ["workspace_id", "dedupe_key"],
        unique=True,
    )
    op.create_index(
        "ix_automation_jobs_workspace_due",
        "automation_jobs",
        ["workspace_id", "status", "scheduled_for", "next_attempt_at"],
    )

    bind = op.get_bind()
    workspace_ids = [row[0] for row in bind.execute(sa.text("SELECT id FROM workspaces")).all()]
    rules_table = sa.table(
        "automation_rules",
        sa.column("id", sa.Uuid()),
        sa.column("workspace_id", sa.Uuid()),
        sa.column("key", sa.String()),
        sa.column("name", sa.String()),
        sa.column("enabled", sa.Boolean()),
        sa.column("trigger_kind", sa.String()),
        sa.column("offset_minutes", sa.Integer()),
        sa.column("channel", sa.String()),
        sa.column("template_name", sa.String()),
        sa.column("template_language", sa.String()),
        sa.column("max_lateness_minutes", sa.Integer()),
        sa.column("config", postgresql.JSONB()),
    )
    rows = []
    for workspace_id in workspace_ids:
        for key, name, trigger_kind, offset, template_name, language, max_lateness in DEFAULT_RULES:
            rows.append(
                {
                    "id": uuid4(),
                    "workspace_id": workspace_id,
                    "key": key,
                    "name": name,
                    "enabled": False,
                    "trigger_kind": trigger_kind,
                    "offset_minutes": offset,
                    "channel": "whatsapp",
                    "template_name": template_name,
                    "template_language": language,
                    "max_lateness_minutes": max_lateness,
                    "config": {},
                }
            )
    if rows:
        op.bulk_insert(rules_table, rows)

    for table in ("automation_rules", "automation_workers", "automation_jobs"):
        op.execute(sa.text(f'ALTER TABLE public."{table}" ENABLE ROW LEVEL SECURITY'))
        op.execute(sa.text(f'REVOKE ALL ON TABLE public."{table}" FROM anon, authenticated'))


def downgrade() -> None:
    op.drop_index("ix_automation_jobs_workspace_due", table_name="automation_jobs")
    op.drop_index("uq_automation_jobs_workspace_dedupe", table_name="automation_jobs")
    op.drop_index("ix_automation_jobs_dispatch_id", table_name="automation_jobs")
    op.drop_index("ix_automation_jobs_message_id", table_name="automation_jobs")
    op.drop_index("ix_automation_jobs_patient_id", table_name="automation_jobs")
    op.drop_index("ix_automation_jobs_appointment_id", table_name="automation_jobs")
    op.drop_index("ix_automation_jobs_rule_id", table_name="automation_jobs")
    op.drop_index("ix_automation_jobs_workspace_id", table_name="automation_jobs")
    op.drop_table("automation_jobs")

    op.drop_index("ix_automation_workers_workspace_status", table_name="automation_workers")
    op.drop_index("ix_automation_workers_workspace_id", table_name="automation_workers")
    op.drop_table("automation_workers")

    op.drop_index("ix_automation_rules_workspace_enabled", table_name="automation_rules")
    op.drop_index("ix_automation_rules_workspace_id", table_name="automation_rules")
    op.drop_table("automation_rules")
