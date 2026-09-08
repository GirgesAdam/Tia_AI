from datetime import UTC, datetime, timedelta
from pathlib import Path

from app.services.meta_whatsapp_transport import _automation_delivery_expired


def test_automation_delivery_expires_only_after_max_lateness_window() -> None:
    scheduled = datetime(2026, 9, 8, 14, 0, tzinfo=UTC)
    boundary = scheduled + timedelta(minutes=60)

    assert (
        _automation_delivery_expired(
            scheduled_for=scheduled,
            max_lateness_minutes=60,
            now=boundary,
        )
        is False
    )
    assert (
        _automation_delivery_expired(
            scheduled_for=scheduled,
            max_lateness_minutes=60,
            now=boundary + timedelta(seconds=1),
        )
        is True
    )


def test_transport_cancels_expired_automation_before_claiming_provider_send() -> None:
    backend = Path(__file__).resolve().parent.parent
    source = (backend / "app/services/meta_whatsapp_transport.py").read_text(encoding="utf-8")
    tick = source.split("def run_meta_transport_tick", 1)[1]

    cancel_index = tick.index("_cancel_expired_automation_dispatches")
    claim_index = tick.index("claim_dispatches")
    assert cancel_index < claim_index
    assert 'MessageDispatch.status == "queued"' in source
    assert 'AutomationJob.status == "dispatched"' in source
    assert '"reason": "expired_before_provider_send"' in source
