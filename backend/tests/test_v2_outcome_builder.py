from __future__ import annotations

from datetime import UTC, datetime

import pytest

from app.agents.v2.semantic_context import build_semantic_context
from app.agents.v2.turn_contract import (
    EntityReference,
    TiaTurnUnderstanding,
    TimeConstraint,
    TurnEntities,
    TurnOperation,
)
from app.services.agent_v2.outcome_builder import (
    OutcomeBuildError,
    build_step_outcome,
    customer_visible_outcome,
)
from app.services.agent_v2.planner import PlanStep, ReadRequest, WriteIntent
from app.services.agent_v2.read_executor import ReadExecutionBundle, ReadResult

NOW = datetime(2026, 9, 11, 15, 0, tzinfo=UTC)


def _semantic_context():
    return build_semantic_context(
        {
            "services": [
                {"id": "service-1", "name": "ليزر إبط"},
                {"id": "service-2", "name": "ليزر بكيني"},
            ],
            "doctors": [{"id": "doctor-1", "name": "مريم"}],
            "appointments": [
                {
                    "appointment_id": "appointment-1",
                    "service_id": "service-1",
                    "doctor_id": "doctor-1",
                    "status": "confirmed",
                    "start_local": "2026-09-17T19:00:00+03:00",
                }
            ],
        }
    )


def _turn(operation: TurnOperation) -> TiaTurnUnderstanding:
    return TiaTurnUnderstanding(operations=[operation], safety_signals=[])


def test_semantic_service_ambiguity_becomes_labeled_choices_without_ids() -> None:
    context = _semantic_context()
    operation = TurnOperation(
        type="book",
        entities=TurnEntities(
            service=EntityReference(text="ليزر", ref=None, candidate_refs=["S1", "S2"])
        ),
        selection=None,
        package_usage="unspecified",
    )
    step = PlanStep(
        operation_index=0,
        operation_type="book",
        disposition="clarify",
        response_goal="ask_service_choice",
        clarification_field="service",
    )

    outcome = build_step_outcome(
        step,
        turn=_turn(operation),
        semantic_context=context,
    )
    visible = customer_visible_outcome(outcome)

    assert outcome.status == "needs_input"
    assert [choice.label for choice in outcome.choices] == ["ليزر إبط", "ليزر بكيني"]
    assert visible["choices"] == [
        {"label": "ليزر إبط", "facts": {}},
        {"label": "ليزر بكيني", "facts": {}},
    ]
    assert "S1" not in str(visible)
    assert "service-1" not in str(visible)


def test_availability_outcome_uses_windows_and_hides_canonical_ids() -> None:
    context = _semantic_context()
    operation = TurnOperation(
        type="availability",
        entities=TurnEntities(
            service=EntityReference(text=None, ref="S1", candidate_refs=[]),
        ),
        selection=None,
        package_usage="unspecified",
    )
    step = PlanStep(
        operation_index=0,
        operation_type="availability",
        disposition="read",
        reads=[ReadRequest(kind="availability")],
        response_goal="present_availability",
        facts={"service_id": "service-1"},
    )
    reads = ReadExecutionBundle(
        results=[
            ReadResult(
                kind="availability",
                ok=True,
                payload={
                    "service_id": "service-1",
                    "service_name": "ليزر إبط",
                    "checked_dates": ["2026-09-17"],
                    "slots": [
                        {
                            "branch_id": "branch-1",
                            "doctor_id": "doctor-1",
                            "doctor_name": "مريم",
                            "service_id": "service-1",
                            "service_name": "ليزر إبط",
                            "start_local": "2026-09-17T19:00:00+03:00",
                            "end_local": "2026-09-17T19:30:00+03:00",
                            "price_minor": 50000,
                            "currency": "EGP",
                            "laser_device_key": "candela_gentle",
                            "laser_device_name": "Candela Gentle",
                        },
                        {
                            "branch_id": "branch-1",
                            "doctor_id": "doctor-1",
                            "doctor_name": "مريم",
                            "service_id": "service-1",
                            "service_name": "ليزر إبط",
                            "start_local": "2026-09-17T19:30:00+03:00",
                            "end_local": "2026-09-17T20:00:00+03:00",
                            "price_minor": 50000,
                            "currency": "EGP",
                            "laser_device_key": "candela_gentle",
                            "laser_device_name": "Candela Gentle",
                        },
                    ],
                    "search_truncated": False,
                },
            )
        ]
    )

    outcome = build_step_outcome(
        step,
        turn=_turn(operation),
        semantic_context=context,
        reads=reads,
    )
    visible = customer_visible_outcome(outcome)
    availability = visible["facts"]["availability"]

    assert outcome.status == "answered"
    assert availability["price"] == "500.00 EGP"
    assert availability["availability_windows"] == [
        {
            "doctor_name": "مريم",
            "laser_device_name": "Candela Gentle",
            "start_local": "2026-09-17T19:00:00+03:00",
            "end_local": "2026-09-17T20:00:00+03:00",
            "start_time_24h": "19:00",
            "end_time_24h": "20:00",
        }
    ]
    assert "doctor-1" not in str(visible)
    assert "branch-1" not in str(visible)
    assert "service-1" not in str(visible)
    assert "candela_gentle" not in str(visible)


