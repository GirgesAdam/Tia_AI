from __future__ import annotations

import hashlib
import hmac
from datetime import UTC, datetime, timedelta
from typing import Any

import httpx
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.meta_whatsapp_config import meta_whatsapp_settings
from app.models.automation_rule import AutomationRule
from app.models.channel_connection import ChannelConnection
from app.models.channel_inbound_event import ChannelInboundEvent
from app.models.channel_provider_credential import ChannelProviderCredential
from app.schemas.channel import DispatchClaimItem, NormalizedInboundMessage
from app.services.channels import (
    accept_normalized_inbound,
    claim_dispatches,
    process_inbound_event,
    record_dispatch_result,
    record_provider_status,
)
from app.services.provider_credentials import (
    ProviderCredentialError,
    decrypt_provider_access_token,
)


class MetaWhatsAppTransportError(RuntimeError):
    def __init__(self, message: str, *, code: int | None = None) -> None:
        super().__init__(message)
        self.code = code


_SUPPORTED_STATUSES = frozenset({"sent", "delivered", "read", "failed"})
_MAX_INBOUND_PROCESS_ATTEMPTS = 3
_PROVIDER_REFRESH_INTERVAL = timedelta(minutes=15)
_PENDING_PROVIDER_REFRESH_INTERVAL = timedelta(minutes=2)
_MAX_TEMPLATE_STATUS_PAGES = 20


def _clean(value: str | None) -> str | None:
    if value is None:
        return None
    value = value.strip()
    return value or None


def _graph_url(path: str) -> str:
    version = _clean(meta_whatsapp_settings.meta_graph_api_version)
    if not version:
        raise MetaWhatsAppTransportError("Meta Graph API version is not configured.")
    normalized = version if version.startswith("v") else f"v{version}"
    return f"https://graph.facebook.com/{normalized}/{path.lstrip('/')}"


def verify_meta_webhook_signature(body: bytes, signature_header: str | None) -> bool:
    app_secret = _clean(meta_whatsapp_settings.meta_app_secret)
    signature = _clean(signature_header)
    if not app_secret or not signature or not signature.startswith("sha256="):
        return False
    expected = hmac.new(app_secret.encode("utf-8"), body, hashlib.sha256).hexdigest()
    supplied = signature.removeprefix("sha256=").strip().lower()
    return bool(supplied) and hmac.compare_digest(expected, supplied)


def verify_meta_webhook_challenge(mode: str | None, token: str | None) -> bool:
    expected = _clean(meta_whatsapp_settings.meta_webhook_verify_token)
    return bool(expected and mode == "subscribe" and token == expected)


def _provider_error_payload(response: httpx.Response) -> tuple[str, dict[str, Any]]:
    message = f"Meta request failed with HTTP {response.status_code}."
    error_meta: dict[str, Any] = {}
    try:
        payload = response.json()
    except ValueError:
        payload = None
    if isinstance(payload, dict) and isinstance(payload.get("error"), dict):
        raw = payload["error"]
        message = str(raw.get("message") or message)[:2000]
        error_meta = {
            "code": raw.get("code"),
            "message": message,
            "title": message,
            "error_data": raw.get("error_data"),
            "type": raw.get("type"),
            "fbtrace_id": raw.get("fbtrace_id"),
        }
    return message, error_meta


def _coerce_meta_error_code(value: object) -> int | None:
    try:
        return int(value) if value is not None else None
    except (TypeError, ValueError):
        return None


def _credential_for_connection(
    db: Session, connection: ChannelConnection
) -> ChannelProviderCredential | None:
    return db.get(ChannelProviderCredential, connection.id)


def _decrypt_connection_token(
    db: Session, connection: ChannelConnection
) -> tuple[str | None, str | None]:
    credential = _credential_for_connection(db, connection)
    if credential is None:
        return None, "Provider credential is missing."
    if credential.expires_at is not None and credential.expires_at <= datetime.now(UTC):
        return None, "Meta access token has expired."
    try:
        return decrypt_provider_access_token(credential.access_token_ciphertext), None
    except ProviderCredentialError as exc:
        return None, str(exc)


