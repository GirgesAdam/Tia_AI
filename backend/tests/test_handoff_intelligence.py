from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path
from types import SimpleNamespace
from uuid import uuid4

import pytest

import app.services.handoffs as handoff_service
from app.models.handoff_event import HandoffEvent
from app.models.handoff_request import HandoffRequest
from app.schemas.inbox import HandoffRead
from app.services.handoff_intelligence import build_handoff_context, merge_handoff_context
from app.services.handoffs import create_handoff


class _FakeDB:
    def __init__(self) -> None:
        self.added: list[object] = []
        self.commits = 0

    def add(self, value: object) -> None:
        self.added.append(value)

    def flush(self) -> None:
        for value in self.added:
            if hasattr(value, "id") and getattr(value, "id", None) is None:
                setattr(value, "id", uuid4())

    def commit(self) -> None:
        self.commits += 1

    def refresh(self, value: object) -> None:
        return None


def _conversation() -> SimpleNamespace:
    return SimpleNamespace(
        id=uuid4(),
        workspace_id=uuid4(),
        patient_id=uuid4(),
        owner_type="ai",
        status="open",
        assigned_user_id=None,
        unread_count=0,
        ownership_changed_at=datetime(2026, 8, 24, tzinfo=UTC),
        closed_at=None,
    )


def _patient(conversation: SimpleNamespace) -> SimpleNamespace:
    return SimpleNamespace(id=conversation.patient_id, workspace_id=conversation.workspace_id)


def _root() -> Path:
    return Path(__file__).resolve().parent.parent


def test_handoff_context_is_bounded_and_uses_existing_semantic_signals() -> None:
    context = build_handoff_context(
        trigger="semantic_policy",
        semantic_reason=" customer explicitly asked for a clinician ",
        confidence=0.93456,
        risk_flags=["medical", "medical", "urgent"],
        capabilities=["human_support", "appointment_creation"],
        latest_customer_message="x" * 3000,
        flow_type="booking",
        flow_status="collecting_requirements",
        missing_information=["doctor", "date"],
    )

    assert context["schema_version"] == 1
    assert context["trigger"] == "semantic_policy"
    assert context["risk_flags"] == ["medical", "urgent"]
    assert context["capabilities"] == ["human_support", "appointment_creation"]
    assert context["confidence"] == 0.9346
    assert len(context["latest_customer_message"]) == 1600
    assert context["flow"] == {
        "type": "booking",
        "status": "collecting_requirements",
        "missing_information": ["doctor", "date"],
    }


def test_handoff_context_merge_preserves_first_trigger_and_latest_snapshot() -> None:
    first = build_handoff_context(
        trigger="semantic_policy",
        semantic_reason="medical question",
        risk_flags=["medical"],
        capabilities=["human_support"],
        latest_customer_message="first",
    )
    merged_first = merge_handoff_context({}, first)
    second = build_handoff_context(
        trigger="agent_tool",
        semantic_reason="customer also asked for staff",
        risk_flags=["urgent"],
        capabilities=["human_support", "appointment_creation"],
        latest_customer_message="second",
    )
    merged = merge_handoff_context(merged_first, second)

    assert merged["first_trigger"] == "semantic_policy"
    assert merged["trigger"] == "agent_tool"
    assert merged["escalation_count"] == 2
    assert merged["risk_flags"] == ["medical", "urgent"]
    assert merged["latest_customer_message"] == "second"



def test_duplicate_handoff_context_is_idempotent() -> None:
    context = merge_handoff_context(
        {},
        build_handoff_context(
            trigger="semantic_policy",
            semantic_reason="same escalation",
            risk_flags=["medical"],
            latest_customer_message="same message",
        ),
    )
    repeated = merge_handoff_context(context, context)
    assert repeated == context
    assert repeated["escalation_count"] == 1

def test_new_handoff_persists_context_and_created_event_snapshot(monkeypatch: pytest.MonkeyPatch) -> None:
    conversation = _conversation()
    patient = _patient(conversation)
    db = _FakeDB()
    context = build_handoff_context(
        trigger="semantic_policy",
        semantic_reason="medical safety boundary",
        risk_flags=["medical"],
        latest_customer_message="هل ينفع العلاج مع دوائي؟",
    )

    monkeypatch.setattr(handoff_service, "lock_conversation_ownership", lambda *a, **k: conversation)
    monkeypatch.setattr(handoff_service, "get_active_handoff", lambda *a, **k: None)
    monkeypatch.setattr(handoff_service, "_quiesce_ai_before_staff", lambda *a, **k: None)

    handoff = create_handoff(
        db,  # type: ignore[arg-type]
        workspace_id=conversation.workspace_id,
        conversation=conversation,  # type: ignore[arg-type]
        patient=patient,  # type: ignore[arg-type]
        reason="medical safety boundary",
        category="medical",
        priority="high",
        handoff_context=context,
        commit=False,
    )

    assert isinstance(handoff, HandoffRequest)
    assert handoff.context_json["risk_flags"] == ["medical"]
    assert handoff.context_json["first_trigger"] == "semantic_policy"
    events = [item for item in db.added if isinstance(item, HandoffEvent)]
    assert len(events) == 1
    assert events[0].event_type == "created"
    assert events[0].metadata_json["context"] == handoff.context_json


