"""CRM core tables.

Revision ID: 0005_crm_core
Revises: 0004_admin_member_roles
Create Date: 2026-08-12
"""

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision: str = "0005_crm_core"
down_revision: str | Sequence[str] | None = "0004_admin_member_roles"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

CRM_TABLES = (
    "patients",
    "patient_tags",
    "patient_tag_assignments",
    "patient_notes",
    "leads",
    "conversations",
    "messages",
)


def upgrade() -> None:
    op.create_table(
        "patients",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("workspace_id", sa.Uuid(), nullable=False),
        sa.Column("first_name", sa.String(length=120), nullable=False),
        sa.Column("last_name", sa.String(length=120), nullable=True),
        sa.Column("phone", sa.String(length=40), nullable=True),
        sa.Column("phone_normalized", sa.String(length=40), nullable=True),
        sa.Column("email", sa.String(length=320), nullable=True),
        sa.Column("gender", sa.String(length=32), nullable=True),
        sa.Column("birth_date", sa.Date(), nullable=True),
        sa.Column("preferred_language", sa.String(length=10), server_default="ar", nullable=False),
        sa.Column("preferred_branch_id", sa.Uuid(), nullable=True),
        sa.Column("source", sa.String(length=32), server_default="other", nullable=False),
        sa.Column("source_detail", sa.String(length=200), nullable=True),
        sa.Column("status", sa.String(length=20), server_default="active", nullable=False),
        sa.Column("marketing_consent", sa.Boolean(), server_default=sa.false(), nullable=False),
        sa.Column("marketing_consent_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_contact_at", sa.DateTime(timezone=True), nullable=True),
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
            "status IN ('active', 'inactive', 'blocked')",
            name=op.f("ck_patients_patient_status_valid"),
        ),
        sa.CheckConstraint(
            "source IN ('whatsapp', 'instagram', 'facebook', 'website', 'referral', "
            "'walk_in', 'campaign', 'phone', 'email', 'other')",
            name=op.f("ck_patients_patient_source_valid"),
        ),
        sa.ForeignKeyConstraint(["workspace_id"], ["workspaces.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(
            ["workspace_id", "preferred_branch_id"],
            ["branches.workspace_id", "branches.id"],
            name="fk_patients_preferred_branch",
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("workspace_id", "id", name="uq_patients_workspace_id_id"),
    )
    op.create_index("ix_patients_workspace_id", "patients", ["workspace_id"])
    op.create_index("ix_patients_preferred_branch_id", "patients", ["preferred_branch_id"])
    op.create_index("ix_patients_last_contact_at", "patients", ["last_contact_at"])
    op.create_index("ix_patients_workspace_status", "patients", ["workspace_id", "status"])
    op.create_index("ix_patients_workspace_source", "patients", ["workspace_id", "source"])
    op.create_index(
        "uq_patients_workspace_phone_normalized",
        "patients",
        ["workspace_id", "phone_normalized"],
        unique=True,
        postgresql_where=sa.text("phone_normalized IS NOT NULL"),
    )

    op.create_table(
        "patient_tags",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("workspace_id", sa.Uuid(), nullable=False),
        sa.Column("name", sa.String(length=100), nullable=False),
        sa.Column("normalized_name", sa.String(length=100), nullable=False),
        sa.Column("color", sa.String(length=20), nullable=True),
        sa.Column("is_active", sa.Boolean(), server_default=sa.true(), nullable=False),
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
        sa.ForeignKeyConstraint(["workspace_id"], ["workspaces.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("workspace_id", "id", name="uq_patient_tags_workspace_id_id"),
        sa.UniqueConstraint(
            "workspace_id",
            "normalized_name",
            name="uq_patient_tags_workspace_normalized_name",
        ),
    )
    op.create_index("ix_patient_tags_workspace_id", "patient_tags", ["workspace_id"])

    op.create_table(
        "patient_tag_assignments",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("workspace_id", sa.Uuid(), nullable=False),
        sa.Column("patient_id", sa.Uuid(), nullable=False),
        sa.Column("tag_id", sa.Uuid(), nullable=False),
        sa.Column("created_by_user_id", sa.Uuid(), nullable=True),
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
        sa.ForeignKeyConstraint(
            ["workspace_id", "patient_id"],
            ["patients.workspace_id", "patients.id"],
            ondelete="CASCADE",
            name="fk_patient_tag_assignments_patient",
        ),
        sa.ForeignKeyConstraint(
            ["workspace_id", "tag_id"],
            ["patient_tags.workspace_id", "patient_tags.id"],
            ondelete="CASCADE",
            name="fk_patient_tag_assignments_tag",
        ),
        sa.ForeignKeyConstraint(["created_by_user_id"], ["users.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "workspace_id",
            "patient_id",
            "tag_id",
            name="uq_patient_tag_assignments_patient_tag",
        ),
    )
    op.create_index(
        "ix_patient_tag_assignments_workspace_id",
        "patient_tag_assignments",
        ["workspace_id"],
    )
    op.create_index(
        "ix_patient_tag_assignments_patient_id",
        "patient_tag_assignments",
        ["patient_id"],
    )
    op.create_index("ix_patient_tag_assignments_tag_id", "patient_tag_assignments", ["tag_id"])

    op.create_table(
        "patient_notes",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("workspace_id", sa.Uuid(), nullable=False),
        sa.Column("patient_id", sa.Uuid(), nullable=False),
        sa.Column("author_user_id", sa.Uuid(), nullable=True),
        sa.Column("note_type", sa.String(length=32), server_default="general", nullable=False),
        sa.Column("content", sa.Text(), nullable=False),
        sa.Column("is_pinned", sa.Boolean(), server_default=sa.false(), nullable=False),
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
            "note_type IN ('general', 'preference', 'customer_service', 'follow_up')",
            name=op.f("ck_patient_notes_patient_note_type_valid"),
        ),
        sa.ForeignKeyConstraint(
            ["workspace_id", "patient_id"],
            ["patients.workspace_id", "patients.id"],
            ondelete="CASCADE",
            name="fk_patient_notes_patient",
        ),
        sa.ForeignKeyConstraint(["author_user_id"], ["users.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_patient_notes_workspace_id", "patient_notes", ["workspace_id"])
    op.create_index("ix_patient_notes_patient_id", "patient_notes", ["patient_id"])
    op.create_index("ix_patient_notes_author_user_id", "patient_notes", ["author_user_id"])

    op.create_table(
        "leads",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("workspace_id", sa.Uuid(), nullable=False),
        sa.Column("patient_id", sa.Uuid(), nullable=False),
        sa.Column("service_id", sa.Uuid(), nullable=True),
        sa.Column("assigned_user_id", sa.Uuid(), nullable=True),
        sa.Column("source", sa.String(length=32), nullable=False),
        sa.Column("status", sa.String(length=20), server_default="new", nullable=False),
        sa.Column("estimated_value_minor", sa.Integer(), nullable=True),
        sa.Column("currency", sa.String(length=3), server_default="EGP", nullable=False),
        sa.Column("lost_reason", sa.Text(), nullable=True),
        sa.Column("next_follow_up_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_contact_at", sa.DateTime(timezone=True), nullable=True),
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
            "source IN ('whatsapp', 'instagram', 'facebook', 'website', 'referral', "
            "'walk_in', 'campaign', 'phone', 'email', 'other')",
            name=op.f("ck_leads_lead_source_valid"),
        ),
        sa.CheckConstraint(
            "status IN ('new', 'contacted', 'qualified', 'booked', 'won', 'lost', 'spam')",
            name=op.f("ck_leads_lead_status_valid"),
        ),
        sa.CheckConstraint(
            "estimated_value_minor IS NULL OR estimated_value_minor >= 0",
            name=op.f("ck_leads_lead_estimated_value_non_negative"),
        ),
        sa.ForeignKeyConstraint(
            ["workspace_id", "patient_id"],
            ["patients.workspace_id", "patients.id"],
            ondelete="CASCADE",
            name="fk_leads_patient",
        ),
        sa.ForeignKeyConstraint(
            ["workspace_id", "service_id"],
            ["services.workspace_id", "services.id"],
            name="fk_leads_service",
        ),
        sa.ForeignKeyConstraint(["assigned_user_id"], ["users.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_leads_workspace_id", "leads", ["workspace_id"])
    op.create_index("ix_leads_patient_id", "leads", ["patient_id"])
    op.create_index("ix_leads_service_id", "leads", ["service_id"])
    op.create_index("ix_leads_assigned_user_id", "leads", ["assigned_user_id"])
    op.create_index("ix_leads_next_follow_up_at", "leads", ["next_follow_up_at"])

    op.create_table(
        "conversations",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("workspace_id", sa.Uuid(), nullable=False),
        sa.Column("patient_id", sa.Uuid(), nullable=False),
        sa.Column("channel", sa.String(length=24), nullable=False),
        sa.Column("status", sa.String(length=20), server_default="open", nullable=False),
        sa.Column("external_conversation_id", sa.String(length=255), nullable=True),
        sa.Column("assigned_user_id", sa.Uuid(), nullable=True),
        sa.Column("subject", sa.String(length=250), nullable=True),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("last_message_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("closed_at", sa.DateTime(timezone=True), nullable=True),
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
            "channel IN ('whatsapp', 'instagram', 'facebook', 'web', 'email', "
            "'sms', 'phone', 'other')",
            name=op.f("ck_conversations_conversation_channel_valid"),
        ),
        sa.CheckConstraint(
            "status IN ('open', 'pending', 'closed')",
            name=op.f("ck_conversations_conversation_status_valid"),
        ),
        sa.ForeignKeyConstraint(
            ["workspace_id", "patient_id"],
            ["patients.workspace_id", "patients.id"],
            ondelete="CASCADE",
            name="fk_conversations_patient",
        ),
        sa.ForeignKeyConstraint(["assigned_user_id"], ["users.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("workspace_id", "id", name="uq_conversations_workspace_id_id"),
    )
    op.create_index("ix_conversations_workspace_id", "conversations", ["workspace_id"])
    op.create_index("ix_conversations_patient_id", "conversations", ["patient_id"])
    op.create_index("ix_conversations_assigned_user_id", "conversations", ["assigned_user_id"])
    op.create_index("ix_conversations_last_message_at", "conversations", ["last_message_at"])
    op.create_index(
        "ix_conversations_workspace_status",
        "conversations",
        ["workspace_id", "status"],
    )
    op.create_index(
        "uq_conversations_workspace_channel_external",
        "conversations",
        ["workspace_id", "channel", "external_conversation_id"],
        unique=True,
        postgresql_where=sa.text("external_conversation_id IS NOT NULL"),
    )

    op.create_table(
        "messages",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("workspace_id", sa.Uuid(), nullable=False),
        sa.Column("conversation_id", sa.Uuid(), nullable=False),
        sa.Column("sender_type", sa.String(length=20), nullable=False),
        sa.Column("direction", sa.String(length=20), nullable=False),
        sa.Column("message_type", sa.String(length=32), server_default="text", nullable=False),
        sa.Column("content", sa.Text(), nullable=True),
        sa.Column("external_message_id", sa.String(length=255), nullable=True),
        sa.Column("delivery_status", sa.String(length=20), nullable=False),
        sa.Column("sent_by_user_id", sa.Uuid(), nullable=True),
        sa.Column(
            "metadata",
            postgresql.JSONB(astext_type=sa.Text()),
            server_default="{}",
            nullable=False,
        ),
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
            "sender_type IN ('patient', 'ai', 'staff', 'system')",
            name=op.f("ck_messages_message_sender_type_valid"),
        ),
        sa.CheckConstraint(
            "direction IN ('inbound', 'outbound', 'internal')",
            name=op.f("ck_messages_message_direction_valid"),
        ),
        sa.CheckConstraint(
            "delivery_status IN ('received', 'queued', 'sent', 'delivered', 'read', 'failed')",
            name=op.f("ck_messages_message_delivery_status_valid"),
        ),
        sa.ForeignKeyConstraint(
            ["workspace_id", "conversation_id"],
            ["conversations.workspace_id", "conversations.id"],
            ondelete="CASCADE",
            name="fk_messages_conversation",
        ),
        sa.ForeignKeyConstraint(["sent_by_user_id"], ["users.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_messages_workspace_id", "messages", ["workspace_id"])
    op.create_index("ix_messages_conversation_id", "messages", ["conversation_id"])
    op.create_index("ix_messages_sent_by_user_id", "messages", ["sent_by_user_id"])
    op.create_index(
        "ix_messages_conversation_created",
        "messages",
        ["conversation_id", "created_at"],
    )
    op.create_index(
        "ix_messages_workspace_external",
        "messages",
        ["workspace_id", "external_message_id"],
    )

    # CRM tables live in public because FastAPI uses the same PostgreSQL database.
    # Keep Supabase Data API clients from bypassing FastAPI workspace authorization.
    for table in CRM_TABLES:
        op.execute(sa.text(f'ALTER TABLE public."{table}" ENABLE ROW LEVEL SECURITY'))
        op.execute(sa.text(f'REVOKE ALL ON TABLE public."{table}" FROM anon, authenticated'))


def downgrade() -> None:
    op.drop_index("ix_messages_workspace_external", table_name="messages")
    op.drop_index("ix_messages_conversation_created", table_name="messages")
    op.drop_index("ix_messages_sent_by_user_id", table_name="messages")
    op.drop_index("ix_messages_conversation_id", table_name="messages")
    op.drop_index("ix_messages_workspace_id", table_name="messages")
    op.drop_table("messages")

    op.drop_index("uq_conversations_workspace_channel_external", table_name="conversations")
    op.drop_index("ix_conversations_workspace_status", table_name="conversations")
    op.drop_index("ix_conversations_last_message_at", table_name="conversations")
    op.drop_index("ix_conversations_assigned_user_id", table_name="conversations")
    op.drop_index("ix_conversations_patient_id", table_name="conversations")
    op.drop_index("ix_conversations_workspace_id", table_name="conversations")
    op.drop_table("conversations")

    op.drop_index("ix_leads_next_follow_up_at", table_name="leads")
    op.drop_index("ix_leads_assigned_user_id", table_name="leads")
    op.drop_index("ix_leads_service_id", table_name="leads")
    op.drop_index("ix_leads_patient_id", table_name="leads")
    op.drop_index("ix_leads_workspace_id", table_name="leads")
    op.drop_table("leads")

    op.drop_index("ix_patient_notes_author_user_id", table_name="patient_notes")
    op.drop_index("ix_patient_notes_patient_id", table_name="patient_notes")
    op.drop_index("ix_patient_notes_workspace_id", table_name="patient_notes")
    op.drop_table("patient_notes")

    op.drop_index("ix_patient_tag_assignments_tag_id", table_name="patient_tag_assignments")
    op.drop_index("ix_patient_tag_assignments_patient_id", table_name="patient_tag_assignments")
    op.drop_index("ix_patient_tag_assignments_workspace_id", table_name="patient_tag_assignments")
    op.drop_table("patient_tag_assignments")

    op.drop_index("ix_patient_tags_workspace_id", table_name="patient_tags")
    op.drop_table("patient_tags")

    op.drop_index("uq_patients_workspace_phone_normalized", table_name="patients")
    op.drop_index("ix_patients_workspace_source", table_name="patients")
    op.drop_index("ix_patients_workspace_status", table_name="patients")
    op.drop_index("ix_patients_last_contact_at", table_name="patients")
    op.drop_index("ix_patients_preferred_branch_id", table_name="patients")
    op.drop_index("ix_patients_workspace_id", table_name="patients")
    op.drop_table("patients")
