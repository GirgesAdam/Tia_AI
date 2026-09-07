from __future__ import annotations

import hashlib
import hmac
import json
from datetime import UTC, datetime, timedelta
from pathlib import Path
from types import SimpleNamespace
from uuid import uuid4

import pytest

import app.services.meta_whatsapp_transport as meta_transport
from app.core.meta_whatsapp_config import meta_whatsapp_settings
from app.schemas.channel import DispatchClaimItem
from app.services.meta_whatsapp_transport import (
    MetaWhatsAppTransportError,
    _readiness_refresh_due,
    build_meta_message_payload,
    refresh_meta_connection_readiness,
    verify_meta_webhook_challenge,
    verify_meta_webhook_signature,
)


def _dispatch(
    *,
    message_type: str = "text",
    content: str | None = "أهلاً",
    metadata: dict | None = None,
) -> DispatchClaimItem:
    return DispatchClaimItem(
        dispatch_id=uuid4(),
        message_id=uuid4(),
        channel="whatsapp",
        provider="meta_cloud",
        external_account_id="123456789",
        external_user_id="201001112223",
        external_conversation_id="201001112223",
        message_type=message_type,
        content=content,
        metadata=metadata or {},
        attempt=1,
    )


def test_meta_webhook_signature_requires_valid_hmac(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    secret = "meta-app-secret"
    body = b'{"object":"whatsapp_business_account"}'
    digest = hmac.new(secret.encode(), body, hashlib.sha256).hexdigest()
    monkeypatch.setattr(meta_whatsapp_settings, "meta_app_secret", secret)

    assert verify_meta_webhook_signature(body, f"sha256={digest}") is True
    assert verify_meta_webhook_signature(body + b"x", f"sha256={digest}") is False
    assert verify_meta_webhook_signature(body, "sha256=deadbeef") is False
    assert verify_meta_webhook_signature(body, None) is False


def test_meta_webhook_challenge_uses_platform_verify_token(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(meta_whatsapp_settings, "meta_webhook_verify_token", "verify-me")

    assert verify_meta_webhook_challenge("subscribe", "verify-me") is True
    assert verify_meta_webhook_challenge("subscribe", "wrong") is False
    assert verify_meta_webhook_challenge("unsubscribe", "verify-me") is False


def _connection_for_refresh(*, checked_at: datetime, template_status: str = "approved", ready: bool = True, status: str = "active"):
    return SimpleNamespace(
        status=status,
        config_json={
            "transport_ready": ready,
            "template_statuses": {"tia_reminder_01": template_status},
            "provider_health": {"last_checked_at": checked_at.isoformat()},
        },
    )


def test_meta_readiness_refresh_is_throttled_when_healthy() -> None:
    checked_at = datetime(2026, 9, 7, 18, 0, tzinfo=UTC)
    connection = _connection_for_refresh(checked_at=checked_at)

    assert _readiness_refresh_due(
        connection,
        required_templates=["tia_reminder_01"],
        now=checked_at + timedelta(minutes=14),
    ) is False
    assert _readiness_refresh_due(
        connection,
        required_templates=["tia_reminder_01"],
        now=checked_at + timedelta(minutes=15),
    ) is True


def test_meta_readiness_refresh_is_faster_while_template_is_pending() -> None:
    checked_at = datetime(2026, 9, 7, 18, 0, tzinfo=UTC)
    connection = _connection_for_refresh(
        checked_at=checked_at,
        template_status="pending",
    )

    assert _readiness_refresh_due(
        connection,
        required_templates=["tia_reminder_01"],
        now=checked_at + timedelta(minutes=1),
    ) is False
    assert _readiness_refresh_due(
        connection,
        required_templates=["tia_reminder_01"],
        now=checked_at + timedelta(minutes=2),
    ) is True


def test_missing_template_uses_pending_refresh_interval_not_every_tick() -> None:
    checked_at = datetime(2026, 9, 7, 18, 0, tzinfo=UTC)
    connection = _connection_for_refresh(checked_at=checked_at)
    connection.config_json["template_statuses"] = {}

    assert _readiness_refresh_due(
        connection,
        required_templates=["tia_reminder_01"],
        now=checked_at + timedelta(seconds=5),
    ) is False
    assert _readiness_refresh_due(
        connection,
        required_templates=["tia_reminder_01"],
        now=checked_at + timedelta(minutes=2),
    ) is True


def test_unready_connection_uses_fast_refresh_without_five_second_polling() -> None:
    checked_at = datetime(2026, 9, 7, 18, 0, tzinfo=UTC)
    connection = _connection_for_refresh(
        checked_at=checked_at,
        ready=False,
        status="paused",
    )

    assert _readiness_refresh_due(
        connection,
        required_templates=[],
        now=checked_at + timedelta(seconds=5),
    ) is False
    assert _readiness_refresh_due(
        connection,
        required_templates=[],
        now=checked_at + timedelta(minutes=2),
    ) is True


def _provider_error_connection():
    return SimpleNamespace(
        channel="whatsapp",
        provider="meta_cloud",
        external_account_id="123456789",
        status="active",
        config_json={
            "phone_number_id": "123456789",
            "waba_id": "987654321",
            "transport_ready": True,
        },
    )


def test_readiness_131031_surfaces_meta_account_review(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    connection = _provider_error_connection()
    db = SimpleNamespace(commit=lambda: None)
    monkeypatch.setattr(
        meta_transport,
        "_decrypt_connection_token",
        lambda _db, _connection: ("token", None),
    )

    def fail_phone(_token: str, _phone_number_id: str):
        raise MetaWhatsAppTransportError("Business account locked", code=131031)

    monkeypatch.setattr(meta_transport, "_fetch_phone_info", fail_phone)

    assert refresh_meta_connection_readiness(db, connection) is False
    health = connection.config_json["provider_health"]
    assert connection.status == "paused"
    assert connection.config_json["transport_ready"] is False
    assert health["state"] == "disabled"
    assert health["current_error_code"] == "131031"
    assert health["action_required"] == "meta_account_review"


def test_readiness_190_surfaces_reconnect_meta(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    connection = _provider_error_connection()
    db = SimpleNamespace(commit=lambda: None)
    monkeypatch.setattr(
        meta_transport,
        "_decrypt_connection_token",
        lambda _db, _connection: ("token", None),
    )

    def fail_phone(_token: str, _phone_number_id: str):
        raise MetaWhatsAppTransportError("Invalid OAuth access token", code=190)

    monkeypatch.setattr(meta_transport, "_fetch_phone_info", fail_phone)

    assert refresh_meta_connection_readiness(db, connection) is False
    health = connection.config_json["provider_health"]
    assert connection.status == "paused"
    assert health["state"] == "degraded"
    assert health["current_error_code"] == "190"
    assert health["action_required"] == "reconnect_meta"


def test_native_transport_builds_text_message() -> None:
    payload = build_meta_message_payload(_dispatch(content="ميعادك اتأكد"))

    assert payload == {
        "messaging_product": "whatsapp",
        "recipient_type": "individual",
        "to": "201001112223",
        "type": "text",
        "text": {"preview_url": False, "body": "ميعادك اتأكد"},
    }


def test_native_transport_builds_three_parameter_template() -> None:
    payload = build_meta_message_payload(
        _dispatch(
            message_type="template",
            content=None,
            metadata={
                "whatsapp_template": {
                    "name": "tia_reminder_01",
                    "language_code": "ar",
                    "body_parameters": ["مريم", "ليزر", "7:00 م"],
                }
            },
        )
    )

    assert payload["type"] == "template"
    assert payload["template"]["name"] == "tia_reminder_01"
    assert payload["template"]["language"] == {"code": "ar"}
    assert payload["template"]["components"] == [
        {
            "type": "body",
            "parameters": [
                {"type": "text", "text": "مريم"},
                {"type": "text", "text": "ليزر"},
                {"type": "text", "text": "7:00 م"},
            ],
        }
    ]


def test_native_transport_builds_booking_buttons() -> None:
    payload = build_meta_message_payload(
        _dispatch(
            content="تم حجز الموعد. تحب تأكده؟",
            metadata={
                "whatsapp_interactive": {
                    "type": "button",
                    "buttons": [
                        {"id": "tia.booking.confirm:abc", "title": "تأكيد الحجز"},
                        {"id": "tia.booking.reschedule:abc", "title": "تغيير الميعاد"},
                    ],
                }
            },
        )
    )

    assert payload["type"] == "interactive"
    assert payload["interactive"]["type"] == "button"
    assert payload["interactive"]["body"]["text"] == "تم حجز الموعد. تحب تأكده؟"
    assert [button["reply"]["id"] for button in payload["interactive"]["action"]["buttons"]] == [
        "tia.booking.confirm:abc",
        "tia.booking.reschedule:abc",
    ]


def test_template_without_contract_is_rejected_before_provider_send() -> None:
    with pytest.raises(MetaWhatsAppTransportError):
        build_meta_message_payload(_dispatch(message_type="template", content=None))


def test_native_routes_and_worker_are_platform_managed() -> None:
    backend = Path(__file__).resolve().parent.parent
    route = (backend / "app/api/routes/whatsapp_setup.py").read_text(encoding="utf-8")
    transport = (backend / "app/services/meta_whatsapp_transport.py").read_text(
        encoding="utf-8"
    )
    worker = json.loads(
        (backend.parent / "n8n/workflows/tia_whatsapp_outbox_worker.json").read_text(
            encoding="utf-8"
        )
    )

    assert '@router.get("/webhook"' in route
    assert '@router.post("/webhook"' in route
    assert "X-Hub-Signature-256" in route
    assert '@router.post("/transport/tick")' in route
    assert "X-Tia-Transport-Token" in route
    assert "decrypt_provider_access_token" in transport
    assert "record_dispatch_result" in transport
    assert "allow_templates=allow_templates" in transport

    serialized = json.dumps(worker)
    assert "n8n-nodes-base.whatsApp" not in serialized
    assert "/api/v1/channels/whatsapp/transport/tick" in serialized
    assert "X-Channel-Token" not in serialized


def test_old_per_clinic_n8n_inbound_transport_is_removed() -> None:
    backend = Path(__file__).resolve().parent.parent
    assert not (backend.parent / "n8n/workflows/tia_whatsapp_inbound_status.json").exists()


def test_whatsapp_credential_revision_is_short_and_hardened() -> None:
    backend = Path(__file__).resolve().parent.parent
    migration = (
        backend / "alembic/versions/0059_channel_provider_credentials.py"
    ).read_text(encoding="utf-8")

    assert 'revision: str = "0059_channel_credentials"' in migration
    assert len("0059_channel_credentials") <= 32
    assert "ENABLE ROW LEVEL SECURITY" in migration
    assert "REVOKE ALL" in migration
