from __future__ import annotations

from datetime import UTC, datetime, timedelta
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.message import Message

WHATSAPP_CUSTOMER_SERVICE_WINDOW = timedelta(hours=24)


def _as_utc(value: datetime) -> datetime:
    if value.tzinfo is None:
        return value.replace(tzinfo=UTC)
    return value.astimezone(UTC)


def latest_customer_inbound_at(
    db: Session,
    *,
    workspace_id: UUID,
    conversation_id: UUID,
) -> datetime | None:
    value = db.scalar(
        select(Message.created_at)
        .where(
            Message.workspace_id == workspace_id,
            Message.conversation_id == conversation_id,
            Message.sender_type == "patient",
            Message.direction == "inbound",
        )
        .order_by(Message.created_at.desc(), Message.id.desc())
        .limit(1)
    )
    return _as_utc(value) if isinstance(value, datetime) else None


def freeform_reply_expires_at(
    db: Session,
    *,
    workspace_id: UUID,
    conversation_id: UUID,
) -> datetime | None:
    inbound_at = latest_customer_inbound_at(
        db,
        workspace_id=workspace_id,
        conversation_id=conversation_id,
    )
    if inbound_at is None:
        return None
    return inbound_at + WHATSAPP_CUSTOMER_SERVICE_WINDOW


def freeform_reply_window_open(
    db: Session,
    *,
    workspace_id: UUID,
    conversation_id: UUID,
    now: datetime | None = None,
) -> bool:
    expires_at = freeform_reply_expires_at(
        db,
        workspace_id=workspace_id,
        conversation_id=conversation_id,
    )
    if expires_at is None:
        return False
    current = _as_utc(now) if isinstance(now, datetime) else datetime.now(UTC)
    return current < expires_at
