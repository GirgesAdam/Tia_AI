"""Harden service package offers against Supabase Data API access.

Revision ID: 0069_service_package_offers_rls
Revises: 0068_visit_group_id
Create Date: 2026-09-13
"""

from __future__ import annotations

import sqlalchemy as sa

from alembic import op

revision = "0069_service_package_offers_rls"
down_revision = "0068_visit_group_id"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Package offers are backend-owned business data. Browser/Supabase Data API
    # clients must not bypass FastAPI workspace authorization or read pricing
    # configuration directly.
    op.execute(sa.text("ALTER TABLE public.service_package_offers ENABLE ROW LEVEL SECURITY"))
    op.execute(sa.text("REVOKE ALL ON TABLE public.service_package_offers FROM anon, authenticated"))


def downgrade() -> None:
    # Match the backend-only security downgrade convention: remove RLS without
    # restoring Data API privileges that were intentionally revoked.
    op.execute(sa.text("ALTER TABLE public.service_package_offers DISABLE ROW LEVEL SECURITY"))