def _required_template_names(db: Session, connection: ChannelConnection) -> list[str]:
    rows = list(
        db.scalars(
            select(AutomationRule).where(
                AutomationRule.workspace_id == connection.workspace_id,
                AutomationRule.enabled.is_(True),
                AutomationRule.channel.in_(("whatsapp", "auto")),
                AutomationRule.template_name.is_not(None),
            )
        )
    )
    return sorted({str(rule.template_name) for rule in rows if rule.template_name})


def _parse_utc_timestamp(value: object) -> datetime | None:
    if not isinstance(value, str) or not value.strip():
        return None
    try:
        parsed = datetime.fromisoformat(value.strip().replace("Z", "+00:00"))
    except ValueError:
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=UTC)
    return parsed.astimezone(UTC)


def _readiness_refresh_due(
    connection: ChannelConnection,
    *,
    required_templates: list[str],
    now: datetime | None = None,
) -> bool:
    """Throttle Meta metadata calls without slowing message delivery.

    Healthy connections refresh provider/template metadata every 15 minutes.
    Connections waiting on a template or otherwise not ready refresh every 2 minutes.
    The transport tick itself may still run every few seconds for inbound/outbound work.
    """
    current = now or datetime.now(UTC)
    config = connection.config_json or {}
    raw_health = config.get("provider_health")
    health = raw_health if isinstance(raw_health, dict) else {}
    last_checked = _parse_utc_timestamp(health.get("last_checked_at"))
    if last_checked is None:
        return True

    raw_statuses = config.get("template_statuses")
    template_statuses = raw_statuses if isinstance(raw_statuses, dict) else {}
    waiting_for_template = any(
        str(template_statuses.get(name) or "").lower()
        not in {"approved", "rejected", "disabled"}
        for name in required_templates
    )
    needs_fast_refresh = (
        connection.status != "active"
        or not bool(config.get("transport_ready"))
        or waiting_for_template
    )
    interval = (
        _PENDING_PROVIDER_REFRESH_INTERVAL
        if needs_fast_refresh
        else _PROVIDER_REFRESH_INTERVAL
    )
    return current - last_checked >= interval


def _fetch_phone_info(token: str, phone_number_id: str) -> dict[str, Any]:
    response = httpx.get(
        _graph_url(phone_number_id),
        params={"fields": "id,display_phone_number,verified_name,quality_rating"},
        headers={"Authorization": f"Bearer {token}"},
        timeout=20.0,
    )
    if response.status_code >= 400:
        message, meta = _provider_error_payload(response)
        raise MetaWhatsAppTransportError(
            message,
            code=_coerce_meta_error_code(meta.get("code")),
        )
    payload = response.json()
    return payload if isinstance(payload, dict) else {}


def _fetch_template_statuses(token: str, waba_id: str) -> dict[str, str]:
    endpoint = _graph_url(f"{waba_id}/message_templates")
    headers = {"Authorization": f"Bearer {token}"}
    statuses: dict[str, str] = {}
    after: str | None = None
    seen_cursors: set[str] = set()

    for _ in range(_MAX_TEMPLATE_STATUS_PAGES):
        params: dict[str, Any] = {
            "fields": "name,status,language",
            "limit": 100,
        }
        if after:
            params["after"] = after

        response = httpx.get(
            endpoint,
            params=params,
            headers=headers,
            timeout=20.0,
        )
        if response.status_code >= 400:
            message, meta = _provider_error_payload(response)
            raise MetaWhatsAppTransportError(
                message,
                code=_coerce_meta_error_code(meta.get("code")),
            )

        payload = response.json()
        data = payload.get("data") if isinstance(payload, dict) else None
        for item in data if isinstance(data, list) else []:
            if not isinstance(item, dict):
                continue
            name = str(item.get("name") or "").strip()
            status = str(item.get("status") or "").strip().lower()
            if name and status:
                statuses[name] = status

        paging = payload.get("paging") if isinstance(payload, dict) else None
        cursors = paging.get("cursors") if isinstance(paging, dict) else None
        next_after = (
            str(cursors.get("after") or "").strip()
            if isinstance(cursors, dict)
            else ""
        )
        if not next_after or next_after in seen_cursors:
            break
        seen_cursors.add(next_after)
        after = next_after

    return statuses


