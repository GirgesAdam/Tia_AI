from types import SimpleNamespace
from uuid import uuid4

from app.api.routes import whatsapp_setup
from app.core.config import settings
from app.models.workspace import Workspace
from app.services import meta_whatsapp_transport as transport


def test_transport_route_is_not_globally_disabled_by_legacy_demo_env(monkeypatch):
    expected = {
        "connections_checked": 1,
        "connections_ready": 1,
        "provider_refreshes": 0,
        "inbound_processed": 0,
        "inbound_failed": 0,
        "sent": 0,
        "send_failed": 0,
    }
    called = False

    def fake_tick(db, *, limit_per_connection, max_connections):
        nonlocal called
        called = True
        assert limit_per_connection == 3
        assert max_connections == 4
        return expected

    monkeypatch.setattr(settings, "demo_mode", True)
    monkeypatch.setattr(settings, "demo_allow_external_dispatch", False)
    monkeypatch.setattr(whatsapp_setup, "run_meta_transport_tick", fake_tick)
    result = whatsapp_setup.whatsapp_transport_tick(
        _worker=None, db=object(), limit_per_connection=3, max_connections=4
    )
    assert called is True
    assert result == expected


class FakeDB:
    def __init__(self, connections, workspaces):
        self.connections = connections
        self.workspaces = workspaces

    def scalars(self, _statement):
        return self.connections

    def get(self, model, key):
        assert model is Workspace
        return self.workspaces.get(key)


def test_native_worker_processes_demo_and_production_independently(monkeypatch):
    demo_workspace_id = uuid4()
    prod_workspace_id = uuid4()
    demo_connection = SimpleNamespace(
        id=uuid4(), workspace_id=demo_workspace_id, status="active",
        config_json={}, created_at=None,
    )
    prod_connection = SimpleNamespace(
        id=uuid4(), workspace_id=prod_workspace_id, status="active",
        config_json={"transport_ready": True}, created_at=None,
    )
    db = FakeDB(
        [demo_connection, prod_connection],
        {
            demo_workspace_id: SimpleNamespace(is_demo=True),
            prod_workspace_id: SimpleNamespace(is_demo=False),
        },
    )
    processed = []
    refreshed = []
    cancelled = []
    claimed = []
    sent = []

    monkeypatch.setattr(transport, "_required_template_names", lambda db, c: [])
    monkeypatch.setattr(transport, "_readiness_refresh_due", lambda *a, **k: True)
    def refresh(db, connection):
        refreshed.append(connection.id)
        return True
    monkeypatch.setattr(transport, "refresh_meta_connection_readiness", refresh)
    def process(db, connection, *, limit):
        processed.append(connection.id)
        return (1, 0)
    monkeypatch.setattr(transport, "_process_pending_inbound", process)
    monkeypatch.setattr(
        transport, "_cancel_expired_automation_dispatches",
        lambda db, *, connection: cancelled.append(connection.id) or 0,
    )
    monkeypatch.setattr(transport, "_decrypt_connection_token", lambda db, c: ("token", None))
    item = SimpleNamespace(dispatch_id=uuid4())
    def claim(db, *, connection, limit, approved_template_names):
        claimed.append(connection.id)
        return [item]
    monkeypatch.setattr(transport, "claim_dispatches", claim)
    def send(db, *, connection, token, item):
        sent.append(connection.id)
        return True
    monkeypatch.setattr(transport, "_send_claimed_dispatch", send)

    result = transport.run_meta_transport_tick(db, limit_per_connection=2, max_connections=5)

    assert processed == [demo_connection.id, prod_connection.id]
    assert cancelled == [demo_connection.id, prod_connection.id]
    assert refreshed == [prod_connection.id]
    assert claimed == [prod_connection.id]
    assert sent == [prod_connection.id]
    assert result == {
        "connections_checked": 2, "connections_ready": 1, "provider_refreshes": 1,
        "inbound_processed": 2, "inbound_failed": 0, "sent": 1, "send_failed": 0,
    }
