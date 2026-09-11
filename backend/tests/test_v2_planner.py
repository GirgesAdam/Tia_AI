from __future__ import annotations

from datetime import datetime, timedelta, timezone

from app.agents.v2.semantic_context import build_semantic_context
from app.agents.v2.turn_contract import (
    DateConstraint,
    EntityReference,
    Selection,
    TiaTurnUnderstanding,
    TimeConstraint,
    TurnEntities,
    TurnOperation,
)
from app.services.agent_v2.planner import (
    PlannerContext,
    VerificationFacts,
    advance_step_after_verification,
    plan_turn,
)
from app.services.agent_v2.state import (
    BookingTaskState,
    CustomerConstraints,
    OptionChoice,
    OptionSnapshot,
    WriteAuthorization,
)

NOW = datetime(2026, 9, 11, 15, 0, tzinfo=timezone.utc)


def _context(*, active_task=None) -> PlannerContext:
    semantic = build_semantic_context(
        {
            "services": [
                {"id": "service-underarm", "name": "ليزر إبط"},
                {"id": "service-bikini", "name": "ليزر بكيني"},
            ],
            "doctors": [
                {"id": "doctor-maryam", "name": "مريم"},
                {"id": "doctor-sarah", "name": "سارة"},
            ],
            "appointments": [
                {
                    "appointment_id": "appointment-1",
                    "service_id": "service-underarm",
                    "doctor_id": "doctor-maryam",
                    "status": "confirmed",
                    "start_local": "2026-09-17T19:00:00+03:00",
                }
            ],
        }
    )
    return PlannerContext(semantic_context=semantic, active_task=active_task, now=NOW)


def _operation(operation_type: str, **updates) -> TurnOperation:
    entities = TurnEntities(**updates)
    return TurnOperation(
        type=operation_type,
        entities=entities,
        selection=None,
        package_usage="unspecified",
    )


def test_availability_can_never_create_booking_write_intent() -> None:
    turn = TiaTurnUnderstanding(
        operations=[
            _operation(
                "availability",
                service=EntityReference(text=None, ref="S1", candidate_refs=[]),
                date=DateConstraint(mode="exact", start_date="2026-09-17", end_date=None),
                time=TimeConstraint(mode="exact", start_time="19:00", end_time=None),
            )
        ],
        safety_signals=[],
    )
    step = plan_turn(turn, _context()).steps[0]

    assert step.disposition == "read"
    assert step.write_intent is None
    assert [item.kind for item in step.reads] == ["availability"]


def test_exact_booking_is_not_write_ready_until_one_verified_slot_exists() -> None:
    turn = TiaTurnUnderstanding(
        operations=[
            _operation(
                "book",
                service=EntityReference(text=None, ref="S1", candidate_refs=[]),
                date=DateConstraint(mode="exact", start_date="2026-09-17", end_date=None),
                time=TimeConstraint(mode="exact", start_time="19:00", end_time=None),
            )
        ],
        safety_signals=[],
    )
    step = plan_turn(turn, _context()).steps[0]
    assert step.disposition == "read"
    assert step.write_intent is not None
    assert step.write_intent.kind == "booking"

    ready = advance_step_after_verification(
        step,
        VerificationFacts(
            exact_slot_match_count=1,
            verified_parameters={"start_at": "2026-09-17T19:00:00+03:00"},
        ),
    )
    assert ready.disposition == "write_ready"
    assert ready.write_intent is not None
    assert ready.write_intent.parameters["start_at"] == "2026-09-17T19:00:00+03:00"


def test_unavailable_exact_booking_is_blocked_instead_of_guessed() -> None:
    turn = TiaTurnUnderstanding(
        operations=[
            _operation(
                "book",
                service=EntityReference(text=None, ref="S1", candidate_refs=[]),
                date=DateConstraint(mode="exact", start_date="2026-09-17", end_date=None),
                time=TimeConstraint(mode="exact", start_time="19:00", end_time=None),
            )
        ],
        safety_signals=[],
    )
    step = plan_turn(turn, _context()).steps[0]
    blocked = advance_step_after_verification(
        step,
        VerificationFacts(exact_slot_match_count=0),
    )
    assert blocked.disposition == "blocked"
    assert blocked.response_goal == "requested_time_unavailable"


def test_broad_booking_window_never_auto_promotes_to_write() -> None:
    turn = TiaTurnUnderstanding(
        operations=[
            _operation(
                "book",
                service=EntityReference(text=None, ref="S1", candidate_refs=[]),
                date=DateConstraint(mode="exact", start_date="2026-09-17", end_date=None),
                time=TimeConstraint(mode="after", start_time="18:00", end_time=None),
            )
        ],
        safety_signals=[],
    )
    step = plan_turn(turn, _context()).steps[0]
    unchanged = advance_step_after_verification(
        step,
        VerificationFacts(exact_slot_match_count=1),
    )
    assert unchanged.disposition == "read"


