from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path
from types import SimpleNamespace
from uuid import uuid4

from app.models.conversation import CONVERSATION_OWNER_TYPES
from app.schemas.inbox import ConversationReadReceipt
from app.services.conversation_ownership import (
    OWNER_AI,
    OWNER_HUMAN,
    agent_can_reply,
    mark_conversation_read,
    record_customer_inbound,
    return_to_ai,
    transfer_to_human,
)


def _conversation(**overrides: object) -> SimpleNamespace:
    values: dict[str, object] = {
        "owner_type": OWNER_AI,
        "status": "open",
        "assigned_user_id": None,
        "unread_count": 0,
        "ownership_changed_at": datetime(2026, 8, 24, tzinfo=UTC),
        "closed_at": None,
        "last_message_at": None,
    }
    values.update(overrides)
    return SimpleNamespace(**values)


def test_owner_contract_is_explicit_and_small() -> None:
    assert CONVERSATION_OWNER_TYPES == ("ai", "human")
    assert OWNER_AI == "ai"
    assert OWNER_HUMAN == "human"


def test_transfer_to_human_and_return_to_ai_are_deterministic() -> None:
    conversation = _conversation()
    user_id = uuid4()
    human_at = datetime(2026, 8, 24, 15, 0, tzinfo=UTC)
    ai_at = datetime(2026, 8, 24, 15, 5, tzinfo=UTC)

    transfer_to_human(conversation, assigned_user_id=user_id, now=human_at)
    assert conversation.owner_type == "human"
    assert conversation.assigned_user_id == user_id
    assert conversation.status == "pending"
    assert conversation.ownership_changed_at == human_at
    assert agent_can_reply(conversation) is False

    return_to_ai(conversation, now=ai_at)
    assert conversation.owner_type == "ai"
    assert conversation.assigned_user_id is None
    assert conversation.status == "open"
    assert conversation.closed_at is None
    assert conversation.ownership_changed_at == ai_at
    assert agent_can_reply(conversation) is True


def test_customer_inbound_updates_unread_state_and_read_clears_it() -> None:
    conversation = _conversation(unread_count=2)
    at = datetime(2026, 8, 24, 15, 10, tzinfo=UTC)

    record_customer_inbound(conversation, now=at)
    assert conversation.unread_count == 3
    assert conversation.last_message_at == at

    mark_conversation_read(conversation)
    assert conversation.unread_count == 0


def test_pending_status_is_still_a_compatibility_pause() -> None:
    conversation = _conversation(owner_type="ai", status="pending")
    assert agent_can_reply(conversation) is False


def test_agent_runtime_rechecks_locked_ownership_before_outbound() -> None:
    backend = Path(__file__).resolve().parent.parent
    source = (backend / "app/services/agent_chat.py").read_text(encoding="utf-8")

    assert source.count("lock_conversation_ownership(") >= 1
    assert "populate_existing=True" in (
        backend / "app/services/conversation_ownership.py"
    ).read_text(encoding="utf-8")
    lock_pos = source.index("locked_conversation = lock_conversation_ownership(")
    outbound_pos = source.index("outbound = Message(", lock_pos)
    guard_pos = source.index("if (not agent_can_reply(conversation)", lock_pos)
    assert lock_pos < guard_pos < outbound_pos


def test_escalation_creates_real_handoff_instead_of_only_setting_pending() -> None:
    backend = Path(__file__).resolve().parent.parent
    source = (backend / "app/agents/tools/clinic_tools.py").read_text(encoding="utf-8")
    start = source.index("def escalate_to_human")
    end = source.index("return [", start)
    block = source[start:end]

    assert "create_handoff(" in block
    assert 'source="ai"' in block
    assert 'commit=False' in block
    assert 'ctx.conversation.status = "pending"' not in block


def test_handoff_transitions_drive_conversation_ownership() -> None:
    backend = Path(__file__).resolve().parent.parent
    source = (backend / "app/services/handoffs.py").read_text(encoding="utf-8")

    assert "transfer_to_human(conversation)" in source
    assert "assigned_user_id=user.id" in source
    assert "return_to_ai(" in source
    assert 'conversation.owner_type != "human"' in source


def test_migration_backfills_existing_human_owned_conversations() -> None:
    backend = Path(__file__).resolve().parent.parent
    migration = (backend / "alembic/versions/0020_conv_ownership.py").read_text(
        encoding="utf-8"
    )

    assert 'revision: str = "0020_conv_ownership"' in migration
    assert 'down_revision: str | Sequence[str] | None = "0019_appt_payments"' in migration
    assert 'sa.Column("owner_type"' in migration
    assert 'sa.Column("unread_count"' in migration
    assert "h.status IN ('pending', 'claimed')" in migration
    assert "c.status = 'pending'" in migration
    assert "c.assigned_user_id IS NOT NULL" in migration


def test_current_ai_handoff_can_send_one_ack_but_claimed_handoff_cannot() -> None:
    backend = Path(__file__).resolve().parent.parent
    source = (backend / "app/services/agent_chat.py").read_text(encoding="utf-8")

    assert "def _current_run_can_send_handoff_ack(" in source
    assert 'getattr(active_handoff, "source", None) != "ai"' in source
    assert 'getattr(active_handoff, "status", None) != "pending"' in source
    assert 'getattr(active_handoff, "assigned_user_id", None) is not None' in source
    assert 'AgentAction.tool_name == "escalate_to_human"' in source
    assert "and not handoff_ack_allowed" in source


def test_inbox_read_receipt_is_small_and_explicit() -> None:
    conversation_id = uuid4()
    receipt = ConversationReadReceipt(conversation_id=conversation_id)
    assert receipt.conversation_id == conversation_id
    assert receipt.unread_count == 0
