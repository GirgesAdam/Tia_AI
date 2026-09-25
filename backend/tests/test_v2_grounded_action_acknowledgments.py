from __future__ import annotations

from uuid import uuid4

import pytest

from app.agents.v2.turn_contract import (
    DateConstraint,
    EntityReference,
    Selection,
    TiaTurnUnderstanding,
    TimeConstraint,
    TurnEntities,
    TurnOperation,
)
from app.services.agent_v2.orchestrator import (
    _completed_action_context,
    _normalize_recent_action_acknowledgments,
)
from app.services.agent_v2.planner import (
    PlanStep,
    ReadRequest,
    TurnPlan,
    WriteIntent,
)


def _booking_step(
    *,
    service_id: str = "service-1",
    doctor_id: str = "doctor-1",
    device_key: str | None = "candela_gentle",
    date: str = "2026-09-25",
    time: str = "14:00",
    package_usage: str = "unspecified",
) -> PlanStep:
    facts: dict[str, object] = {
        "service_id": service_id,
        "doctor_id": doctor_id,
        "date": {"mode": "exact", "start_date": date, "end_date": None},
        "time": {
            "mode": "exact",
            "start_time": time,
            "end_time": None,
            "start_time_ambiguity": "none",
            "end_time_ambiguity": "none",
        },
        "package_usage": package_usage,
        "exact_time_requested": True,
    }
    if device_key is not None:
        facts["device_key"] = device_key
    return PlanStep(
        operation_index=0,
        operation_type="book",
        disposition="read",
        reads=[ReadRequest(kind="availability", parameters=dict(facts))],
        write_intent=WriteIntent(
            kind="booking",
            authorized=True,
            parameters=dict(facts),
        ),
        response_goal="present_availability",
        facts=facts,
    )


def _booking_operation() -> TurnOperation:
    return TurnOperation(
        type="book",
        entities=TurnEntities(
            service=EntityReference(ref="S1"),
            doctor=EntityReference(ref="D1"),
            device=EntityReference(ref="V1"),
            date=DateConstraint(mode="exact", start_date="2026-09-25"),
            time=TimeConstraint(mode="exact", start_time="14:00"),
        ),
        execution_intent="execute",
    )


def _recent_booking(**updates: object) -> dict[str, object]:
    base: dict[str, object] = {
        "operation_type": "book",
        "appointment_id": "appointment-1",
        "service_id": "service-1",
        "doctor_id": "doctor-1",
        "device_key": "candela_gentle",
        "start_at": "2026-09-25T11:00:00+00:00",
        "status": "confirmed",
        "package_usage": "unspecified",
    }
    base.update(updates)
    return base


def test_completed_booking_context_uses_verified_write_parameters() -> None:
    step = _booking_step().model_copy(
        update={
            "disposition": "write_ready",
            "write_intent": WriteIntent(
                kind="booking",
                authorized=True,
                parameters={
                    **_booking_step().facts,
                    "start_at": "2026-09-25T11:00:00+00:00",
                    "branch_id": "branch-1",
                },
            ),
        }
    )

    context = _completed_action_context(
        step,
        {
            "ok": True,
            "appointment_id": "appointment-1",
            "status": "confirmed",
        },
    )

    assert context is not None
    assert context["operation_type"] == "book"
    assert context["appointment_id"] == "appointment-1"
    assert context["service_id"] == "service-1"
    assert context["doctor_id"] == "doctor-1"
    assert context["device_key"] == "candela_gentle"
    assert context["start_at"] == "2026-09-25T11:00:00+00:00"
    assert context["status"] == "confirmed"


def test_completed_cancellation_context_requires_verified_success() -> None:
    step = PlanStep(
        operation_index=0,
        operation_type="cancel_appointment",
        disposition="write_ready",
        write_intent=WriteIntent(
            kind="cancel_appointment",
            authorized=True,
            parameters={"appointment_id": "appointment-1"},
        ),
        response_goal="cancellation_completed",
    )

    assert _completed_action_context(
        step,
        {"ok": True, "appointment_id": "appointment-1", "status": "cancelled"},
    ) == {
        "operation_type": "cancel_appointment",
        "appointment_id": "appointment-1",
        "status": "cancelled",
    }
    assert _completed_action_context(
        step,
        {"ok": False, "appointment_id": "appointment-1", "status": "cancelled"},
    ) is None


def test_same_effective_booking_becomes_acknowledgment_only() -> None:
    turn = TiaTurnUnderstanding(operations=[_booking_operation()])
    plan = TurnPlan(steps=[_booking_step()])

    normalized = _normalize_recent_action_acknowledgments(
        plan,
        turn,
        recent_action=_recent_booking(),
        timezone_name="Africa/Cairo",
    )

    step = normalized.steps[0]
    assert step.disposition == "respond"
    assert step.reads == []
    assert step.write_intent is None
    assert step.response_goal == "social_ack"
    assert step.facts == {
        "acknowledgment": {
            "action": "booking",
            "already_completed": True,
            "same_booking": True,
        }
    }


