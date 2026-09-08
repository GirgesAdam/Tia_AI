from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path
from types import SimpleNamespace

from app.services.conversation_ownership import (
    agent_can_reply,
    ai_dispatch_is_sendable,
    record_customer_inbound,
    return_to_ai,
    transfer_to_human,
)


def _conversation(*, changed_at: datetime) -> SimpleNamespace:
    return SimpleNamespace(
        owner_type="ai",
        status="open",
        assigned_user_id=None,
        unread_count=0,
        ownership_changed_at=changed_at,
        closed_at=None,
        last_message_at=changed_at,
    )


def test_inflight_ai_turn_cannot_revive_after_takeover_and_handback() -> None:
    started_at = datetime(2026, 9, 8, 12, 0, tzinfo=UTC)
    takeover_at = datetime(2026, 9, 8, 12, 1, tzinfo=UTC)
    handback_at = datetime(2026, 9, 8, 12, 2, tzinfo=UTC)
    new_inbound_at = datetime(2026, 9, 8, 12, 3, tzinfo=UTC)
    conversation = _conversation(changed_at=started_at)

    # First authority check captures the ownership epoch for this AI run.
    assert agent_can_reply(conversation) is True  # type: ignore[arg-type]

    transfer_to_human(conversation, now=takeover_at)  # type: ignore[arg-type]
    return_to_ai(conversation, now=handback_at)  # type: ignore[arg-type]

    # The old run stays invalid even though ownership is AI again.
    assert agent_can_reply(conversation) is False  # type: ignore[arg-type]

    # Only a genuinely new customer inbound starts a fresh AI turn.
    record_customer_inbound(conversation, now=new_inbound_at)  # type: ignore[arg-type]
    assert agent_can_reply(conversation) is True  # type: ignore[arg-type]


def test_pre_handback_conversational_dispatch_never_becomes_sendable_again() -> None:
    handback_at = datetime(2026, 9, 8, 12, 2, tzinfo=UTC)
    conversation = _conversation(changed_at=handback_at)
    stale_reply = SimpleNamespace(
        sender_type="ai",
        metadata_json={"in_reply_to_message_id": "old-customer-message"},
        created_at=datetime(2026, 9, 8, 12, 1, tzinfo=UTC),
    )

    assert not ai_dispatch_is_sendable(
        conversation=conversation,  # type: ignore[arg-type]
        message=stale_reply,  # type: ignore[arg-type]
        active_handoff=None,
    )


def test_independent_automation_is_not_blocked_by_conversation_handback_boundary() -> None:
    handback_at = datetime(2026, 9, 8, 12, 2, tzinfo=UTC)
    conversation = _conversation(changed_at=handback_at)
    automation_message = SimpleNamespace(
        sender_type="ai",
        metadata_json={"source": "automation_engine"},
        created_at=datetime(2026, 9, 8, 12, 1, tzinfo=UTC),
    )

    assert ai_dispatch_is_sendable(
        conversation=conversation,  # type: ignore[arg-type]
        message=automation_message,  # type: ignore[arg-type]
        active_handoff=None,
    )


def test_channel_guard_compares_processing_inbound_to_resolved_handoff_boundary() -> None:
    backend = Path(__file__).resolve().parent.parent
    source = (backend / "app/services/conversation_ownership.py").read_text(encoding="utf-8")

    assert "def _channel_turn_is_after_latest_handback(" in source
    assert "HandoffRequest.resolved_at" in source
    assert 'ChannelInboundEvent.status == "processing"' in source
    assert "_as_utc(inbound_created_at) > _as_utc(resolved_at)" in source


def test_resume_guard_uses_existing_state_only() -> None:
    backend = Path(__file__).resolve().parent.parent
    source = (backend / "app/services/conversation_ownership.py").read_text(encoding="utf-8")

    assert "HandoffRequest.resolved_at" in source
    assert "ownership_changed_at" in source
    assert "resume_after" not in source
