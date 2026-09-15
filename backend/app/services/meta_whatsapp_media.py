from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.models.channel_connection import ChannelConnection
from app.models.channel_inbound_event import ChannelInboundEvent
from app.models.message import Message
from app.schemas.channel import NormalizedInboundMessage
from app.services.channels import (
    ChannelConflictError,
    _next_conversation_activity_at,
    _resolve_conversation,
    _resolve_identity,
)
from app.services.conversation_ownership import record_customer_inbound
from app.services.handoffs import create_handoff

_MEDIA_TYPES = frozenset({"image", "audio", "video", "document", "sticker"})
_MEDIA_METADATA_KEYS = (
    "id",
    "mime_type",
    "sha256",
    "filename",
    "caption",
    "voice",
    "animated",
)


@dataclass(frozen=True)
class MetaMediaInbound:
    external_event_id: str
    external_message_id: str
    external_user_id: str
    external_conversation_id: str
    display_name: str | None
    phone: str
    message_type: str
    content: str | None
    metadata: dict[str, Any]


def _display_name_for_sender(contacts: list[Any], sender: str) -> str | None:
    for contact in contacts:
        if not isinstance(contact, dict):
            continue
        if str(contact.get("wa_id") or "") not in {"", sender}:
            continue
        profile = contact.get("profile")
        if isinstance(profile, dict):
            name = str(profile.get("name") or "").strip()
            if name:
                return name[:200]
    return None


def _safe_media_metadata(detail: dict[str, Any]) -> dict[str, Any]:
    media: dict[str, Any] = {}
    for key in _MEDIA_METADATA_KEYS:
        value = detail.get(key)
        if value is None or value == "":
            continue
        if key in {"voice", "animated"}:
            media[key] = bool(value)
        else:
            media[key] = str(value)[:2000]
    return media


def normalize_meta_media(value: dict[str, Any]) -> list[MetaMediaInbound]:
    contacts = value.get("contacts") if isinstance(value.get("contacts"), list) else []
    messages = value.get("messages") if isinstance(value.get("messages"), list) else []
    phone_number_id = str((value.get("metadata") or {}).get("phone_number_id") or "").strip()
    normalized: list[MetaMediaInbound] = []

    for message in messages:
        if not isinstance(message, dict):
            continue
        message_type = str(message.get("type") or "").strip().lower()
        if message_type not in _MEDIA_TYPES:
            continue
        detail = message.get(message_type)
        if not isinstance(detail, dict):
            continue
        media = _safe_media_metadata(detail)
        if not str(media.get("id") or "").strip():
            continue

        message_id = str(message.get("id") or "").strip()
        sender = str(message.get("from") or "").strip()
        if not message_id or not sender:
            continue

        caption = str(detail.get("caption") or "").strip() or None
        metadata: dict[str, Any] = {
            "provider": "meta_cloud",
            "phone_number_id": phone_number_id or None,
            "whatsapp_timestamp": message.get("timestamp"),
            "whatsapp_type": message_type,
            "context_message_id": (
                message.get("context", {}).get("id")
                if isinstance(message.get("context"), dict)
                else None
            ),
            "media": media,
        }
        normalized.append(
            MetaMediaInbound(
                external_event_id=f"message:{message_id}",
                external_message_id=message_id,
                external_user_id=sender,
                external_conversation_id=sender,
                display_name=_display_name_for_sender(contacts, sender),
                phone=sender,
                message_type=message_type,
                content=caption,
                metadata=metadata,
            )
        )
    return normalized


def _identity_payload(inbound: MetaMediaInbound) -> NormalizedInboundMessage:
    # Identity/conversation resolution is shared with the canonical channel path.
    # The synthetic text never gets persisted or sent to the agent.
    return NormalizedInboundMessage(
        external_event_id=inbound.external_event_id,
        external_message_id=inbound.external_message_id,
        external_user_id=inbound.external_user_id,
        external_conversation_id=inbound.external_conversation_id,
        display_name=inbound.display_name,
        phone=inbound.phone,
        message_type="text",
        text="media",
        metadata=inbound.metadata,
    )


