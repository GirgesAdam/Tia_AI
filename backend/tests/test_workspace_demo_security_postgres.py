"""PostgreSQL evidence for multi-tenant production isolation."""

import os
from uuid import uuid4

import pytest
from fastapi import HTTPException
from sqlalchemy import create_engine, text
from sqlalchemy.engine import make_url
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.api.dependencies.security import get_workspace_access
from app.models.channel_connection import ChannelConnection
from app.models.user import User
from app.models.workspace import Workspace
from app.models.workspace_member import WorkspaceMember


def _engine():
    url = make_url(os.environ["DATABASE_URL"])
    if url.host not in {"localhost", "127.0.0.1", "::1"} or url.database != "ci_db":
        pytest.fail("Tenant-isolation PostgreSQL gate requires disposable local ci_db.")
    return create_engine(url, connect_args={"connect_timeout": 3})


def test_workspace_scoped_tables_are_not_directly_crudable_by_supabase_browser_roles():
    engine = _engine()
    try:
        with engine.connect() as conn:
            tables = conn.execute(text("""
                SELECT table_name FROM information_schema.columns
                WHERE table_schema='public' AND column_name='workspace_id'
                ORDER BY table_name
            """)).scalars().all()
            assert tables
            for table in tables:
                rls = conn.execute(
                    text("""
                        SELECT c.relrowsecurity
                        FROM pg_class c JOIN pg_namespace n ON n.oid=c.relnamespace
                        WHERE n.nspname='public' AND c.relname=:table
                    """), {"table": table}
                ).scalar_one()
                assert rls is True, table
                qualified = f"public.{table}"
                for role in ("anon", "authenticated"):
                    for privilege in ("SELECT", "INSERT", "UPDATE", "DELETE"):
                        allowed = conn.execute(
                            text("SELECT has_table_privilege(:role, :table, :privilege)"),
                            {"role": role, "table": qualified, "privilege": privilege},
                        ).scalar_one()
                        assert allowed is False, (table, role, privilege)
    finally:
        engine.dispose()


def test_membership_gate_blocks_demo_and_real_users_from_each_others_workspace():
    engine = _engine()
    conn = engine.connect()
    outer = conn.begin()
    db = Session(bind=conn, join_transaction_mode="create_savepoint")
    try:
        demo = Workspace(name="Demo", slug=f"demo-{uuid4()}", is_demo=True)
        real = Workspace(name="Real", slug=f"real-{uuid4()}", is_demo=False)
        demo_user = User(email=f"demo-{uuid4()}@example.test", auth_user_id=uuid4())
        real_user = User(email=f"real-{uuid4()}@example.test", auth_user_id=uuid4())
        db.add_all([demo, real, demo_user, real_user])
        db.flush()
        db.add_all([
            WorkspaceMember(workspace_id=demo.id, user_id=demo_user.id, role="admin"),
            WorkspaceMember(workspace_id=real.id, user_id=real_user.id, role="admin"),
        ])
        db.commit()

        assert get_workspace_access(x_workspace_id=demo.id, user=demo_user, db=db).workspace.id == demo.id
        assert get_workspace_access(x_workspace_id=real.id, user=real_user, db=db).workspace.id == real.id
        with pytest.raises(HTTPException) as demo_to_real:
            get_workspace_access(x_workspace_id=real.id, user=demo_user, db=db)
        with pytest.raises(HTTPException) as real_to_demo:
            get_workspace_access(x_workspace_id=demo.id, user=real_user, db=db)
        assert demo_to_real.value.status_code == 403
        assert real_to_demo.value.status_code == 403
    finally:
        db.close()
        if outer.is_active:
            outer.rollback()
        conn.close()
        engine.dispose()


def test_active_meta_phone_number_cannot_be_shared_across_workspaces():
    engine = _engine()
    conn = engine.connect()
    outer = conn.begin()
    db = Session(bind=conn, join_transaction_mode="create_savepoint")
    try:
        a = Workspace(name="Clinic A", slug=f"clinic-a-{uuid4()}")
        b = Workspace(name="Clinic B", slug=f"clinic-b-{uuid4()}")
        db.add_all([a, b])
        db.flush()
        external_id = f"phone-{uuid4()}"
        db.add(ChannelConnection(
            workspace_id=a.id, channel="whatsapp", provider="meta_cloud",
            display_name="A", status="active", external_account_id=external_id,
            adapter_token_hash=uuid4().hex + uuid4().hex, config_json={},
        ))
        db.commit()
        db.add(ChannelConnection(
            workspace_id=b.id, channel="whatsapp", provider="meta_cloud",
            display_name="B", status="active", external_account_id=external_id,
            adapter_token_hash=uuid4().hex + uuid4().hex, config_json={},
        ))
        with pytest.raises(IntegrityError):
            db.commit()
        db.rollback()
    finally:
        db.close()
        if outer.is_active:
            outer.rollback()
        conn.close()
        engine.dispose()