def test_verified_booking_snapshot_selection_requires_persisted_write_authorization() -> None:
    snapshot = OptionSnapshot(
        snapshot_id="snapshot-1",
        purpose="booking_slot",
        task_version=5,
        created_at=NOW - timedelta(minutes=1),
        expires_at=NOW + timedelta(minutes=9),
        options=[
            OptionChoice(
                ref="slot-7",
                label="7:00",
                payload={"start_time_24h": "19:00", "start_at": "2026-09-17T19:00:00+03:00"},
            )
        ],
    )
    authorized_task = BookingTaskState(
        status="awaiting_choice",
        write_authorization=WriteAuthorization(
            operation="booking",
            authorized=True,
            source_turn_id="turn-1",
            granted_at=NOW - timedelta(minutes=2),
        ),
        constraints=CustomerConstraints(service_id="service-underarm"),
        option_snapshot=snapshot,
        version=5,
    )
    selection = TurnOperation(
        type="select_active",
        entities=TurnEntities(),
        selection=Selection(kind="time", index=None, time="19:00", ref=None),
        package_usage="unspecified",
    )
    turn = TiaTurnUnderstanding(operations=[selection], safety_signals=[])

    ready = plan_turn(turn, _context(active_task=authorized_task)).steps[0]
    assert ready.disposition == "write_ready"
    assert ready.write_intent is not None
    assert ready.write_intent.kind == "booking"

    unauthorized_task = authorized_task.model_copy(
        update={
            "write_authorization": WriteAuthorization(
                operation="booking",
                authorized=False,
                source_turn_id=None,
                granted_at=None,
            )
        }
    )
    no_write = plan_turn(turn, _context(active_task=unauthorized_task)).steps[0]
    assert no_write.disposition == "respond"
    assert no_write.write_intent is None


def test_stale_snapshot_selection_never_writes() -> None:
    snapshot = OptionSnapshot(
        snapshot_id="snapshot-old",
        purpose="booking_slot",
        task_version=4,
        created_at=NOW - timedelta(minutes=20),
        expires_at=NOW - timedelta(minutes=10),
        options=[OptionChoice(ref="slot-old", label="7:00", payload={"start_time_24h": "19:00"})],
    )
    task = BookingTaskState(
        status="awaiting_choice",
        write_authorization=WriteAuthorization(
            operation="booking",
            authorized=True,
            source_turn_id="turn-1",
            granted_at=NOW - timedelta(minutes=30),
        ),
        constraints=CustomerConstraints(service_id="service-underarm"),
        option_snapshot=snapshot,
        version=4,
    )
    turn = TiaTurnUnderstanding(
        operations=[
            TurnOperation(
                type="select_active",
                entities=TurnEntities(),
                selection=Selection(kind="index", index=1, time=None, ref=None),
                package_usage="unspecified",
            )
        ],
        safety_signals=[],
    )
    step = plan_turn(turn, _context(active_task=task)).steps[0]
    assert step.disposition == "clarify"
    assert step.write_intent is None


def test_cancel_active_is_not_appointment_cancellation() -> None:
    turn = TiaTurnUnderstanding(
        operations=[_operation("cancel_active")],
        safety_signals=[],
    )
    step = plan_turn(turn, _context()).steps[0]
    assert step.disposition == "state_update"
    assert step.state_action == "cancel_active"
    assert step.write_intent is None


def test_cancel_appointment_requires_verified_unique_patient_appointment() -> None:
    turn = TiaTurnUnderstanding(
        operations=[
            _operation(
                "cancel_appointment",
                appointment=EntityReference(text=None, ref="A1", candidate_refs=[]),
            )
        ],
        safety_signals=[],
    )
    step = plan_turn(turn, _context()).steps[0]
    assert step.disposition == "read"
    assert step.write_intent is not None

    ambiguous = advance_step_after_verification(
        step,
        VerificationFacts(appointment_match_count=2),
    )
    assert ambiguous.disposition == "clarify"
    assert ambiguous.clarification_field == "appointment"

    ready = advance_step_after_verification(
        step,
        VerificationFacts(
            appointment_match_count=1,
            verified_parameters={"appointment_id": "appointment-1"},
        ),
    )
    assert ready.disposition == "write_ready"


def test_medical_safety_overrides_simultaneous_booking() -> None:
    turn = TiaTurnUnderstanding(
        operations=[
            _operation(
                "book",
                service=EntityReference(text=None, ref="S1", candidate_refs=[]),
                date=DateConstraint(mode="exact", start_date="2026-09-17", end_date=None),
            )
        ],
        safety_signals=["urgent_medical", "medical"],
    )
    plan = plan_turn(turn, _context())
    assert plan.steps == []
    assert plan.handoff_category == "medical"
    assert plan.handoff_priority == "urgent"


def test_payment_question_and_payment_dispute_are_separate_semantics() -> None:
    safe_turn = TiaTurnUnderstanding(
        operations=[_operation("customer_history")],
        safety_signals=[],
    )
    safe = plan_turn(safe_turn, _context())
    assert safe.handoff_category is None
    assert safe.steps[0].reads[0].kind == "customer_history"

    dispute_turn = TiaTurnUnderstanding(
        operations=[_operation("customer_history")],
        safety_signals=["payment_dispute"],
    )
    dispute = plan_turn(dispute_turn, _context())
    assert dispute.steps == []
    assert dispute.handoff_category == "payment"


def test_marketing_false_is_an_explicit_write_not_missing_data() -> None:
    turn = TiaTurnUnderstanding(
        operations=[_operation("marketing_update", marketing_consent=False)],
        safety_signals=[],
    )
    step = plan_turn(turn, _context()).steps[0]
    assert step.disposition == "write_ready"
    assert step.write_intent is not None
    assert step.write_intent.parameters["marketing_consent"] is False


def test_compound_turn_produces_ordered_independent_steps() -> None:
    turn = TiaTurnUnderstanding(
        operations=[
            _operation(
                "pricing",
                service=EntityReference(text=None, ref="S1", candidate_refs=[]),
            ),
            _operation(
                "availability",
                service=EntityReference(text=None, ref="S1", candidate_refs=[]),
                date=DateConstraint(mode="exact", start_date="2026-09-19", end_date=None),
            ),
        ],
        safety_signals=[],
    )
    plan = plan_turn(turn, _context())
    assert [step.operation_type for step in plan.steps] == ["pricing", "availability"]
    assert plan.steps[0].write_intent is None
    assert plan.steps[1].write_intent is None
