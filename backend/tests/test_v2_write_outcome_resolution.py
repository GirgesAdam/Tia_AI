from __future__ import annotations

from datetime import UTC, datetime

import pytest

from app.agents.v2.semantic_context import build_semantic_context
from app.agents.v2.turn_contract import TiaTurnUnderstanding, TurnEntities, TurnOperation
from app.services.agent_v2.outcome_builder import build_step_outcome
from app.services.agent_v2.planner import PlanStep, WriteIntent

NOW = datetime(2026, 9, 11, 15, 0, tzinfo=UTC)


def _context():
    return build_semantic_context({"services": [], "doctors": [], "appointments": []})


@pytest.mark.parametrize(
    ("operation_type", "write_kind", "pre_execution_goal", "expected_goal"),
    [
        ("book", "booking", "present_availability", "booking_completed"),
        ("confirm_appointment", "confirm_appointment", "clarification", "appointment_confirmed"),
        ("cancel_appointment", "cancel_appointment", "clarification", "cancellation_completed"),
        ("reschedule", "reschedule", "present_availability", "reschedule_completed"),
        ("buy_package", "buy_package", "package_information", "package_purchased"),
        ("follow_up", "follow_up", "clarification", "follow_up_created"),
        ("marketing_update", "marketing_update", "clarification", "marketing_updated"),
    ],
)
def test_successful_write_uses_terminal_goal_from_actual_write_kind(
    operation_type: str,
    write_kind: str,
    pre_execution_goal: str,
    expected_goal: str,
) -> None:
    operation = TurnOperation(
        type=operation_type,
        entities=TurnEntities(),
        selection=None,
        package_usage="unspecified",
        requested_service_details=[],
    )
    turn = TiaTurnUnderstanding(operations=[operation], safety_signals=[])
    step = PlanStep(
        operation_index=0,
        operation_type=operation_type,
        disposition="write_ready",
        write_intent=WriteIntent(kind=write_kind, authorized=True, parameters={}),
        response_goal=pre_execution_goal,
    )

    outcome = build_step_outcome(
        step,
        turn=turn,
        semantic_context=_context(),
        action_result={"ok": True},
    )

    assert outcome.status == "completed"
    assert outcome.response_goal == expected_goal


@pytest.mark.parametrize(
    ("operation_type", "write_kind", "stale_success_goal", "expected_failure_goal"),
    [
        ("book", "booking", "booking_completed", "clarification"),
        ("reschedule", "reschedule", "reschedule_completed", "clarification"),
        ("cancel_appointment", "cancel_appointment", "cancellation_completed", "clarification"),
        ("buy_package", "buy_package", "package_purchased", "package_information"),
    ],
)
def test_failed_write_cannot_keep_a_success_goal(
    operation_type: str,
    write_kind: str,
    stale_success_goal: str,
    expected_failure_goal: str,
) -> None:
    operation = TurnOperation(
        type=operation_type,
        entities=TurnEntities(),
        selection=None,
        package_usage="unspecified",
        requested_service_details=[],
    )
    turn = TiaTurnUnderstanding(operations=[operation], safety_signals=[])
    step = PlanStep(
        operation_index=0,
        operation_type=operation_type,
        disposition="write_ready",
        write_intent=WriteIntent(kind=write_kind, authorized=True, parameters={}),
        response_goal=stale_success_goal,
    )

    outcome = build_step_outcome(
        step,
        turn=turn,
        semantic_context=_context(),
        action_result={"ok": False, "error_code": "execution_failed"},
    )

    assert outcome.status == "blocked"
    assert outcome.response_goal == expected_failure_goal
