from __future__ import annotations

from datetime import UTC, datetime

from app.agents.v2.semantic_context import build_semantic_context
from app.agents.v2.turn_contract import (
    DateConstraint,
    EntityReference,
    TimeConstraint,
    TurnEntities,
    TurnOperation,
)
from app.services.agent_v2.active_task_progress import (
    persist_initial_task_intent,
    plan_active_task_progress,
)
from app.services.agent_v2.planner import PlanStep
from app.services.agent_v2.state import (
    BookingTaskState,
    CustomerConstraints,
    WriteAuthorization,
)

NOW = datetime(2026, 9, 11, 18, 0, tzinfo=UTC)


def _context():
    return build_semantic_context(
        {
            "services": [
                {
                    "id": "svc-underarm",
                    "name": "ليزر إبط",
                    "requires_laser_device": True,
                    "laser_devices": [
                        {"device_key": "candela_gentle", "device_name": "Candela Gentle"}
                    ],
                }
            ],
            "doctors": [],
        }
    )


def _authorization() -> WriteAuthorization:
    return WriteAuthorization(
        operation="booking",
        authorized=True,
        source_turn_id="turn-start",
        granted_at=NOW,
    )


def test_initial_booking_clarification_is_marked_for_state_persistence() -> None:
    context = _context()
    operation = TurnOperation(
        type="book",
        entities=TurnEntities(service=EntityReference(ref="S1")),
    )
    step = PlanStep(
        operation_index=0,
        operation_type="book",
        disposition="clarify",
        clarification_field="date",
        response_goal="clarification",
    )

    persisted = persist_initial_task_intent(step, operation=operation, context=context)

    assert persisted.state_action == "start_booking"
    assert persisted.facts["service_id"] == "svc-underarm"


def test_booking_progress_asks_only_for_missing_date() -> None:
    state = BookingTaskState(
        write_authorization=_authorization(),
        constraints=CustomerConstraints(service_id="svc-underarm"),
    )

    step = plan_active_task_progress(state, operation_index=0, context=_context())

    assert step.disposition == "clarify"
    assert step.clarification_field == "date"
    assert step.state_action == "update_active"


def test_booking_progress_reads_availability_once_service_and_date_are_known() -> None:
    state = BookingTaskState(
        write_authorization=_authorization(),
        constraints=CustomerConstraints(
            service_id="svc-underarm",
            date=DateConstraint(mode="exact", start_date="2026-09-12"),
            time=TimeConstraint(mode="after", start_time="18:00"),
        ),
    )

    step = plan_active_task_progress(state, operation_index=0, context=_context())

    assert step.disposition == "read"
    assert step.operation_type == "book"
    assert step.state_action == "update_active"
    assert [read.kind for read in step.reads] == ["availability"]
    assert step.write_intent is not None
    assert step.write_intent.kind == "booking"
    assert step.write_intent.authorized is True
    assert step.facts["exact_time_requested"] is False
    assert step.facts["service_requires_laser_device"] is True


def test_exact_time_is_planned_for_verification_not_immediate_success() -> None:
    state = BookingTaskState(
        write_authorization=_authorization(),
        constraints=CustomerConstraints(
            service_id="svc-underarm",
            date=DateConstraint(mode="exact", start_date="2026-09-12"),
            time=TimeConstraint(mode="exact", start_time="19:00"),
        ),
    )

    step = plan_active_task_progress(state, operation_index=0, context=_context())

    assert step.disposition == "read"
    assert step.facts["exact_time_requested"] is True
    assert step.write_intent is not None
    assert step.write_intent.requires_verification is True
