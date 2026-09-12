from __future__ import annotations

from datetime import UTC, datetime

from app.services.agent_v2.outcome import TurnOutcome
from app.services.agent_v2.planner import PlanStep
from app.services.agent_v2.state import BookingTaskState, WriteAuthorization
from app.services.agent_v2.state_executor import (
    StateTransition,
    finalize_step_after_state_transition,
)

NOW = datetime(2026, 9, 11, 18, 0, tzinfo=UTC)


def test_cancelled_active_task_becomes_terminal_answered_state_result() -> None:
    step = PlanStep(
        operation_index=0,
        operation_type="cancel_active",
        disposition="state_update",
        state_action="cancel_active",
        response_goal="clarification",
    )
    transition = StateTransition(
        active_task=None,
        changed=True,
        reason="cancel_active",
    )

    finalized = finalize_step_after_state_transition(step, transition)

    assert finalized.response_goal == "active_task_cancelled"
    assert finalized.facts["active_task_cancelled"] is True
    assert finalized.write_intent is None


def test_cancel_active_without_existing_task_does_not_claim_cancellation() -> None:
    step = PlanStep(
        operation_index=0,
        operation_type="cancel_active",
        disposition="state_update",
        state_action="cancel_active",
        response_goal="clarification",
    )
    transition = StateTransition(
        active_task=None,
        changed=False,
        reason="cancel_active",
    )

    finalized = finalize_step_after_state_transition(step, transition)

    assert finalized.response_goal == "clarification"
    assert finalized.facts["active_task_cancelled"] is False


def test_turn_outcome_strips_reference_metadata_recursively() -> None:
    outcome = TurnOutcome(
        status="completed",
        response_goal="booking_completed",
        facts={
            "selected_option_ref": "slot-2",
            "nested": {
                "service_ref": "S1",
                "candidate_refs": ["S1", "S2"],
                "label": "8 مساءً",
            },
        },
        action_result={
            "ok": True,
            "internal_ref": "write-7",
            "service_name": "ليزر إبط",
        },
        active_task_summary={
            "current_ref": "task-1",
            "status": "ready",
        },
    )

    assert outcome.facts == {"nested": {"label": "8 مساءً"}}
    assert outcome.action_result["service_name"] == "ليزر إبط"
    assert "internal_ref" not in outcome.action_result
    assert outcome.active_task_summary == {"status": "ready"}


def test_active_task_cancelled_is_not_a_clinic_write_completion() -> None:
    outcome = TurnOutcome(
        status="answered",
        response_goal="active_task_cancelled",
        facts={"active_task_cancelled": True},
    )

    assert outcome.status == "answered"
    assert outcome.action_result == {}


def test_reference_hygiene_does_not_mutate_server_state_objects() -> None:
    state = BookingTaskState(
        write_authorization=WriteAuthorization(
            operation="booking",
            authorized=True,
            source_turn_id="turn-secret",
            granted_at=NOW,
        )
    )

    TurnOutcome(
        status="answered",
        response_goal="present_availability",
        active_task_summary={
            "source_turn_ref": "turn-secret",
            "status": state.status,
        },
    )

    assert state.write_authorization.source_turn_id == "turn-secret"
