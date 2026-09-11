from __future__ import annotations

import pytest
from pydantic import ValidationError

from app.services.agent_v2.outcome import OutcomeChoice, TurnOutcome


def test_booking_outcome_contains_structured_facts_not_customer_copy() -> None:
    outcome = TurnOutcome(
        status="completed",
        response_goal="booking_completed",
        facts={
            "service": "ليزر إبط",
            "doctor": "مريم",
            "date": "2026-09-17",
            "time": "19:00",
            "billing": "package",
            "package_remaining": 4,
        },
        choices=[],
        action_result={"appointment_id": "appointment-1", "status": "confirmed"},
        active_task_summary={},
    )

    assert outcome.response_goal == "booking_completed"
    assert outcome.facts["package_remaining"] == 4
    assert "message" not in outcome.model_dump()
    assert "reply" not in outcome.model_dump()


def test_choice_goal_requires_verified_choices() -> None:
    with pytest.raises(ValidationError):
        TurnOutcome(
            status="needs_input",
            response_goal="ask_doctor_choice",
            facts={},
            choices=[],
            action_result={},
            active_task_summary={},
        )

    outcome = TurnOutcome(
        status="needs_input",
        response_goal="ask_doctor_choice",
        facts={"service": "ليزر إبط"},
        choices=[
            OutcomeChoice(ref="D1", label="مريم", facts={}),
            OutcomeChoice(ref="D2", label="سارة", facts={}),
        ],
        action_result={},
        active_task_summary={"task_type": "booking"},
    )
    assert len(outcome.choices) == 2


def test_handoff_status_cannot_masquerade_as_normal_response_goal() -> None:
    with pytest.raises(ValidationError):
        TurnOutcome(
            status="handoff",
            response_goal="answer_price",
            facts={},
            choices=[],
            action_result={},
            active_task_summary={},
        )

    outcome = TurnOutcome(
        status="handoff",
        response_goal="handoff",
        facts={"category": "medical", "priority": "urgent"},
        choices=[],
        action_result={},
        active_task_summary={},
    )
    assert outcome.status == "handoff"


def test_completed_outcome_rejects_pre_execution_response_goal() -> None:
    with pytest.raises(ValidationError):
        TurnOutcome(
            status="completed",
            response_goal="present_availability",
            facts={},
            choices=[],
            action_result={"ok": True},
            active_task_summary={},
        )


def test_terminal_write_goal_rejects_non_completed_status() -> None:
    with pytest.raises(ValidationError):
        TurnOutcome(
            status="blocked",
            response_goal="booking_completed",
            facts={},
            choices=[],
            action_result={"ok": False},
            active_task_summary={},
        )