def test_reused_handoff_escalates_in_place_and_records_audit_event(monkeypatch: pytest.MonkeyPatch) -> None:
    conversation = _conversation()
    patient = _patient(conversation)
    db = _FakeDB()
    existing = SimpleNamespace(
        id=uuid4(),
        workspace_id=conversation.workspace_id,
        conversation_id=conversation.id,
        patient_id=patient.id,
        category="other",
        priority="normal",
        reason="initial",
        context_json=merge_handoff_context(
            {}, build_handoff_context(trigger="semantic_policy", risk_flags=["complaint"])
        ),
        assigned_user_id=None,
    )

    monkeypatch.setattr(handoff_service, "lock_conversation_ownership", lambda *a, **k: conversation)
    monkeypatch.setattr(handoff_service, "get_active_handoff", lambda *a, **k: existing)
    monkeypatch.setattr(handoff_service, "_quiesce_ai_before_staff", lambda *a, **k: None)

    result = create_handoff(
        db,  # type: ignore[arg-type]
        workspace_id=conversation.workspace_id,
        conversation=conversation,  # type: ignore[arg-type]
        patient=patient,  # type: ignore[arg-type]
        reason="urgent follow-up",
        category="complaint",
        priority="urgent",
        handoff_context=build_handoff_context(
            trigger="agent_tool",
            risk_flags=["urgent"],
            latest_customer_message="عايز حد يكلمني حالًا",
        ),
        commit=False,
    )

    assert result is existing
    assert existing.category == "complaint"
    assert existing.priority == "urgent"
    assert existing.context_json["risk_flags"] == ["complaint", "urgent"]
    assert existing.context_json["escalation_count"] == 2
    events = [item for item in db.added if isinstance(item, HandoffEvent)]
    assert len(events) == 1
    assert events[0].event_type == "escalated"
    assert events[0].metadata_json["previous_priority"] == "normal"
    assert events[0].metadata_json["priority"] == "urgent"


def test_handoff_read_exposes_context_to_team_inbox() -> None:
    now = datetime(2026, 8, 24, tzinfo=UTC)
    value = HandoffRead(
        id=uuid4(), workspace_id=uuid4(), conversation_id=uuid4(), patient_id=uuid4(),
        status="pending", category="medical", priority="high", source="ai",
        reason="medical", context_json={"risk_flags": ["medical"]}, assigned_user_id=None,
        created_by_user_id=None, claimed_at=None, resolved_at=None, resolved_by_user_id=None,
        resolution_note=None, created_at=now, updated_at=now,
    )
    assert value.context_json == {"risk_flags": ["medical"]}


def test_agent_handoff_uses_same_turn_context_without_second_intelligence_model() -> None:
    agent_chat = (_root() / "app/services/agent_chat.py").read_text(encoding="utf-8")
    tools = (_root() / "app/agents/tools/clinic_tools.py").read_text(encoding="utf-8")

    assert "handoff_context=_handoff_context_for_turn(" in agent_chat
    assert 'trigger="semantic_policy" if policy.requires_human else "agent_tool"' in agent_chat
    assert "handoff_context=ctx.handoff_context" in tools
    assert "build_handoff_context(" not in tools


def test_handoff_intelligence_migration_is_incremental() -> None:
    migration = (_root() / "alembic/versions/0022_handoff_intelligence.py").read_text(
        encoding="utf-8"
    )
    assert 'down_revision: str | Sequence[str] | None = "0021_msg_cancelled"' in migration
    assert '"handoff_requests"' in migration
    assert '"context"' in migration
    assert "'escalated'" in migration


def test_adapter_requires_human_creates_real_handoff_not_status_only() -> None:
    tools = (_root() / "app/agents/tools/clinic_tools.py").read_text(encoding="utf-8")
    start = tools.index("def _set_handoff(")
    end = tools.index("def build_clinic_tools(", start)
    helper = tools[start:end]

    assert "create_handoff(" in helper
    assert 'source="system"' in helper
    assert 'category: str = "booking_exception"' in helper
    assert 'ctx.conversation.status = "pending"' not in helper
    assert '"handoff_id": str(handoff.id)' in tools
