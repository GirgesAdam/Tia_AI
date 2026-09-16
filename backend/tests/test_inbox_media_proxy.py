from __future__ import annotations

from datetime import UTC, datetime, timedelta
from types import SimpleNamespace
from uuid import uuid4

import pytest
from fastapi import HTTPException

from app.api.routes import inbox_media
from app.models.message import Message
from app.services import meta_whatsapp_media as media_service


class _ProviderResponse:
    def __init__(
        self,
        *,
        status_code: int,
        json_payload: dict | None = None,
        headers: dict[str, str] | None = None,
        chunks: list[bytes] | None = None,
    ) -> None:
        self.status_code = status_code
        self._json_payload = json_payload or {}
        self.headers = headers or {}
        self._chunks = chunks or []
        self.closed = False

    def json(self):
        return self._json_payload

    def iter_bytes(self):
        yield from self._chunks

    def read(self):
        return b"".join(self._chunks)

    def close(self) -> None:
        self.closed = True


class _ProviderClient:
    def __init__(self, metadata_response: _ProviderResponse, media_response: _ProviderResponse) -> None:
        self.metadata_response = metadata_response
        self.media_response = media_response
        self.closed = False
        self.download_headers: dict[str, str] = {}

    def get(self, *_args, **_kwargs):
        return self.metadata_response

    def build_request(self, _method: str, _url: str, *, headers: dict[str, str]):
        self.download_headers = dict(headers)
        return object()

    def send(self, _request, *, stream: bool):
        assert stream is True
        return self.media_response

    def close(self) -> None:
        self.closed = True


class _ScalarSession:
    def __init__(self, values: list[object | None]) -> None:
        self.values = list(values)

    def scalar(self, _statement):
        return self.values.pop(0) if self.values else None


def test_open_meta_media_stream_keeps_token_server_side_and_forwards_range(monkeypatch) -> None:
    metadata_response = _ProviderResponse(
        status_code=200,
        json_payload={
            "url": "https://lookaside.fbsbx.com/whatsapp_business/attachments/example",
            "mime_type": "image/jpeg",
        },
    )
    media_response = _ProviderResponse(
        status_code=206,
        headers={
            "content-type": "image/jpeg",
            "content-length": "3",
            "content-range": "bytes 0-2/3",
            "accept-ranges": "bytes",
        },
        chunks=[b"abc"],
    )
    client = _ProviderClient(metadata_response, media_response)
    monkeypatch.setattr(media_service.httpx, "Client", lambda **_kwargs: client)
    monkeypatch.setattr(
        media_service,
        "_graph_url",
        lambda media_id: f"https://graph.facebook.com/v99.0/{media_id}",
    )

    stream = media_service.open_meta_media_stream(
        access_token="secret-provider-token",
        media_id="media-123",
        phone_number_id="phone-123",
        range_header="bytes=0-2",
    )

    assert stream.status_code == 206
    assert stream.content_type == "image/jpeg"
    assert stream.content_range == "bytes 0-2/3"
    assert client.download_headers == {
        "Authorization": "Bearer secret-provider-token",
        "Range": "bytes=0-2",
    }
    assert list(stream.iter_bytes()) == [b"abc"]
    assert media_response.closed is True
    assert client.closed is True


def test_open_meta_media_stream_rejects_non_https_provider_url(monkeypatch) -> None:
    metadata_response = _ProviderResponse(
        status_code=200,
        json_payload={"url": "http://127.0.0.1/internal", "mime_type": "image/jpeg"},
    )
    client = _ProviderClient(metadata_response, _ProviderResponse(status_code=200))
    monkeypatch.setattr(media_service.httpx, "Client", lambda **_kwargs: client)
    monkeypatch.setattr(media_service, "_graph_url", lambda media_id: f"https://graph/{media_id}")

    with pytest.raises(media_service.MetaWhatsAppMediaError):
        media_service.open_meta_media_stream(
            access_token="provider-token",
            media_id="media-123",
            phone_number_id="phone-123",
        )

    assert client.closed is True


def test_inbox_media_proxy_is_workspace_scoped_and_never_exposes_provider_token(monkeypatch) -> None:
    workspace_id = uuid4()
    connection_id = uuid4()
    message = Message(
        id=uuid4(),
        workspace_id=workspace_id,
        conversation_id=uuid4(),
        channel_connection_id=connection_id,
        sender_type="patient",
        direction="inbound",
        message_type="document",
        content="نتيجة التحليل",
        delivery_status="received",
        metadata_json={
            "media": {
                "id": "media-456",
                "mime_type": "application/pdf",
                "filename": "result.pdf",
            }
        },
    )
    connection = SimpleNamespace(
        id=connection_id,
        external_account_id="phone-456",
    )
    credential = SimpleNamespace(
        access_token_ciphertext="encrypted-token",
        expires_at=datetime.now(UTC) + timedelta(hours=1),
    )
    access = SimpleNamespace(workspace=SimpleNamespace(id=workspace_id))
    db = _ScalarSession([message, connection, credential])
    captured: dict[str, object] = {}

    monkeypatch.setattr(inbox_media, "decrypt_provider_access_token", lambda _value: "real-token")

    class _Stream:
        status_code = 200
        content_type = "application/pdf"
        content_length = "4"
        content_range = None
        accept_ranges = "bytes"

        def iter_bytes(self):
            yield b"test"

    def fake_open_meta_media_stream(**kwargs):
        captured.update(kwargs)
        return _Stream()

    monkeypatch.setattr(inbox_media, "open_meta_media_stream", fake_open_meta_media_stream)

    response = inbox_media.stream_inbox_message_media(
        message_id=message.id,
        access=access,
        db=db,
        range_header=None,
    )

    assert response.status_code == 200
    assert response.headers["cache-control"] == "private, no-store"
    assert response.headers["x-content-type-options"] == "nosniff"
    assert "result.pdf" in response.headers["content-disposition"]
    assert "real-token" not in " ".join(response.headers.values())
    assert captured["access_token"] == "real-token"
    assert captured["media_id"] == "media-456"
    assert captured["phone_number_id"] == "phone-456"


def test_inbox_media_proxy_rejects_non_media_messages() -> None:
    workspace_id = uuid4()
    message = Message(
        id=uuid4(),
        workspace_id=workspace_id,
        conversation_id=uuid4(),
        channel_connection_id=uuid4(),
        sender_type="patient",
        direction="inbound",
        message_type="text",
        content="hello",
        delivery_status="received",
        metadata_json={},
    )
    access = SimpleNamespace(workspace=SimpleNamespace(id=workspace_id))

    with pytest.raises(HTTPException) as exc_info:
        inbox_media.stream_inbox_message_media(
            message_id=message.id,
            access=access,
            db=_ScalarSession([message]),
            range_header=None,
        )

    assert exc_info.value.status_code == 404
