from __future__ import annotations

from datetime import UTC, datetime
from types import SimpleNamespace
from uuid import uuid4

import pytest
from langchain_core.messages import HumanMessage

from app.agents.structured_output import StructuredOutputError
from app.agents.v2.turn_contract import TiaTurnUnderstanding, TurnEntities, TurnOperation
from app.models.message import Message
from app.services.agent_v2 import live_chat
from app.services.agent_v2.orchestrator import (
    V2OrchestratedTurn,
    V2TurnInterpretationStructuredOutputError,
)
from app.services.agent_v2.planner import TurnPlan


class _FakeDB:
    def __init__(self) -> None:
        self.added: list[object] = []
        self.commits = 0
        self.rollbacks = 0

    def add(self, value: object) -> None:
        if isinstance(value, Message) and value.id is None:
            value.id = uuid4()
        self.added.append(value)

    def commit(self) -> None:
        self.commits += 1

    def rollback(self) -> None:
        self.rollbacks += 1


def _state():
    workspace_id = uuid4()
    patient_id = uuid4()
    conversation = SimpleNamespace(
        id=uuid4(),
        workspace_id=workspace_id,
        patient_id=patient_id,
        channel_connection_id=None,
        owner_type="ai",
        status="open",
        assigned_user_id=None,
        last_message_at=None,
    )
    return SimpleNamespace(
        workspace=SimpleNamespace(id=workspace_id, name="Linka Test", timezone="Africa/Cairo"),
        patient=SimpleNamespace(
            id=patient_id,
            workspace_id=workspace_id,
            preferred_language="ar",
        ),
        conversation=conversation,
        inbound=SimpleNamespace(
            id=uuid4(),
            content="second option time?",
            created_at=datetime(2026, 10, 10, 12, 0, tzinfo=UTC),
        ),
    )


def _patch_pre_interpretation(monkeypatch: pytest.MonkeyPatch, state, *, error: Exception) -> dict[str, object]:
    read_context = {"operation_type": "availability", "service_ref": "S1"}
    availability_context = {
        "last_selected_option_ref": "slot-2",
        "availability_reference_options": [{"option_ref": "slot-1"}, {"option_ref": "slot-2"}],
    }
    action_context = {"operation_type": "book", "appointment_id": str(uuid4())}
    pending_choice = {"kind": "appointment", "options": [{"ref": "A1"}]}
    automation_context = {"source": "automation_engine", "appointment_id": str(uuid4())}

    monkeypatch.setattr(live_chat, "get_active_handoff", lambda *a, **k: None)
    monkeypatch.setattr(live_chat, "agent_can_reply", lambda *_a, **_k: True)
    monkeypatch.setattr(
        live_chat,
        "lock_conversation_ownership",
        lambda *a, **k: state.conversation,
    )
    monkeypatch.setattr(
        live_chat,
        "_history_from_db",
        lambda *a, **k: [HumanMessage(content=state.inbound.content)],
    )
    monkeypatch.setattr(
        live_chat,
        "_workspace_clock",
        lambda *_a, **_k: ("Africa/Cairo", datetime(2026, 10, 10, 12, 0, tzinfo=UTC)),
    )
    monkeypatch.setattr(live_chat, "get_clinic_adapter", lambda **_k: object())
    monkeypatch.setattr(live_chat, "_recent_verified_read_context", lambda *a, **k: read_context)
    monkeypatch.setattr(
        live_chat,
        "_recent_availability_reference_context",
        lambda *a, **k: availability_context,
    )
    monkeypatch.setattr(
        live_chat,
        "_recent_verified_action_context",
        lambda *a, **k: action_context,
    )
    monkeypatch.setattr(
        live_chat,
        "_recent_pending_choice_context",
        lambda *a, **k: pending_choice,
    )
    monkeypatch.setattr(
        live_chat,
        "_recent_automation_context",
        lambda *a, **k: automation_context,
    )

    def fail_orchestrator(**_kwargs):
        raise error

    monkeypatch.setattr(live_chat, "orchestrate_v2_turn", fail_orchestrator)
    monkeypatch.setattr(
        live_chat,
        "execute_write_ready_step",
        lambda *a, **k: (_ for _ in ()).throw(AssertionError("write executor must not run")),
    )
    return {
        "read": read_context,
        "availability": availability_context,
        "action": action_context,
        "pending": pending_choice,
        "automation": automation_context,
    }


