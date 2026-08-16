from __future__ import annotations

from datetime import datetime, timezone
from typing import Any


def delivery_rank(status: str) -> int:
    return {
        "queued": 0,
        "processing": 1,
        "failed": 1,
        "sent": 2,
        "delivered": 3,
        "read": 4,
        "cancelled": 99,
    }.get(status, -1)


def apply_provider_delivery_status(
    *,
    dispatch: Any,
    message: Any,
    provider_status: str,
    occurred_at: datetime | None,
    error: str | None,
    metadata: dict,
) -> None:
    now = datetime.now(timezone.utc)
    happened_at = occurred_at or now

    dispatch.metadata_json = {
        **(dispatch.metadata_json or {}),
        "provider_delivery": {
            "status": provider_status,
            "occurred_at": happened_at.isoformat(),
            **metadata,
        },
    }

    if dispatch.status == "cancelled":
        return

    if provider_status == "failed":
        # A late failure callback must never downgrade a message that the
        # provider already confirmed as delivered/read.
        if dispatch.status in {"delivered", "read"}:
            return
        dispatch.status = "failed"
        dispatch.last_error = (error or "Provider reported message delivery failure.")[:2000]
        dispatch.next_attempt_at = None
        dispatch.locked_at = None
        message.delivery_status = "failed"
        return

    if provider_status not in {"sent", "delivered", "read"}:
        raise ValueError("Unsupported provider delivery status.")

    if delivery_rank(dispatch.status) > delivery_rank(provider_status):
        return

    dispatch.status = provider_status
    dispatch.last_error = None
    dispatch.next_attempt_at = None
    dispatch.locked_at = None

    if provider_status == "sent":
        dispatch.sent_at = dispatch.sent_at or happened_at
        message.delivery_status = "sent"
    elif provider_status == "delivered":
        dispatch.sent_at = dispatch.sent_at or happened_at
        dispatch.delivered_at = dispatch.delivered_at or happened_at
        message.delivery_status = "delivered"
    elif provider_status == "read":
        dispatch.sent_at = dispatch.sent_at or happened_at
        dispatch.delivered_at = dispatch.delivered_at or happened_at
        dispatch.read_at = dispatch.read_at or happened_at
        message.delivery_status = "read"