def _set_provider_health(
    connection: ChannelConnection,
    *,
    state: str,
    error: str | None = None,
    error_code: int | str | None = None,
    action_required: str | None = None,
) -> None:
    config = dict(connection.config_json or {})
    raw_health = config.get("provider_health")
    health = dict(raw_health) if isinstance(raw_health, dict) else {}
    health["state"] = state
    health["last_checked_at"] = datetime.now(UTC).isoformat()
    health["current_error"] = error[:2000] if error else None
    health["current_error_code"] = str(error_code) if error_code is not None else None
    if action_required:
        health["action_required"] = action_required
    else:
        health.pop("action_required", None)
    config["provider_health"] = health
    connection.config_json = config


def refresh_meta_connection_readiness(db: Session, connection: ChannelConnection) -> bool:
    """Refresh provider metadata and make native transport ready without clinic-side credentials."""
    if connection.channel != "whatsapp" or connection.provider != "meta_cloud":
        return False

    token, credential_error = _decrypt_connection_token(db, connection)
    config = dict(connection.config_json or {})
    phone_number_id = str(config.get("phone_number_id") or connection.external_account_id or "").strip()
    waba_id = str(config.get("waba_id") or "").strip()
    if credential_error or not token or not phone_number_id or not waba_id:
        config["transport_ready"] = False
        connection.config_json = config
        connection.status = "paused"
        _set_provider_health(
            connection,
            state="degraded",
            error=credential_error or "WhatsApp connection metadata is incomplete.",
            action_required="reconnect_meta" if credential_error else None,
        )
        db.commit()
        return False

    try:
        phone_info = _fetch_phone_info(token, phone_number_id)
        template_statuses = _fetch_template_statuses(token, waba_id)
    except (httpx.HTTPError, MetaWhatsAppTransportError) as exc:
        message = str(exc)
        error_code = exc.code if isinstance(exc, MetaWhatsAppTransportError) else None
        config = dict(connection.config_json or {})
        config["transport_ready"] = False
        connection.config_json = config
        connection.status = "paused"
        action_required = (
            "reconnect_meta"
            if error_code == 190
            else "meta_account_review"
            if error_code == 131031
            else None
        )
        _set_provider_health(
            connection,
            state="disabled" if error_code == 131031 else "degraded",
            error=message,
            error_code=error_code,
            action_required=action_required,
        )
        db.commit()
        return False

    config = dict(connection.config_json or {})
    config.update(
        {
            "phone_number_id": phone_number_id,
            "display_phone_number": str(phone_info.get("display_phone_number") or "").strip()
            or config.get("display_phone_number"),
            "verified_name": str(phone_info.get("verified_name") or "").strip()
            or config.get("verified_name"),
            "quality_rating": str(phone_info.get("quality_rating") or "").strip()
            or config.get("quality_rating"),
            "template_statuses": template_statuses,
            "templates_checked_at": datetime.now(UTC).isoformat(),
            "transport_ready": True,
            "transport": "tia_native_meta_cloud",
        }
    )
    connection.config_json = config
    connection.external_account_id = phone_number_id
    connection.display_name = (
        str(config.get("verified_name") or config.get("display_phone_number") or "WhatsApp")[:120]
    )
    connection.status = "active"
    _set_provider_health(connection, state="healthy")
    db.commit()
    return True


def _template_payload(item: DispatchClaimItem) -> dict[str, Any] | None:
    raw = item.metadata.get("whatsapp_template") if isinstance(item.metadata, dict) else None
    if not isinstance(raw, dict):
        return None
    name = str(raw.get("name") or "").strip()
    language = str(raw.get("language_code") or "").strip()
    params = raw.get("body_parameters")
    if not name or not language or not isinstance(params, list):
        return None
    components: list[dict[str, Any]] = []
    if params:
        components.append(
            {
                "type": "body",
                "parameters": [
                    {"type": "text", "text": str(value)}
                    for value in params
                ],
            }
        )
    return {
        "name": name,
        "language": {"code": language},
        "components": components,
    }