def test_structured_output_error_is_contained_with_safe_reply_and_zero_write(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    state = _state()
    db = _FakeDB()
    contexts = _patch_pre_interpretation(
        monkeypatch,
        state,
        error=V2TurnInterpretationStructuredOutputError("invalid structured result"),
    )

    result = live_chat._run_v2_after_inbound(
        db=db,  # type: ignore[arg-type]
        workspace=state.workspace,  # type: ignore[arg-type]
        patient=state.patient,  # type: ignore[arg-type]
        conversation=state.conversation,  # type: ignore[arg-type]
        inbound=state.inbound,  # type: ignore[arg-type]
        run_id=uuid4(),
        outbound_delivery_status="queued",
        source="test",
    )

    assert result.reply == live_chat._structured_interpretation_clarification_reply(state.patient)
    assert result.model == "deterministic:structured-output-clarification"
    assert result.handoff_required is False
    assert result.agent_paused is False
    assert db.commits == 1
    outbound = next(value for value in db.added if isinstance(value, Message))
    metadata = dict(outbound.metadata_json or {})
    assert metadata["v2_read_context"] == contexts["read"]
    assert metadata["v2_availability_reference_context"] == contexts["availability"]
    assert metadata["v2_action_context"] == contexts["action"]
    assert metadata["v2_pending_choice"] == contexts["pending"]
    assert metadata["v2_automation_context"] == contexts["automation"]
    failure = metadata["v2_structured_interpretation_failure"]
    assert failure["stage"] == "turn_interpretation"
    assert failure["category"] == "StructuredOutputError"
    forbidden = ("StructuredOutputError", "ValidationError", "Pydantic", "schema", "provider")
    assert not any(token.lower() in result.reply.lower() for token in forbidden)


def test_non_structured_exception_is_not_swallowed(monkeypatch: pytest.MonkeyPatch) -> None:
    state = _state()
    db = _FakeDB()
    _patch_pre_interpretation(monkeypatch, state, error=TypeError("programming bug"))

    with pytest.raises(TypeError, match="programming bug"):
        live_chat._run_v2_after_inbound(
            db=db,  # type: ignore[arg-type]
            workspace=state.workspace,  # type: ignore[arg-type]
            patient=state.patient,  # type: ignore[arg-type]
            conversation=state.conversation,  # type: ignore[arg-type]
            inbound=state.inbound,  # type: ignore[arg-type]
            run_id=uuid4(),
            outbound_delivery_status="sent",
            source="test",
        )

    assert not any(isinstance(value, Message) for value in db.added)
    assert db.commits == 0



def test_next_turn_recovers_normally_after_contained_failure(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    state = _state()
    db = _FakeDB()
    contexts = _patch_pre_interpretation(
        monkeypatch,
        state,
        error=V2TurnInterpretationStructuredOutputError("invalid structured result"),
    )
    first = live_chat._run_v2_after_inbound(
        db=db,  # type: ignore[arg-type]
        workspace=state.workspace,  # type: ignore[arg-type]
        patient=state.patient,  # type: ignore[arg-type]
        conversation=state.conversation,  # type: ignore[arg-type]
        inbound=state.inbound,  # type: ignore[arg-type]
        run_id=uuid4(),
        outbound_delivery_status="sent",
        source="test",
    )
    assert first.model == "deterministic:structured-output-clarification"

    recovered_turn = V2OrchestratedTurn(
        understanding=TiaTurnUnderstanding(
            operations=[
                TurnOperation(
                    type="social",
                    entities=TurnEntities(),
                    execution_intent="informational",
                )
            ]
        ),
        plan=TurnPlan(),
        traces=(),
        outcomes=(),
        reply="Recovered normally.",
        responder_model="test:recovered",
        active_task=None,
        persisted_task=None,
        pending_write=None,
    )
    monkeypatch.setattr(live_chat, "orchestrate_v2_turn", lambda **_kwargs: recovered_turn)
    monkeypatch.setattr(
        live_chat,
        "_verified_read_context_from_turn",
        lambda *a, **k: contexts["read"],
    )
    monkeypatch.setattr(
        live_chat,
        "_outbound_verified_action_context",
        lambda *a, **k: contexts["action"],
    )
    monkeypatch.setattr(
        live_chat,
        "_availability_reference_context_from_turn",
        lambda *a, **k: contexts["availability"],
    )
    second_inbound = SimpleNamespace(
        id=uuid4(),
        content="I mean the second option.",
        created_at=datetime(2026, 10, 10, 12, 1, tzinfo=UTC),
    )
    second = live_chat._run_v2_after_inbound(
        db=db,  # type: ignore[arg-type]
        workspace=state.workspace,  # type: ignore[arg-type]
        patient=state.patient,  # type: ignore[arg-type]
        conversation=state.conversation,  # type: ignore[arg-type]
        inbound=second_inbound,  # type: ignore[arg-type]
        run_id=uuid4(),
        outbound_delivery_status="sent",
        source="test",
    )

    assert second.reply == "Recovered normally."
    assert second.model == "test:recovered"



def test_structured_error_outside_typed_interpretation_boundary_is_not_swallowed(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    state = _state()
    db = _FakeDB()
    _patch_pre_interpretation(
        monkeypatch,
        state,
        error=StructuredOutputError("downstream structured bug"),
    )

    with pytest.raises(StructuredOutputError, match="downstream structured bug"):
        live_chat._run_v2_after_inbound(
            db=db,  # type: ignore[arg-type]
            workspace=state.workspace,  # type: ignore[arg-type]
            patient=state.patient,  # type: ignore[arg-type]
            conversation=state.conversation,  # type: ignore[arg-type]
            inbound=state.inbound,  # type: ignore[arg-type]
            run_id=uuid4(),
            outbound_delivery_status="sent",
            source="test",
        )

    assert not any(isinstance(value, Message) for value in db.added)
    assert db.commits == 0