def test_empty_exact_availability_becomes_requested_time_unavailable() -> None:
    context = _semantic_context()
    operation = TurnOperation(
        type="availability",
        entities=TurnEntities(time=TimeConstraint(mode="exact", start_time="19:00", end_time=None)),
        selection=None,
        package_usage="unspecified",
    )
    step = PlanStep(
        operation_index=0,
        operation_type="availability",
        disposition="read",
        response_goal="present_availability",
        facts={"time": {"mode": "exact", "start_time": "19:00", "end_time": None}},
    )
    reads = ReadExecutionBundle(
        results=[
            ReadResult(
                kind="availability",
                ok=True,
                payload={"slots": [], "checked_dates": ["2026-09-17"]},
            )
        ]
    )

    outcome = build_step_outcome(
        step,
        turn=_turn(operation),
        semantic_context=context,
        reads=reads,
    )
    assert outcome.status == "blocked"
    assert outcome.response_goal == "requested_time_unavailable"


def test_ambiguous_verified_appointments_become_customer_choices() -> None:
    context = _semantic_context()
    operation = TurnOperation(
        type="cancel_appointment",
        entities=TurnEntities(),
        selection=None,
        package_usage="unspecified",
    )
    step = PlanStep(
        operation_index=0,
        operation_type="cancel_appointment",
        disposition="clarify",
        response_goal="ask_appointment_choice",
        clarification_field="appointment",
    )
    reads = ReadExecutionBundle(
        results=[
            ReadResult(
                kind="appointments",
                ok=True,
                payload={
                    "appointments": [
                        {
                            "appointment_id": "a-1",
                            "service_name": "ليزر إبط",
                            "doctor_name": "مريم",
                            "start_local": "2026-09-17T19:00:00+03:00",
                        },
                        {
                            "appointment_id": "a-2",
                            "service_name": "هيدرافيشل",
                            "doctor_name": "سارة",
                            "start_local": "2026-09-18T17:00:00+03:00",
                        },
                    ]
                },
            )
        ]
    )

    outcome = build_step_outcome(
        step,
        turn=_turn(operation),
        semantic_context=context,
        reads=reads,
    )
    visible = customer_visible_outcome(outcome)

    assert outcome.status == "needs_input"
    assert len(outcome.choices) == 2
    assert "a-1" not in str(visible)
    assert "a-2" not in str(visible)
    assert "ليزر إبط" in outcome.choices[0].label


def test_write_ready_step_cannot_claim_success_without_execution_result() -> None:
    context = _semantic_context()
    operation = TurnOperation(
        type="book",
        entities=TurnEntities(),
        selection=None,
        package_usage="unspecified",
    )
    step = PlanStep(
        operation_index=0,
        operation_type="book",
        disposition="write_ready",
        write_intent=WriteIntent(kind="booking", authorized=True, parameters={}),
        response_goal="booking_completed",
    )

    with pytest.raises(OutcomeBuildError):
        build_step_outcome(
            step,
            turn=_turn(operation),
            semantic_context=context,
        )


def test_successful_write_outcome_hides_action_identifiers_and_formats_money() -> None:
    context = _semantic_context()
    operation = TurnOperation(
        type="book",
        entities=TurnEntities(),
        selection=None,
        package_usage="unspecified",
    )
    step = PlanStep(
        operation_index=0,
        operation_type="book",
        disposition="write_ready",
        response_goal="booking_completed",
        write_intent=WriteIntent(kind="booking", authorized=True, parameters={}),
    )
    outcome = build_step_outcome(
        step,
        turn=_turn(operation),
        semantic_context=context,
        action_result={
            "ok": True,
            "appointment_id": "appointment-secret",
            "service_name": "ليزر إبط",
            "price_minor": 50000,
            "currency": "EGP",
        },
    )
    visible = customer_visible_outcome(outcome)

    assert outcome.status == "completed"
    assert visible["action_result"]["price"] == "500.00 EGP"
    assert "appointment-secret" not in str(visible)


def test_unsafe_refund_quote_becomes_blocked_staff_review() -> None:
    context = _semantic_context()
    operation = TurnOperation(
        type="refund_quote",
        entities=TurnEntities(),
        selection=None,
        package_usage="unspecified",
    )
    step = PlanStep(
        operation_index=0,
        operation_type="refund_quote",
        disposition="read",
        response_goal="package_refund_quote",
    )
    reads = ReadExecutionBundle(
        results=[
            ReadResult(
                kind="package_refund_quote",
                ok=False,
                payload={"quotes": [], "unsafe_package_ids": ["secret-package"]},
                error_code="refund_quote_requires_staff",
            )
        ]
    )

    outcome = build_step_outcome(
        step,
        turn=_turn(operation),
        semantic_context=context,
        reads=reads,
    )
    visible = customer_visible_outcome(outcome)

    assert outcome.status == "blocked"
    assert outcome.facts["requires_staff_review"] is True
    assert "secret-package" not in str(visible)
