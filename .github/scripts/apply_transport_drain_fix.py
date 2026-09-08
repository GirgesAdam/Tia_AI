from pathlib import Path


def replace_once(path: Path, old: str, new: str) -> None:
    text = path.read_text(encoding="utf-8")
    if old not in text:
        raise SystemExit(f"Expected patch anchor not found in {path}: {old[:120]!r}")
    path.write_text(text.replace(old, new, 1), encoding="utf-8")


transport = Path("backend/app/services/meta_whatsapp_transport.py")
replace_once(
    transport,
    "from datetime import UTC, datetime, timedelta\nfrom typing import Any\n",
    "from datetime import UTC, datetime, timedelta\nfrom typing import Any\nfrom uuid import UUID\n",
)
replace_once(
    transport,
    "def run_meta_transport_tick(\n    db: Session,\n    *,\n    limit_per_connection: int = 10,\n    max_connections: int = 25,\n) -> dict[str, int]:\n    connections = list(\n        db.scalars(\n            select(ChannelConnection)\n            .where(\n                ChannelConnection.channel == \"whatsapp\",\n                ChannelConnection.provider == \"meta_cloud\",\n                ChannelConnection.status.in_((\"active\", \"paused\")),\n            )\n            .order_by(ChannelConnection.created_at)\n            .limit(max_connections)\n        )\n    )\n",
    "def run_meta_transport_tick(\n    db: Session,\n    *,\n    limit_per_connection: int = 10,\n    max_connections: int = 25,\n    workspace_id: UUID | None = None,\n) -> dict[str, int]:\n    connection_stmt = select(ChannelConnection).where(\n        ChannelConnection.channel == \"whatsapp\",\n        ChannelConnection.provider == \"meta_cloud\",\n        ChannelConnection.status.in_((\"active\", \"paused\")),\n    )\n    if workspace_id is not None:\n        connection_stmt = connection_stmt.where(ChannelConnection.workspace_id == workspace_id)\n    connections = list(\n        db.scalars(\n            connection_stmt.order_by(ChannelConnection.created_at).limit(max_connections)\n        )\n    )\n",
)

routes = Path("backend/app/api/routes/automations.py")
replace_once(
    routes,
    "from app.services.clinic_integration_sync_runtime import run_scheduled_sync_tick\n",
    "from app.services.clinic_integration_sync_runtime import run_scheduled_sync_tick\nfrom app.services.meta_whatsapp_transport import run_meta_transport_tick\n",
)
replace_once(
    routes,
    "    workspace_id = worker_access.worker.workspace_id\n    planning = plan_automation_jobs(\n",
    "    workspace_id = worker_access.worker.workspace_id\n    # The existing once-per-minute automation scheduler also drains this workspace's\n    # native Meta outbox. This keeps WhatsApp delivery alive without requiring a\n    # second external scheduler/workflow.\n    run_meta_transport_tick(\n        db,\n        workspace_id=workspace_id,\n        limit_per_connection=min(payload.limit, 50),\n        max_connections=25,\n    )\n    planning = plan_automation_jobs(\n",
)
replace_once(
    routes,
    "    except AutomationError as exc:\n        raise HTTPException(status_code=409, detail=str(exc)) from exc\n\n    job = result.job\n",
    "    except AutomationError as exc:\n        raise HTTPException(status_code=409, detail=str(exc)) from exc\n\n    # Automation execution can enqueue a WhatsApp dispatch. Drain immediately so\n    # the user does not wait for the next minute tick; the next scheduler tick is\n    # still a durable fallback for any queued outbound work.\n    run_meta_transport_tick(\n        db,\n        workspace_id=worker_access.worker.workspace_id,\n        limit_per_connection=10,\n        max_connections=25,\n    )\n\n    job = result.job\n",
)

test = Path("backend/tests/test_automation_transport_scheduler.py")
test.write_text(
    '''from pathlib import Path\n\n\ndef _root() -> Path:\n    return Path(__file__).resolve().parents[2]\n\n\ndef test_automation_scheduler_drains_native_whatsapp_outbox_per_workspace() -> None:\n    root = _root()\n    routes = (root / "backend/app/api/routes/automations.py").read_text(encoding="utf-8")\n    transport = (\n        root / "backend/app/services/meta_whatsapp_transport.py"\n    ).read_text(encoding="utf-8")\n\n    assert "from app.services.meta_whatsapp_transport import run_meta_transport_tick" in routes\n    assert routes.count("run_meta_transport_tick(") >= 2\n    assert "workspace_id=workspace_id" in routes\n    assert "workspace_id=worker_access.worker.workspace_id" in routes\n    assert "workspace_id: UUID | None = None" in transport\n    assert "ChannelConnection.workspace_id == workspace_id" in transport\n\n\ndef test_transport_scope_is_optional_for_platform_transport_endpoint() -> None:\n    transport = (\n        _root() / "backend/app/services/meta_whatsapp_transport.py"\n    ).read_text(encoding="utf-8")\n    assert "if workspace_id is not None:" in transport\n    assert "connection_stmt = connection_stmt.where" in transport\n''',
    encoding="utf-8",
)

docs = Path("n8n/AUTOMATIONS_SETUP.md")
text = docs.read_text(encoding="utf-8")
marker = "## WhatsApp transport worker\n"
if marker in text and "automation scheduler also drains" not in text:
    text = text.replace(
        marker,
        "## WhatsApp transport worker\n\nThe active Tia automation scheduler also drains the native Meta outbox for its own workspace on every tick, and immediately after an automation job enqueues a WhatsApp dispatch. This is the production fallback that prevents a clinic automation from appearing active while messages remain queued just because a separate transport workflow was not enabled.\n\n",
        1,
    )
    docs.write_text(text, encoding="utf-8")
