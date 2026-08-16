from datetime import datetime, timezone
from pathlib import Path
from types import SimpleNamespace

from app.models.message_dispatch import MESSAGE_DISPATCH_STATUSES
from app.schemas.channel import DispatchResultRequest, ProviderStatusRequest
from app.core.channel_delivery import apply_provider_delivery_status, delivery_rank


def test_dispatch_state_supports_read_receipts() -> None:
    assert "read" in MESSAGE_DISPATCH_STATUSES
    assert delivery_rank("sent") < delivery_rank("delivered") < delivery_rank("read")


def test_provider_status_schema_normalizes_ids() -> None:
    payload = ProviderStatusRequest(
        external_event_id=" status:wamid:read:123 ",
        provider_message_id=" wamid.abc ",
        status="read",
    )
    assert payload.external_event_id == "status:wamid:read:123"
    assert payload.provider_message_id == "wamid.abc"


def test_dispatch_result_accepts_read() -> None:
    payload = DispatchResultRequest(
        status="read",
        provider_message_id="wamid.abc",
    )
    assert payload.status == "read"


def test_delivery_status_never_downgrades() -> None:
    dispatch = SimpleNamespace(
        status="delivered",
        metadata_json={},
        last_error=None,
        next_attempt_at=None,
        locked_at=None,
        sent_at=datetime(2026, 8, 13, 0, 0, tzinfo=timezone.utc),
        delivered_at=datetime(2026, 8, 13, 0, 1, tzinfo=timezone.utc),
        read_at=None,
    )
    message = SimpleNamespace(delivery_status="delivered")

    apply_provider_delivery_status(
        dispatch=dispatch,
        message=message,
        provider_status="sent",
        occurred_at=datetime(2026, 8, 13, 0, 2, tzinfo=timezone.utc),
        error=None,
        metadata={},
    )

    assert dispatch.status == "delivered"
    assert message.delivery_status == "delivered"


def test_read_receipt_advances_dispatch_and_message() -> None:
    dispatch = SimpleNamespace(
        status="sent",
        metadata_json={},
        last_error=None,
        next_attempt_at=None,
        locked_at=None,
        sent_at=datetime(2026, 8, 13, 0, 0, tzinfo=timezone.utc),
        delivered_at=None,
        read_at=None,
    )
    message = SimpleNamespace(delivery_status="sent")
    occurred_at = datetime(2026, 8, 13, 0, 3, tzinfo=timezone.utc)

    apply_provider_delivery_status(
        dispatch=dispatch,
        message=message,
        provider_status="read",
        occurred_at=occurred_at,
        error=None,
        metadata={"provider": "meta_cloud"},
    )

    assert dispatch.status == "read"
    assert message.delivery_status == "read"
    assert dispatch.read_at == occurred_at
    assert dispatch.delivered_at == occurred_at


def test_late_failure_does_not_override_delivered() -> None:
    dispatch = SimpleNamespace(
        status="delivered",
        metadata_json={},
        last_error=None,
        next_attempt_at=None,
        locked_at=None,
        sent_at=datetime(2026, 8, 13, 0, 0, tzinfo=timezone.utc),
        delivered_at=datetime(2026, 8, 13, 0, 1, tzinfo=timezone.utc),
        read_at=None,
    )
    message = SimpleNamespace(delivery_status="delivered")

    apply_provider_delivery_status(
        dispatch=dispatch,
        message=message,
        provider_status="failed",
        occurred_at=datetime(2026, 8, 13, 0, 2, tzinfo=timezone.utc),
        error="late provider failure",
        metadata={},
    )

    assert dispatch.status == "delivered"
    assert message.delivery_status == "delivered"


def test_n8n_workflow_templates_are_present() -> None:
    project_root = Path(__file__).resolve().parents[2]
    inbound = project_root / "n8n/workflows/tia_whatsapp_inbound_status.json"
    outbox = project_root / "n8n/workflows/tia_whatsapp_outbox_worker.json"
    assert inbound.is_file()
    assert outbox.is_file()
    assert "n8n-nodes-base.whatsAppTrigger" in inbound.read_text(encoding="utf-8")
    assert "n8n-nodes-base.whatsApp" in outbox.read_text(encoding="utf-8")
