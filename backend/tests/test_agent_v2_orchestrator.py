from __future__ import annotations

from datetime import datetime
from types import SimpleNamespace
from uuid import uuid4

import pytest

from app.agents.v2.turn_contract import TiaTurnUnderstanding, TurnEntities, TurnOperation
from app.services.agent_v2 import orchestrator as runtime
from app.services.agent_v2.outcome import TurnOutcome
from app.services.agent_v2.planner import PlanStep, TurnPlan, WriteIntent
from app.services.agent_v2.state import BookingTaskState, CustomerConstraints, WriteAuthorization
from app.services.agent_v2.state_executor import StateTransition
from app.services.agent_v2.state_persistence import PersistedActiveTask, V2StateConflictError

_NOW = datetime(2026, 9, 12, 1, 0, 0)


def _booking_task(*, status: str = "collecting", version: int = 1) -> BookingTaskState:
    return BookingTaskState(
        status=status,
        write_authorization=WriteAuthorization(
            operation="booking",
            authorized=True,
            source_turn_id="turn-1",
            granted_at=_NOW,
        ),
        constraints=CustomerConstraints(service_id="service-1"),
        version=version,
    )


def _understanding(operation_type: str) -> TiaTurnUnderstanding:
    return TiaTurnUnderstanding(
        operations=[TurnOperation(type=operation_type, entities=TurnEntities())]
    )


def _runtime_args() -> dict[str, object]:
    return {
        "db": object(),
        "workspace": SimpleNamespace(id=uuid4()),
        "patient": SimpleNamespace(id=uuid4()),
        "conversation_id": uuid4(),
        "run_id": uuid4(),
        "history": [],
        "local_now": _NOW,
        "timezone_name": "Africa/Cairo",
        "clinic_name": "Tia Test Clinic",
        "catalog": {"fixture": True},
        "turn_id": "turn-1",
    }


def _patch_semantic_pipeline(
    monkeypatch: pytest.MonkeyPatch,
    *,
    persisted: PersistedActiveTask | None,
    understanding: TiaTurnUnderstanding,
    plan: TurnPlan,
) -> None:
    semantic_context = object()
    monkeypatch.setattr(runtime, "load_active_task", lambda *args, **kwargs: persisted)
    monkeypatch.setattr(runtime, "build_semantic_context", lambda catalog: semantic_context)
    monkeypatch.setattr(
        runtime,
        "with_safe_task_context",
        lambda context, *, active_task: context,
    )
    monkeypatch.setattr(
        runtime,
        "interpret_customer_turn_v2",
        lambda **kwargs: understanding,
    )
    monkeypatch.setattr(runtime, "plan_turn", lambda turn, context: plan)
    monkeypatch.setattr(
        runtime,
        "adapt_matching_active_task_step",
        lambda step, **kwargs: step,
    )
    monkeypatch.setattr(
        runtime,
        "persist_initial_task_intent",
        lambda step, **kwargs: step,
    )


