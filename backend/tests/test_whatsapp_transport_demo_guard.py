from app.api.routes import whatsapp_setup


def test_demo_transport_tick_fails_closed_before_native_transport(monkeypatch):
    called = False

    def fake_run_meta_transport_tick(*args, **kwargs):
        nonlocal called
        called = True
        raise AssertionError("native transport must not run while demo dispatch is disabled")

    monkeypatch.setattr(whatsapp_setup.settings, "demo_mode", True)
    monkeypatch.setattr(whatsapp_setup.settings, "demo_allow_external_dispatch", False)
    monkeypatch.setattr(whatsapp_setup, "run_meta_transport_tick", fake_run_meta_transport_tick)

    result = whatsapp_setup.whatsapp_transport_tick(
        _worker=None,
        db=object(),
        limit_per_connection=10,
        max_connections=25,
    )

    assert called is False
    assert result == {
        "connections_checked": 0,
        "connections_ready": 0,
        "provider_refreshes": 0,
        "inbound_processed": 0,
        "inbound_failed": 0,
        "sent": 0,
        "send_failed": 0,
    }


def test_demo_transport_tick_can_be_explicitly_enabled(monkeypatch):
    expected = {
        "connections_checked": 1,
        "connections_ready": 1,
        "provider_refreshes": 0,
        "inbound_processed": 0,
        "inbound_failed": 0,
        "sent": 1,
        "send_failed": 0,
    }

    def fake_run_meta_transport_tick(db, *, limit_per_connection, max_connections):
        assert limit_per_connection == 3
        assert max_connections == 4
        return expected

    monkeypatch.setattr(whatsapp_setup.settings, "demo_mode", True)
    monkeypatch.setattr(whatsapp_setup.settings, "demo_allow_external_dispatch", True)
    monkeypatch.setattr(whatsapp_setup, "run_meta_transport_tick", fake_run_meta_transport_tick)

    result = whatsapp_setup.whatsapp_transport_tick(
        _worker=None,
        db=object(),
        limit_per_connection=3,
        max_connections=4,
    )

    assert result == expected