def build_meta_message_payload(item: DispatchClaimItem) -> dict[str, Any]:
    base: dict[str, Any] = {
        "messaging_product": "whatsapp",
        "recipient_type": "individual",
        "to": item.external_user_id,
    }
    if item.message_type == "template":
        template = _template_payload(item)
        if template is None:
            raise MetaWhatsAppTransportError("Template dispatch is missing WhatsApp template metadata.")
        return {**base, "type": "template", "template": template}

    interactive = item.metadata.get("whatsapp_interactive") if isinstance(item.metadata, dict) else None
    if isinstance(interactive, dict) and interactive.get("type") == "button":
        raw_buttons = interactive.get("buttons")
        buttons = []
        for raw in raw_buttons if isinstance(raw_buttons, list) else []:
            if not isinstance(raw, dict):
                continue
            button_id = str(raw.get("id") or "").strip()
            title = str(raw.get("title") or "").strip()
            if button_id and title:
                buttons.append(
                    {
                        "type": "reply",
                        "reply": {"id": button_id, "title": title[:20]},
                    }
                )
        if buttons and item.content:
            return {
                **base,
                "type": "interactive",
                "interactive": {
                    "type": "button",
                    "body": {"text": item.content},
                    "action": {"buttons": buttons[:3]},
                },
            }

    if not item.content:
        raise MetaWhatsAppTransportError("Text dispatch has no message body.")
    return {
        **base,
        "type": "text",
        "text": {"preview_url": False, "body": item.content},
    }


def _send_claimed_dispatch(
    db: Session,
    *,
    connection: ChannelConnection,
    token: str,
    item: DispatchClaimItem,
) -> bool:
    try:
        body = build_meta_message_payload(item)
    except MetaWhatsAppTransportError as exc:
        record_dispatch_result(
            db,
            connection=connection,
            dispatch_id=item.dispatch_id,
            result_status="failed",
            provider_message_id=None,
            error=str(exc),
            retry_after_seconds=None,
            metadata={"transport": "tia_native", "provider": "meta_cloud", "attempt": item.attempt},
        )
        return False

    phone_number_id = str(connection.external_account_id or "").strip()
    if not phone_number_id:
        record_dispatch_result(
            db,
            connection=connection,
            dispatch_id=item.dispatch_id,
            result_status="failed",
            provider_message_id=None,
            error="Connected WhatsApp phone number id is missing.",
            retry_after_seconds=None,
            metadata={"transport": "tia_native", "provider": "meta_cloud", "attempt": item.attempt},
        )
        return False

    try:
        response = httpx.post(
            _graph_url(f"{phone_number_id}/messages"),
            headers={"Authorization": f"Bearer {token}"},
            json=body,
            timeout=30.0,
        )
    except httpx.HTTPError as exc:
        record_dispatch_result(
            db,
            connection=connection,
            dispatch_id=item.dispatch_id,
            result_status="failed",
            provider_message_id=None,
            error=f"Could not reach Meta: {exc}",
            retry_after_seconds=30,
            metadata={"transport": "tia_native", "provider": "meta_cloud", "attempt": item.attempt},
        )
        return False

    metadata: dict[str, Any] = {
        "transport": "tia_native",
        "provider": "meta_cloud",
        "attempt": item.attempt,
    }
    if response.status_code >= 400:
        message, error_meta = _provider_error_payload(response)
        if error_meta:
            metadata["errors"] = [error_meta]
        retry_after = None if error_meta.get("code") in {131031, 190} else 30
        record_dispatch_result(
            db,
            connection=connection,
            dispatch_id=item.dispatch_id,
            result_status="failed",
            provider_message_id=None,
            error=message,
            retry_after_seconds=retry_after,
            metadata=metadata,
        )
        if error_meta.get("code") == 190:
            connection.status = "paused"
            config = dict(connection.config_json or {})
            config["transport_ready"] = False
            connection.config_json = config
            _set_provider_health(
                connection,
                state="degraded",
                error=message,
                error_code=190,
                action_required="reconnect_meta",
            )
            db.commit()
        return False

    payload = response.json()
    messages = payload.get("messages") if isinstance(payload, dict) else None
    provider_message_id = None
    if isinstance(messages, list) and messages and isinstance(messages[0], dict):
        provider_message_id = str(messages[0].get("id") or "").strip() or None
    if not provider_message_id:
        record_dispatch_result(
            db,
            connection=connection,
            dispatch_id=item.dispatch_id,
            result_status="failed",
            provider_message_id=None,
            error="Meta accepted the request without returning a message id.",
            retry_after_seconds=30,
            metadata=metadata,
        )
        return False

    record_dispatch_result(
        db,
        connection=connection,
        dispatch_id=item.dispatch_id,
        result_status="sent",
        provider_message_id=provider_message_id,
        error=None,
        retry_after_seconds=None,
        metadata=metadata,
    )
    return True


