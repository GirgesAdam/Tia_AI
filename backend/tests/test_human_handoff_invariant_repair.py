from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace
from uuid import uuid4

import pytest

import app.services.handoffs as handoff_service
from app.models.handoff_request import HandoffRequest
from app.services.handoffs import create_handoff


class _FakeDB:
    def __init__(self) -> None:
        self.added: list[object] = []
        self.commits = 0
        self.refreshes: list[object] = []

    def add(self, value: object) -> None:
        self.added.append(value)

    def flush(self) -> None:
        for value in self.added:
            if hasattr(value, "id") and getattr(value, "id", None) is None:
                value.id = uuid4()

    def commit(self) -> None:
        self.commits += 1

    def refresh(self, value: object) -> None:
        self.refreshes.append(value)


def _root() -> Path:
    return Path(__file__).resolve().parents[2]


def test_create_handoff_repairs_human_owned_conversation_without_active_row(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    workspace_id = uuid4()
    patient_id = uuid4()
    conversation = SimpleNamespace(
        id=uuid4(),
        workspace_id=workspace_id,
        patient_id=patient_id,
        owner_type="human",
        status="pending",
        assigned_user_id=None,
        closed_at=None,
        ownership_changed_at=None,
    )
    patient = SimpleNamespace(id=patient_id, workspace_id=workspace_id)
    db = _FakeDB()

    monkeypatch.setattr(
        handoff_service,
        "lock_conversation_ownership",
        lambda *args, **kwargs: conversation,
    )
    monkeypatch.setattr(
        handoff_service,
        "get_active_handoff",
        lambda *args, **kwargs: None,
    )

    handoff = create_handoff(
        db,  # type: ignore[arg-type]
        workspace_id=workspace_id,
        conversation=conversation,  # type: ignore[arg-type]
        patient=patient,  # type: ignore[arg-type]
        reason="Repair missing active handoff.",
        source="staff",
        created_by_user_id=uuid4(),
        commit=False,
    )

    assert isinstance(handoff, HandoffRequest)
    assert handoff.status == "pending"
    assert handoff.conversation_id == conversation.id
    assert conversation.owner_type == "human"
    assert conversation.status == "pending"
    assert db.commits == 0


def test_repair_migration_backfills_only_open_human_conversations_without_active_handoff() -> None:
    migration = (
        _root() / "backend/alembic/versions/0027_human_handoff_invariant.py"
    ).read_text(encoding="utf-8")

    assert 'revision: str = "0027_human_handoff_invariant"' in migration
    assert 'down_revision: str | Sequence[str] | None = "0026_appointment_reminder_6h"' in migration
    assert "c.owner_type = 'human'" in migration
    assert "c.status <> 'closed'" in migration
    assert "h.status IN ('pending', 'claimed')" in migration
    assert '"source": "system"' in migration
    assert '"trigger": "ownership_invariant_repair"' in migration


def test_crm_human_ownership_routes_materialize_a_real_handoff() -> None:
    source = (_root() / "backend/app/api/routes/crm.py").read_text(encoding="utf-8")

    assert "def _ensure_crm_handoff(" in source
    assert source.count("_ensure_crm_handoff(") >= 3  # helper + create + update
    assert 'conversation.owner_type = "human"' not in source
    assert "create_handoff(" in source
    assert "assign_handoff(" in source
    assert "commit=False" in source


def test_team_inbox_offers_explicit_repair_action_for_missing_handoff() -> None:
    source = (
        _root() / "frontend/src/app/(dashboard)/inbox/[conversationId]/page.tsx"
    ).read_text(encoding="utf-8")

    assert 'conversation.owner_type === "ai"' in source
    assert "handoff && unassigned" in source
    assert source.count("<form action={takeOverConversation}>") >= 2