@pytest.mark.parametrize(
    ("step_updates", "recent_updates"),
    [
        ({"service_id": "service-2"}, {}),
        ({"doctor_id": "doctor-2"}, {}),
        ({"device_key": "prime_lase"}, {}),
        ({"date": "2026-09-26"}, {}),
        ({"time": "15:00"}, {}),
        ({}, {"status": "cancelled"}),
    ],
)
def test_different_or_inactive_booking_is_not_treated_as_duplicate(
    step_updates: dict[str, object],
    recent_updates: dict[str, object],
) -> None:
    step_kwargs = dict(step_updates)
    plan = TurnPlan(steps=[_booking_step(**step_kwargs)])
    turn = TiaTurnUnderstanding(operations=[_booking_operation()])

    normalized = _normalize_recent_action_acknowledgments(
        plan,
        turn,
        recent_action=_recent_booking(**recent_updates),
        timezone_name="Africa/Cairo",
    )

    assert normalized == plan


def test_bare_immediate_cancellation_after_completed_cancel_is_acknowledged() -> None:
    operation = TurnOperation(
        type="cancel_appointment",
        entities=TurnEntities(),
        execution_intent="execute",
    )
    step = PlanStep(
        operation_index=0,
        operation_type="cancel_appointment",
        disposition="read",
        reads=[ReadRequest(kind="appointments")],
        write_intent=WriteIntent(
            kind="cancel_appointment",
            authorized=True,
            parameters={},
        ),
        response_goal="cancellation_completed",
    )

    normalized = _normalize_recent_action_acknowledgments(
        TurnPlan(steps=[step]),
        TiaTurnUnderstanding(operations=[operation]),
        recent_action={
            "operation_type": "cancel_appointment",
            "appointment_id": "appointment-1",
            "status": "cancelled",
        },
        timezone_name="Africa/Cairo",
    )

    result = normalized.steps[0]
    assert result.disposition == "respond"
    assert result.reads == []
    assert result.write_intent is None
    assert result.facts["acknowledgment"] == {
        "action": "cancel_appointment",
        "already_completed": True,
    }


def test_different_explicit_cancellation_target_is_not_acknowledged() -> None:
    operation = TurnOperation(
        type="cancel_appointment",
        entities=TurnEntities(appointment=EntityReference(ref="A2")),
        execution_intent="execute",
    )
    step = PlanStep(
        operation_index=0,
        operation_type="cancel_appointment",
        disposition="read",
        reads=[ReadRequest(kind="appointments", parameters={"appointment_id": "appointment-2"})],
        write_intent=WriteIntent(
            kind="cancel_appointment",
            authorized=True,
            parameters={"appointment_id": "appointment-2"},
        ),
        response_goal="cancellation_completed",
        facts={"appointment_id": "appointment-2"},
    )
    plan = TurnPlan(steps=[step])

    normalized = _normalize_recent_action_acknowledgments(
        plan,
        TiaTurnUnderstanding(operations=[operation]),
        recent_action={
            "operation_type": "cancel_appointment",
            "appointment_id": "appointment-1",
            "status": "cancelled",
        },
        timezone_name="Africa/Cairo",
    )

    assert normalized == plan


def test_different_cancellation_selection_is_not_acknowledged_as_already_completed() -> None:
    operation = TurnOperation(
        type="cancel_appointment",
        entities=TurnEntities(),
        selection=Selection(kind="index", index=2),
        execution_intent="execute",
    )
    step = PlanStep(
        operation_index=0,
        operation_type="cancel_appointment",
        disposition="read",
        reads=[ReadRequest(kind="appointments")],
        write_intent=WriteIntent(
            kind="cancel_appointment",
            authorized=True,
            parameters={},
        ),
        response_goal="cancellation_completed",
    )
    plan = TurnPlan(steps=[step])

    normalized = _normalize_recent_action_acknowledgments(
        plan,
        TiaTurnUnderstanding(operations=[operation]),
        recent_action={
            "operation_type": "cancel_appointment",
            "appointment_id": "appointment-1",
            "status": "cancelled",
        },
        timezone_name="Africa/Cairo",
    )

    assert normalized == plan


def test_unrelated_social_followup_is_not_forced_into_completed_action_acknowledgment() -> None:
    operation = TurnOperation(type="social", entities=TurnEntities())
    step = PlanStep(
        operation_index=0,
        operation_type="social",
        disposition="respond",
        response_goal="social_ack",
    )
    plan = TurnPlan(steps=[step])

    normalized = _normalize_recent_action_acknowledgments(
        plan,
        TiaTurnUnderstanding(operations=[operation]),
        recent_action={
            "operation_type": "cancel_appointment",
            "appointment_id": "appointment-1",
            "status": "cancelled",
        },
        timezone_name="Africa/Cairo",
    )

    assert normalized == plan


def test_failed_or_unverified_write_never_creates_acknowledgment_context() -> None:
    step = _booking_step().model_copy(
        update={
            "disposition": "write_ready",
            "write_intent": WriteIntent(
                kind="booking",
                authorized=True,
                parameters={
                    **_booking_step().facts,
                    "start_at": "2026-09-25T11:00:00+00:00",
                },
            ),
        }
    )
    assert _completed_action_context(
        step,
        {
            "ok": False,
            "appointment_id": str(uuid4()),
            "status": "confirmed",
        },
    ) is None
