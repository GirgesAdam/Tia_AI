from __future__ import annotations

from datetime import UTC, datetime
from types import SimpleNamespace
from uuid import uuid4

from app.models.channel_inbound_event import ChannelInboundEvent
from app.models.message import Message
from app.services import meta_whatsapp_media as media_service


class _FakeSession:
    def __init__(self, scalar_results: list[object] | None = None) -> None:
        self.scalar_results = list(scalar_results or [])
        self.added: list[object] = []
        self.commits = 0
        self.rollbacks = 0

    def scalar(self, _statement):
        return self.scalar_results.pop(0) if self.scalar_results else None

    def add(self, value: object) -> None:
        self.added.append(value)

    def flush(self) -> None:
        for value in self.added:
            if hasattr(value, "id") and getattr(value, "id") is None:
                setattr(value, "id", uuid4())

    def commit(self) -> None:
        self.commits += 1

    def rollback(self) -> None:
        self.rollbacks += 1


def _image_value() -> dict:
    return {
        "metadata": {"phone_number_id": "phone-123"},
        "contacts": [{"wa_id": "201000000000", "profile": {"name": "Mona"}}],
        "messages": [
            {
                "id": "wamid.image-1",
                "from": "201000000000",
                "timestamp": "1789500000",
                "type": "image",
                "image": {
                    "id": "media-123",
                    "mime_type": "image/jpeg",
                    "sha256": "safe-digest",
                    "caption": "صورة قبل الجلسة",
                    "access_token": "must-not-be-copied",
                },
            },
            {
                "id": "wamid.text-1",
                "from": "201000000000",
                "type": "text",
                "text": {"body": "hello"},
            },
        ],
    }


def test_normalize_meta_media_keeps_safe_metadata_and_ignores_text() -> None:
    items = media_service.normalize_meta_media(_image_value())

    assert len(items) == 1
    item = items[0]
    assert item.message_type == "image"
    assert item.content == "صورة قبل الجلسة"
    assert item.display_name == "Mona"
    assert item.metadata["media"] == {
        "id": "media-123",
        "mime_type": "image/jpeg",
        "sha256": "safe-digest",
        "caption": "صورة قبل الجلسة",
    }
    assert "access_token" not in item.metadata["media"]


def test_normalize_meta_media_rejects_media_without_provider_id() -> None:
    value = _image_value()
    value["messages"][0]["image"].pop("id")

    assert media_service.normalize_meta_media(value) == []


def test_persist_media_is_atomic_with_handoff_and_never_creates_agent_text(monkeypatch) -> None:
    workspace_id = uuid4()
    connection_id = uuid4()
    patient_id = uuid4()
    conversation_id = uuid4()
    fixed_now = datetime(2026, 9, 16, 1, 30, tzinfo=UTC)
    db = _FakeSession([None, None])
    connection = SimpleNamespace(
        id=connection_id,
        workspace_id=workspace_id,
        provider="meta_cloud",
    )
    patient = SimpleNamespace(
        id=patient_id,
        workspace_id=workspace_id,
        whatsapp_opt_in=False,
        whatsapp_opt_in_at=None,
        whatsapp_opt_in_source=None,
        last_contact_at=None,
    )
    conversation = SimpleNamespace(
        id=conversation_id,
        workspace_id=workspace_id,
        patient_id=patient_id,
        unread_count=0,
        last_message_at=fixed_now,
        ownership_changed_at=fixed_now,
        owner_type="ai",
        status="open",
    )
    handoff_calls: list[dict] = []

    monkeypatch.setattr(
        media_service,
        "_resolve_identity",
        lambda *_args, **_kwargs: (object(), patient),
    )
    monkeypatch.setattr(
        media_service,
        "_resolve_conversation",
        lambda *_args, **_kwargs: conversation,
    )
    monkeypatch.setattr(
        media_service,
        "_next_conversation_activity_at",
        lambda _conversation: fixed_now,
    )

    def fake_create_handoff(*_args, **kwargs):
        handoff_calls.append(kwargs)
        conversation.owner_type = "human"
        conversation.status = "pending"
        return object()

    monkeypatch.setattr(media_service, "create_handoff", fake_create_handoff)

    inbound = media_service.normalize_meta_media(_image_value())[0]
    inserted = media_service._persist_media_inbound(
        db,
        connection=connection,
        inbound=inbound,
    )

    assert inserted is True
    assert db.commits == 0
    messages = [item for item in db.added if isinstance(item, Message)]
    events = [item for item in db.added if isinstance(item, ChannelInboundEvent)]
    assert len(messages) == 1
    assert len(events) == 1
    assert messages[0].message_type == "image"
    assert messages[0].content == "صورة قبل الجلسة"
    assert messages[0].metadata_json["media"]["id"] == "media-123"
    assert events[0].status == "processed"
    assert events[0].attempts == 1
    assert events[0].outbound_message_id is None
    assert patient.whatsapp_opt_in is True
    assert conversation.owner_type == "human"
    assert handoff_calls[0]["source"] == "system"
    assert handoff_calls[0]["commit"] is False
    assert handoff_calls[0]["handoff_context"]["media_type"] == "image"