def _connection_for_phone_number(
    db: Session, phone_number_id: str
) -> ChannelConnection | None:
    return db.scalar(
        select(ChannelConnection).where(
            ChannelConnection.channel == "whatsapp",
            ChannelConnection.provider == "meta_cloud",
            ChannelConnection.external_account_id == phone_number_id,
            ChannelConnection.status.in_(("active", "paused")),
        )
    )


def _normalize_inbound(value: dict[str, Any]) -> list[NormalizedInboundMessage]:
    contacts = value.get("contacts") if isinstance(value.get("contacts"), list) else []
    messages = value.get("messages") if isinstance(value.get("messages"), list) else []
    phone_number_id = str((value.get("metadata") or {}).get("phone_number_id") or "").strip()
    normalized: list[NormalizedInboundMessage] = []
    for message in messages:
        if not isinstance(message, dict):
            continue
        message_id = str(message.get("id") or "").strip()
        sender = str(message.get("from") or "").strip()
        message_type = str(message.get("type") or "").strip()
        button_reply = None
        text = None
        if message_type == "text" and isinstance(message.get("text"), dict):
            text = str(message["text"].get("body") or "").strip()
        elif message_type == "interactive" and isinstance(message.get("interactive"), dict):
            interactive = message["interactive"]
            if interactive.get("type") == "button_reply" and isinstance(
                interactive.get("button_reply"), dict
            ):
                button_reply = interactive["button_reply"]
                text = str(button_reply.get("title") or "").strip()
        if not message_id or not sender or not text:
            continue
        display_name = None
        for contact in contacts:
            if not isinstance(contact, dict):
                continue
            if str(contact.get("wa_id") or "") not in {"", sender}:
                continue
            profile = contact.get("profile")
            if isinstance(profile, dict) and profile.get("name"):
                display_name = str(profile["name"])
                break
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
        }
        if button_reply is not None:
            metadata["interactive_reply"] = {
                "type": "button_reply",
                "id": button_reply.get("id"),
                "title": button_reply.get("title"),
            }
        normalized.append(
            NormalizedInboundMessage(
                external_event_id=f"message:{message_id}",
                external_message_id=message_id,
                external_user_id=sender,
                external_conversation_id=sender,
                display_name=display_name,
                phone=sender,
                message_type="text",
                text=text,
                metadata=metadata,
            )
        )
    return normalized


