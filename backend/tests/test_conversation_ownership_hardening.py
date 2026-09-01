from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path
from uuid import uuid4

from app.schemas.crm import ConversationRead


def _backend() -> Path:
    return Path(__file__).resolve().parent.parent


def _function_block(source: str, name: str, next_name: str) -> str:
    start = source.index(f"def {name}(")
    end = source.index(f"def {next_name}(", start)
    return source[start:end]


def test_channel_inbound_serializes_conversation_activity_updates() -> None:
    source = (_backend() / "app/services/channels.py").read_text(encoding="utf-8")
    block = _function_block(source, "_resolve_conversation", "accept_normalized_inbound")

    assert ".with_for_update()" in block
    assert "record_customer_inbound(conversation, now=now)" in source


def test_agent_api_locks_existing_conversation_before_recording_inbound() -> None:
    source = (_backend() / "app/services/agent_chat.py").read_text(encoding="utf-8")
    lookup = _function_block(source, "_get_or_create_conversation", "_history_from_db")
    run = _function_block(source, "run_agent_chat", "run_agent_for_existing_inbound")

    assert ".with_for_update()" in lookup
    assert "activity_now = datetime.now(UTC)" in run
    assert "record_customer_inbound(conversation, now=activity_now)" in run


def test_crm_message_write_cannot_bypass_phase4_ownership() -> None:
    source = (_backend() / "app/api/routes/crm.py").read_text(encoding="utf-8")
    block = _function_block(source, "create_message", "list_messages")

    assert ".with_for_update()" in block
    assert 'if payload.sender_type == "ai":' in block
    assert 'conversation.owner_type != "human"' in block
    assert "conversation.assigned_user_id != access.user.id" in block
    assert "record_customer_inbound(conversation, now=now)" in block


def test_crm_assignment_and_pending_status_materialize_handoff_ownership() -> None:
    source = (_backend() / "app/api/routes/crm.py").read_text(encoding="utf-8")
    create = _function_block(source, "create_conversation", "list_conversations")
    update = _function_block(source, "update_conversation", "create_message")

    assert 'payload.assigned_user_id is not None or payload.status == "pending"' in create
    assert 'owner_type="ai"' in create
    assert "_ensure_crm_handoff(" in create
    assert 'updates.get("assigned_user_id") is not None' in update
    assert 'updates.get("status") == "pending"' in update
    assert "_ensure_crm_handoff(" in update
    assert 'conversation.owner_type = "human"' not in update


def test_crm_conversation_read_exposes_authoritative_ownership_state() -> None:
    now = datetime(2026, 8, 24, 18, 0, tzinfo=UTC)
    payload = ConversationRead(
        id=uuid4(),
        workspace_id=uuid4(),
        patient_id=uuid4(),
        channel="whatsapp",
        status="pending",
        external_conversation_id="wa-thread-1",
        assigned_user_id=uuid4(),
        owner_type="human",
        unread_count=4,
        ownership_changed_at=now,
        subject=None,
        started_at=now,
        last_message_at=now,
        closed_at=None,
        created_at=now,
        updated_at=now,
    )

    assert payload.owner_type == "human"
    assert payload.unread_count == 4
    assert payload.ownership_changed_at == now