def _persist_media_inbound(
    db: Session,
    *,
    connection: ChannelConnection,
    inbound: MetaMediaInbound,
) -> bool:
    existing_event = db.scalar(
        select(ChannelInboundEvent).where(
            ChannelInboundEvent.channel_connection_id == connection.id,
            ChannelInboundEvent.external_event_id == inbound.external_event_id,
        )
    )
    if existing_event is not None:
        return False

    existing_message = db.scalar(
        select(Message).where(
            Message.workspace_id == connection.workspace_id,
            Message.channel_connection_id == connection.id,
            Message.external_message_id == inbound.external_message_id,
        )
    )
    if existing_message is not None:
        raise ChannelConflictError(
            "External media message id already exists without its inbound event."
        )

    payload = _identity_payload(inbound)
    _, patient = _resolve_identity(db, connection=connection, payload=payload)
    if not patient.whatsapp_opt_in:
        patient.whatsapp_opt_in = True
        patient.whatsapp_opt_in_at = datetime.now(UTC)
        patient.whatsapp_opt_in_source = "customer_inbound"
    conversation = _resolve_conversation(
        db,
        connection=connection,
        patient=patient,
        payload=payload,
    )

    now = _next_conversation_activity_at(conversation)
    message = Message(
        workspace_id=connection.workspace_id,
        conversation_id=conversation.id,
        channel_connection_id=connection.id,
        sender_type="patient",
        direction="inbound",
        message_type=inbound.message_type,
        content=inbound.content,
        external_message_id=inbound.external_message_id,
        delivery_status="received",
        created_at=now,
        metadata_json={
            "source": "meta_whatsapp_media",
            "provider": connection.provider,
            "external_event_id": inbound.external_event_id,
            "external_user_id": inbound.external_user_id,
            **inbound.metadata,
        },
    )
    record_customer_inbound(conversation, now=now)
    patient.last_contact_at = now
    db.add(message)
    db.flush()

    event = ChannelInboundEvent(
        workspace_id=connection.workspace_id,
        channel_connection_id=connection.id,
        message_id=message.id,
        external_event_id=inbound.external_event_id,
        status="processed",
        attempts=1,
        last_error=None,
        payload_json={
            "external_event_id": inbound.external_event_id,
            "external_message_id": inbound.external_message_id,
            "external_user_id": inbound.external_user_id,
            "external_conversation_id": inbound.external_conversation_id,
            "display_name": inbound.display_name,
            "phone": inbound.phone,
            "message_type": inbound.message_type,
            "text": inbound.content,
            "metadata": inbound.metadata,
        },
    )
    db.add(event)
    db.flush()

    create_handoff(
        db,
        workspace_id=connection.workspace_id,
        conversation=conversation,
        patient=patient,
        reason=f"WhatsApp {inbound.message_type} requires human review",
        category="other",
        priority="normal",
        source="system",
        handoff_context={
            "trigger": "whatsapp_media",
            "media_type": inbound.message_type,
            "inbound_message_id": str(message.id),
        },
        commit=False,
    )
    return True


def ingest_meta_media_webhook(
    db: Session,
    *,
    connection: ChannelConnection,
    payload: dict[str, Any],
) -> dict[str, int]:
    accepted = 0
    duplicates = 0
    ignored = 0
    entries = payload.get("entry") if isinstance(payload.get("entry"), list) else []

    for entry in entries:
        if not isinstance(entry, dict):
            continue
        changes = entry.get("changes") if isinstance(entry.get("changes"), list) else []
        for change in changes:
            value = change.get("value") if isinstance(change, dict) else None
            if not isinstance(value, dict):
                continue
            media_items = normalize_meta_media(value)
            if not media_items:
                continue
            phone_number_id = str((value.get("metadata") or {}).get("phone_number_id") or "").strip()
            if not phone_number_id or phone_number_id != str(connection.external_account_id or "").strip():
                ignored += len(media_items)
                continue

            for inbound in media_items:
                try:
                    inserted = _persist_media_inbound(
                        db,
                        connection=connection,
                        inbound=inbound,
                    )
                    if inserted:
                        db.commit()
                        accepted += 1
                    else:
                        db.rollback()
                        duplicates += 1
                except IntegrityError:
                    db.rollback()
                    duplicate = db.scalar(
                        select(ChannelInboundEvent.id).where(
                            ChannelInboundEvent.channel_connection_id == connection.id,
                            ChannelInboundEvent.external_event_id == inbound.external_event_id,
                        )
                    )
                    if duplicate is None:
                        raise
                    duplicates += 1
                except Exception:
                    db.rollback()
                    raise

    return {
        "accepted_media": accepted,
        "duplicate_media": duplicates,
        "ignored_media": ignored,
    }