def test_write_ready_persists_once_and_never_renders_success(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    understanding = _understanding("book")
    step = PlanStep(
        operation_index=0,
        operation_type="book",
        disposition="write_ready",
        write_intent=WriteIntent(
            kind="booking",
            authorized=True,
            requires_verification=False,
        ),
        state_action="start_booking",
    )
    plan = TurnPlan(steps=[step])
    _patch_semantic_pipeline(
        monkeypatch,
        persisted=None,
        understanding=understanding,
        plan=plan,
    )

    ready_task = _booking_task(status="ready", version=4)
    monkeypatch.setattr(
        runtime,
        "apply_step_state",
        lambda *args, **kwargs: StateTransition(
            active_task=ready_task,
            changed=True,
            reason="start_booking",
        ),
    )
    monkeypatch.setattr(
        runtime,
        "finalize_step_after_state_transition",
        lambda planned_step, transition: planned_step,
    )
    monkeypatch.setattr(
        runtime,
        "build_step_outcome",
        lambda *args, **kwargs: pytest.fail("write_ready must not build a success outcome"),
    )
    monkeypatch.setattr(
        runtime,
        "compose_v2_customer_reply",
        lambda **kwargs: pytest.fail("write_ready must not render a customer success reply"),
    )

    save_calls: list[dict[str, object]] = []
    persisted_after = PersistedActiveTask(
        active_task=ready_task,
        flow_id=uuid4(),
        flow_version=7,
    )

    def save_once(*args: object, **kwargs: object) -> PersistedActiveTask:
        save_calls.append(dict(kwargs))
        return persisted_after

    monkeypatch.setattr(runtime, "save_active_task", save_once)
    monkeypatch.setattr(
        runtime,
        "cancel_active_task",
        lambda *args, **kwargs: pytest.fail("write_ready must not cancel state"),
    )

    result = runtime.orchestrate_v2_turn(**_runtime_args())

    assert result.pending_write is not None
    assert result.pending_write.step.disposition == "write_ready"
    assert result.reply is None
    assert result.responder_model is None
    assert result.outcomes == ()
    assert result.active_task == ready_task
    assert result.persisted_task == persisted_after
    assert len(save_calls) == 1
    assert save_calls[0]["expected"] is None
    assert save_calls[0]["active_task"].version == 4
    assert result.traces[0].pending_write is True


def test_unchanged_side_read_does_not_persist_task_again(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    task = _booking_task(version=3)
    persisted = PersistedActiveTask(active_task=task, flow_id=uuid4(), flow_version=11)
    understanding = _understanding("social")
    step = PlanStep(
        operation_index=0,
        operation_type="social",
        disposition="respond",
        state_action="none",
        response_goal="social_ack",
    )
    _patch_semantic_pipeline(
        monkeypatch,
        persisted=persisted,
        understanding=understanding,
        plan=TurnPlan(steps=[step]),
    )
    monkeypatch.setattr(
        runtime,
        "apply_step_state",
        lambda *args, **kwargs: StateTransition(
            active_task=task,
            changed=False,
            reason="side_read_preserved",
        ),
    )
    monkeypatch.setattr(
        runtime,
        "finalize_step_after_state_transition",
        lambda planned_step, transition: planned_step,
    )
    outcome = TurnOutcome(status="answered", response_goal="social_ack")
    monkeypatch.setattr(runtime, "build_step_outcome", lambda *args, **kwargs: outcome)
    monkeypatch.setattr(
        runtime,
        "compose_v2_customer_reply",
        lambda **kwargs: ("أهلًا بيك", "test-model"),
    )
    monkeypatch.setattr(
        runtime,
        "save_active_task",
        lambda *args, **kwargs: pytest.fail("unchanged state must not be saved again"),
    )
    monkeypatch.setattr(
        runtime,
        "cancel_active_task",
        lambda *args, **kwargs: pytest.fail("side read must not cancel active state"),
    )

    result = runtime.orchestrate_v2_turn(**_runtime_args())

    assert result.active_task == task
    assert result.persisted_task == persisted
    assert result.pending_write is None
    assert result.reply == "أهلًا بيك"
    assert result.outcomes == (outcome,)


def test_explicit_cancel_closes_persisted_task_once(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    task = _booking_task(version=5)
    persisted = PersistedActiveTask(active_task=task, flow_id=uuid4(), flow_version=13)
    understanding = _understanding("cancel_active")
    step = PlanStep(
        operation_index=0,
        operation_type="cancel_active",
        disposition="state_update",
        state_action="cancel_active",
        response_goal="clarification",
    )
    _patch_semantic_pipeline(
        monkeypatch,
        persisted=persisted,
        understanding=understanding,
        plan=TurnPlan(steps=[step]),
    )
    monkeypatch.setattr(
        runtime,
        "apply_step_state",
        lambda *args, **kwargs: StateTransition(
            active_task=None,
            changed=True,
            reason="cancel_active",
        ),
    )
    cancelled_step = step.model_copy(
        update={
            "response_goal": "active_task_cancelled",
            "facts": {"active_task_cancelled": True},
        }
    )
    monkeypatch.setattr(
        runtime,
        "finalize_step_after_state_transition",
        lambda planned_step, transition: cancelled_step,
    )
    outcome = TurnOutcome(status="answered", response_goal="active_task_cancelled")
    monkeypatch.setattr(runtime, "build_step_outcome", lambda *args, **kwargs: outcome)
    monkeypatch.setattr(
        runtime,
        "compose_v2_customer_reply",
        lambda **kwargs: ("تمام، ألغيت الطلب الحالي.", "test-model"),
    )
    monkeypatch.setattr(
        runtime,
        "save_active_task",
        lambda *args, **kwargs: pytest.fail("cancelled task must not be saved"),
    )

    cancel_calls: list[dict[str, object]] = []

    def cancel_once(*args: object, **kwargs: object) -> None:
        cancel_calls.append(dict(kwargs))

    monkeypatch.setattr(runtime, "cancel_active_task", cancel_once)

    result = runtime.orchestrate_v2_turn(**_runtime_args())

    assert result.active_task is None
    assert result.persisted_task is None
    assert result.pending_write is None
    assert result.reply == "تمام، ألغيت الطلب الحالي."
    assert len(cancel_calls) == 1
    assert cancel_calls[0]["expected"] == persisted


def test_stale_persistence_conflict_propagates_without_retry(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    understanding = _understanding("book")
    step = PlanStep(
        operation_index=0,
        operation_type="book",
        disposition="write_ready",
        write_intent=WriteIntent(
            kind="booking",
            authorized=True,
            requires_verification=False,
        ),
        state_action="start_booking",
    )
    _patch_semantic_pipeline(
        monkeypatch,
        persisted=None,
        understanding=understanding,
        plan=TurnPlan(steps=[step]),
    )
    ready_task = _booking_task(status="ready", version=2)
    monkeypatch.setattr(
        runtime,
        "apply_step_state",
        lambda *args, **kwargs: StateTransition(
            active_task=ready_task,
            changed=True,
            reason="start_booking",
        ),
    )
    monkeypatch.setattr(
        runtime,
        "finalize_step_after_state_transition",
        lambda planned_step, transition: planned_step,
    )
    monkeypatch.setattr(
        runtime,
        "compose_v2_customer_reply",
        lambda **kwargs: pytest.fail("conflicted state must never render a reply"),
    )

    attempts = 0

    def stale_save(*args: object, **kwargs: object) -> PersistedActiveTask:
        nonlocal attempts
        attempts += 1
        raise V2StateConflictError("stale flow version")

    monkeypatch.setattr(runtime, "save_active_task", stale_save)

    with pytest.raises(V2StateConflictError, match="stale flow version"):
        runtime.orchestrate_v2_turn(**_runtime_args())

    assert attempts == 1


def test_orchestrator_source_keeps_write_and_transaction_boundaries() -> None:
    source = runtime.__file__
    assert source is not None
    text = open(source, encoding="utf-8").read()

    assert ".commit(" not in text
    assert "complete_state_after_action" not in text
    assert "execute_booking" not in text
    assert "execute_reschedule" not in text
    assert "re.compile(" not in text
    assert "import re" not in text
