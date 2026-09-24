from __future__ import annotations

from datetime import UTC, datetime

from app.agents.v2.semantic_context import build_semantic_context
from app.agents.v2.turn_contract import (
    DateConstraint,
    EntityReference,
    TiaTurnUnderstanding,
    TimeConstraint,
    TurnEntities,
    TurnOperation,
)
from app.agents.v2.turn_normalization import normalize_semantic_invariants
from app.services.agent_v2.planner import PlannerContext, plan_turn

NOW = datetime(2026, 9, 24, 12, 0, tzinfo=UTC)
SERVICE_ID = "service-prp"
DOCTOR_1 = "doctor-maha"
DOCTOR_2 = "doctor-sara"


def _context():
    return build_semantic_context(
        {
            "services": [
                {
                    "id": SERVICE_ID,
                    "name": "PRP",
                    "requires_laser_device": False,
                }
            ],
            "doctors": [
                {
                    "id": DOCTOR_1,
                    "name": "د. مها",
                    "service_ids": [SERVICE_ID],
                },
                {
                    "id": DOCTOR_2,
                    "name": "د. سارة",
                    "service_ids": [SERVICE_ID],
                },
            ],
            "branches": [],
        }
    )


def _doctor_set(*, mode: str = "set") -> EntityReference:
    return EntityReference(
        text="د. مها ود. سارة",
        ref=None,
        candidate_refs=["D1", "D2"],
        candidate_mode=mode,
    )


def _operation(
    *,
    operation_type: str = "book",
    execution_intent: str = "execute",
    doctor: EntityReference | None = None,
    date: DateConstraint | None = None,
    time: TimeConstraint | None = None,
) -> TurnOperation:
    return TurnOperation(
        type=operation_type,
        entities=TurnEntities(
            service=EntityReference(ref="S1"),
            doctor=doctor,
            date=date,
            time=time,
        ),
        execution_intent=execution_intent,
    )


def _normalized(operation: TurnOperation) -> TurnOperation:
    turn = TiaTurnUnderstanding(operations=[operation], safety_signals=[])
    return normalize_semantic_invariants(turn).operations[0]


def test_rc6_book_execute_doctor_set_next_available_normalizes_to_informational_availability() -> None:
    operation = _operation(
        doctor=_doctor_set(),
        date=DateConstraint(mode="next_available"),
    )

    normalized = _normalized(operation)

    assert normalized.type == "availability"
    assert normalized.execution_intent == "informational"


def test_rc6_normalization_preserves_doctor_candidates_and_service_scope() -> None:
    operation = _operation(
        doctor=_doctor_set(),
        date=DateConstraint(mode="next_available"),
    )

    normalized = _normalized(operation)

    assert normalized.entities.doctor == operation.entities.doctor
    assert normalized.entities.doctor is not None
    assert normalized.entities.doctor.candidate_refs == ["D1", "D2"]
    assert normalized.entities.doctor.candidate_mode == "set"
    assert normalized.entities.service == operation.entities.service
    assert normalized.entities.date == operation.entities.date


def test_single_doctor_booking_does_not_normalize() -> None:
    operation = _operation(
        doctor=EntityReference(text="د. مها", ref="D1"),
        date=DateConstraint(mode="next_available"),
    )

    normalized = _normalized(operation)

    assert normalized.type == "book"
    assert normalized.execution_intent == "execute"


def test_ambiguous_doctor_candidates_do_not_normalize() -> None:
    operation = _operation(
        doctor=_doctor_set(mode="ambiguous"),
        date=DateConstraint(mode="next_available"),
    )

    normalized = _normalized(operation)

    assert normalized.type == "book"
    assert normalized.execution_intent == "execute"


def test_doctor_set_exact_date_booking_does_not_normalize() -> None:
    operation = _operation(
        doctor=_doctor_set(),
        date=DateConstraint(mode="exact", start_date="2026-09-26"),
        time=TimeConstraint(mode="exact", start_time="18:00"),
    )

    normalized = _normalized(operation)

    assert normalized.type == "book"
    assert normalized.execution_intent == "execute"


def test_already_correct_informational_availability_is_unchanged() -> None:
    operation = _operation(
        operation_type="availability",
        execution_intent="informational",
        doctor=_doctor_set(),
        date=DateConstraint(mode="next_available"),
    )

    normalized = _normalized(operation)

    assert normalized == operation


def test_ordinary_booking_control_is_unchanged() -> None:
    operation = _operation(
        doctor=EntityReference(text="د. مها", ref="D1"),
        date=DateConstraint(mode="exact", start_date="2026-09-26"),
        time=TimeConstraint(mode="exact", start_time="18:00"),
    )

    normalized = _normalized(operation)

    assert normalized == operation


def test_normalized_doctor_comparison_plans_verified_availability_read_without_booking_write() -> None:
    operation = _operation(
        doctor=_doctor_set(),
        date=DateConstraint(mode="next_available"),
    )
    normalized_turn = normalize_semantic_invariants(
        TiaTurnUnderstanding(operations=[operation], safety_signals=[])
    )

    plan = plan_turn(
        normalized_turn,
        PlannerContext(
            semantic_context=_context(),
            active_task=None,
            now=NOW,
        ),
    )

    assert len(plan.steps) == 1
    step = plan.steps[0]
    assert step.operation_type == "availability"
    assert step.disposition == "read"
    assert step.clarification_field is None
    assert step.write_intent is None
    assert [read.kind for read in step.reads] == ["availability"]
    assert step.reads[0].parameters["service_id"] == SERVICE_ID
    assert step.reads[0].parameters["doctor_ids"] == [DOCTOR_1, DOCTOR_2]
    assert step.reads[0].parameters["date"] == {
        "mode": "next_available",
        "start_date": None,
        "end_date": None,
    }
