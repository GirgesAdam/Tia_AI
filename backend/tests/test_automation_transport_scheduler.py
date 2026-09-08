from pathlib import Path


def _root() -> Path:
    return Path(__file__).resolve().parents[2]


def test_automation_scheduler_drains_native_whatsapp_outbox_per_workspace() -> None:
    root = _root()
    routes = (root / "backend/app/api/routes/automations.py").read_text(encoding="utf-8")
    transport = (
        root / "backend/app/services/meta_whatsapp_transport.py"
    ).read_text(encoding="utf-8")

    assert "from app.services.meta_whatsapp_transport import run_meta_transport_tick" in routes
    assert routes.count("run_meta_transport_tick(") >= 2
    assert "workspace_id=workspace_id" in routes
    assert "workspace_id=worker_access.worker.workspace_id" in routes
    assert "workspace_id: UUID | None = None" in transport
    assert "ChannelConnection.workspace_id == workspace_id" in transport


def test_transport_scope_is_optional_for_platform_transport_endpoint() -> None:
    transport = (
        _root() / "backend/app/services/meta_whatsapp_transport.py"
    ).read_text(encoding="utf-8")
    assert "if workspace_id is not None:" in transport
    assert "connection_stmt = connection_stmt.where" in transport