def ingest_meta_webhook(db: Session, payload: dict[str, Any]) -> dict[str, int]:
    accepted = 0
    statuses = 0
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
            phone_number_id = str((value.get("metadata") or {}).get("phone_number_id") or "").strip()
            if not phone_number_id:
                ignored += 1
                continue
            connection = _connection_for_phone_number(db, phone_number_id)
            if connection is None:
                ignored += 1
                continue

            for inbound in _normalize_inbound(value):
                accept_normalized_inbound(db, connection=connection, payload=inbound)
                accepted += 1

            raw_statuses = value.get("statuses") if isinstance(value.get("statuses"), list) else []
            for raw in raw_statuses:
                if not isinstance(raw, dict):
                    continue
                provider_message_id = str(raw.get("id") or "").strip()
                provider_status = str(raw.get("status") or "").strip().lower()
                if not provider_message_id or provider_status not in _SUPPORTED_STATUSES:
                    continue
                timestamp = str(raw.get("timestamp") or "0")
                occurred_at = None
                try:
                    seconds = int(timestamp)
                    if seconds > 0:
                        occurred_at = datetime.fromtimestamp(seconds, tz=UTC)
                except (TypeError, ValueError, OSError):
                    occurred_at = None
                errors = raw.get("errors") if isinstance(raw.get("errors"), list) else []
                first_error = errors[0] if errors and isinstance(errors[0], dict) else {}
                error = str(first_error.get("title") or first_error.get("message") or "").strip() or None
                record_provider_status(
                    db,
                    connection=connection,
                    external_event_id=f"status:{provider_message_id}:{provider_status}:{timestamp}",
                    provider_message_id=provider_message_id,
                    provider_status=provider_status,
                    occurred_at=occurred_at,
                    error=error,
                    metadata={
                        "provider": "meta_cloud",
                        "phone_number_id": phone_number_id,
                        "recipient_id": raw.get("recipient_id"),
                        "conversation": raw.get("conversation"),
                        "pricing": raw.get("pricing"),
                        "errors": errors or None,
                    },
                )
                statuses += 1
    return {"accepted_inbound": accepted, "delivery_statuses": statuses, "ignored": ignored}


def _process_pending_inbound(
    db: Session, connection: ChannelConnection, *, limit: int
) -> tuple[int, int]:
    events = list(
        db.scalars(
            select(ChannelInboundEvent)
            .where(
                ChannelInboundEvent.workspace_id == connection.workspace_id,
                ChannelInboundEvent.channel_connection_id == connection.id,
                ChannelInboundEvent.status.in_(("received", "failed")),
                ChannelInboundEvent.attempts < _MAX_INBOUND_PROCESS_ATTEMPTS,
            )
            .order_by(ChannelInboundEvent.created_at)
            .limit(limit)
        )
    )
    processed = 0
    failed = 0
    for event in events:
        try:
            process_inbound_event(db, connection=connection, event_id=event.id)
            processed += 1
        except Exception:
            failed += 1
    return processed, failed


def run_meta_transport_tick(
    db: Session,
    *,
    limit_per_connection: int = 10,
    max_connections: int = 25,
) -> dict[str, int]:
    connections = list(
        db.scalars(
            select(ChannelConnection)
            .where(
                ChannelConnection.channel == "whatsapp",
                ChannelConnection.provider == "meta_cloud",
                ChannelConnection.status.in_(("active", "paused")),
            )
            .order_by(ChannelConnection.created_at)
            .limit(max_connections)
        )
    )
    sent = 0
    send_failed = 0
    inbound_processed = 0
    inbound_failed = 0
    ready_connections = 0

    provider_refreshes = 0

    for connection in connections:
        required_templates = _required_template_names(db, connection)
        if _readiness_refresh_due(
            connection,
            required_templates=required_templates,
        ):
            ready = refresh_meta_connection_readiness(db, connection)
            provider_refreshes += 1
        else:
            ready = bool((connection.config_json or {}).get("transport_ready"))

        processed, failed = _process_pending_inbound(
            db, connection, limit=limit_per_connection
        )
        inbound_processed += processed
        inbound_failed += failed
        if not ready or connection.status != "active":
            continue

        token, error = _decrypt_connection_token(db, connection)
        if not token or error:
            continue
        ready_connections += 1
        raw_statuses = (connection.config_json or {}).get("template_statuses")
        template_statuses = raw_statuses if isinstance(raw_statuses, dict) else {}
        approved_template_names = frozenset(
            str(name)
            for name, status in template_statuses.items()
            if str(status or "").lower() == "approved"
        )
        for item in claim_dispatches(
            db,
            connection=connection,
            limit=limit_per_connection,
            approved_template_names=approved_template_names,
        ):
            if _send_claimed_dispatch(db, connection=connection, token=token, item=item):
                sent += 1
            else:
                send_failed += 1

    return {
        "connections_checked": len(connections),
        "connections_ready": ready_connections,
        "provider_refreshes": provider_refreshes,
        "inbound_processed": inbound_processed,
        "inbound_failed": inbound_failed,
        "sent": sent,
        "send_failed": send_failed,
    }
