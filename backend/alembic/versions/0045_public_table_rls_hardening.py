"""Harden backend-owned public tables against Supabase Data API access.

Revision ID: 0045_public_table_rls_hardening
Revises: 0044_campaign_analytics_tracking
Create Date: 2026-08-30
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "0045_public_table_rls_hardening"
down_revision: str | None = "0044_campaign_analytics_tracking"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


BACKEND_ONLY_PUBLIC_TABLES = (
    "activity_events",
    "clinic_integration_entity_links",
    "clinic_integration_sync_checkpoints",
    "clinic_integration_sync_failures",
    "clinic_integration_sync_runs",
    "clinic_integration_sync_schedules",
    "clinic_integrations",
    "crm_campaign_recipients",
    "crm_campaigns",
    "crm_cohort_members",
    "crm_cohorts",
    "crm_tasks",
    "payment_allocations",
    "payment_transactions",
)


def upgrade() -> None:
    # These tables are owned by the FastAPI backend. Browser/Supabase Data API
    # clients must not be able to bypass workspace authorization in FastAPI.
    for table in BACKEND_ONLY_PUBLIC_TABLES:
        op.execute(sa.text(f'ALTER TABLE public."{table}" ENABLE ROW LEVEL SECURITY'))
        op.execute(sa.text(f'REVOKE ALL ON TABLE public."{table}" FROM anon, authenticated'))


def downgrade() -> None:
    # Match the project's existing security-migration downgrade convention:
    # disable RLS, but do not restore Data API privileges that were revoked.
    for table in BACKEND_ONLY_PUBLIC_TABLES:
        op.execute(sa.text(f'ALTER TABLE public."{table}" DISABLE ROW LEVEL SECURITY'))
