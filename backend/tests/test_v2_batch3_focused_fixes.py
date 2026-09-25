from __future__ import annotations

from datetime import UTC, datetime, timedelta

from app.agents.v2.semantic_context import build_semantic_context
from app.agents.v2.turn_contract import (
    AppointmentSelector,
    DateConstraint,
    EntityReference,
    Selection,
    TiaTurnUnderstanding,
    TimeConstraint,
    TurnEntities,
    TurnOperation,
)
from app.agents.v2.turn_normalization import normalize_semantic_invariants
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

NOW = datetime(2026, 9, 25, 12, 0, tzinfo=UTC)
def _semantic():
    return build_semantic_context(
        {
            "services": [
                {"id": "svc-underarm", "name": "ليزر إبط"},
                {"id": "svc-bikini", "name": "ليزر بكيني"},
            ],
            "doctors": [{"id": "doc-1", "name": "أحمد"}],
            "appointments": [
                {
                    "appointment_id": "apt-1",
                    "service_id": "svc-underarm",
                    "doctor_id": "doc-1",
                    "status": "confirmed",
                    "start_local": "2026-09-28T12:00:00+03:00",
                },
                {
                    "appointment_id": "apt-2",
                    "service_id": "svc-underarm",
                    "doctor_id": "doc-1",
                    "status": "confirmed",
                    "start_local": "2026-09-30T12:00:00+03:00",
                },
            ],
        }
    )


def _authorized_booking() -> BookingTaskState:
    return BookingTaskState(
        write_authorization=WriteAuthorization(
            operation="booking",
            authorized=True,
            source_turn_id="booking-turn",
            granted_at=NOW - timedelta(minutes=1),
        ),
        constraints=CustomerConstraints(service_id="svc-underarm"),
    )


def _context(*, active_task=None, pending_choice=None) -> PlannerContext:
    return PlannerContext(
        semantic_context=_semantic(),
        active_task=active_task,
        pending_choice=pending_choice,
        now=NOW,
    )


def _candidate_snapshot(*, purpose="appointment", expires=None) -> OptionSnapshot:
    return OptionSnapshot(
        snapshot_id="verified-appointments",
        purpose=purpose,
        lifecycle_action="reschedule",
        task_version=1,
        created_at=NOW - timedelta(minutes=1),
        expires_at=expires or NOW + timedelta(minutes=14),
        options=[
            OptionChoice(ref="choice-1", label="الأول", payload={"appointment_id": "apt-1"}),
            OptionChoice(ref="choice-2", label="التاني", payload={"appointment_id": "apt-2"}),
        ]
        if purpose == "appointment"
        else [OptionChoice(ref="choice-2", label="التاني", payload={"appointment_id": "apt-2"})],
    )


def test_generic_financial_ownership_inside_booking_normalizes_to_handoff_only() -> None:
    financial = TurnOperation(
        type="pricing",
        entities=TurnEntities(service=EntityReference(ref="S1")),
        requested_service_details=["price"],
        financial_ownership="reception",
        execution_intent="informational",
    )
    normalized = normalize_semantic_invariants(
        TiaTurnUnderstanding(operations=[financial], safety_signals=[])
    )
    assert [item.type for item in normalized.operations] == ["human_support"]

    plan = plan_turn(normalized, _context(active_task=_authorized_booking()))
    assert plan.handoff_category == "payment"
    assert plan.steps[-1].disposition == "handoff"
    assert plan.steps[-1].facts["preserve_active_task"] is True
    assert all(not step.reads for step in plan.steps)


def test_service_price_inside_booking_remains_service_catalog_read() -> None:
    pricing = TurnOperation(
        type="pricing",
        entities=TurnEntities(service=EntityReference(ref="S1")),
        requested_service_details=["price"],
        financial_ownership="none",
        execution_intent="informational",
    )
    step = plan_turn(
        TiaTurnUnderstanding(operations=[pricing], safety_signals=[]),
        _context(active_task=_authorized_booking()),
    ).steps[0]
    assert step.disposition == "read"
    assert [read.kind for read in step.reads] == ["service_catalog"]
    assert step.reads[0].parameters == {"service_id": "svc-underarm"}


def test_reschedule_separates_source_date_from_replacement_date_and_time() -> None:
    operation = TurnOperation(
        type="reschedule",
        source_appointment=AppointmentSelector(
            date=DateConstraint(mode="exact", start_date="2026-09-28")
        ),
        entities=TurnEntities(
            date=DateConstraint(mode="exact", start_date="2026-09-30"),
            time=TimeConstraint(mode="exact", start_time="12:00"),
        ),
    )
    step = plan_turn(
        TiaTurnUnderstanding(operations=[operation], safety_signals=[]),
        _context(),
    ).steps[0]
    assert [read.kind for read in step.reads] == ["appointments", "availability"]
    assert step.reads[0].parameters == {
        "date": {"mode": "exact", "start_date": "2026-09-28", "end_date": None}
    }
    replacement = step.reads[1].parameters
    assert replacement["date"]["start_date"] == "2026-09-30"
    assert replacement["time"]["start_time"] == "12:00"
    assert replacement["reschedule"] is True
    assert step.write_intent is not None
    assert step.write_intent.parameters["date"]["start_date"] == "2026-09-30"
    assert "appointment_id" not in step.write_intent.parameters


def test_verified_appointment_candidate_two_selection_is_state_only() -> None:
    selection = TurnOperation(
        type="select_active",
        entities=TurnEntities(),
        selection=Selection(kind="index", index=2),
    )
    step = plan_turn(
        TiaTurnUnderstanding(operations=[selection], safety_signals=[]),
        _context(pending_choice=_candidate_snapshot()),
    ).steps[0]
    assert step.disposition == "clarify"
    assert step.write_intent is None
    assert step.facts["lifecycle_action"] == "reschedule"
    selected = step.facts["selected_option"]
    assert selected["payload"]["appointment_id"] == "apt-2"


def test_stale_verified_appointment_candidate_cannot_be_selected() -> None:
    selection = TurnOperation(
        type="select_active",
        entities=TurnEntities(),
        selection=Selection(kind="index", index=2),
    )
    step = plan_turn(
        TiaTurnUnderstanding(operations=[selection], safety_signals=[]),
        _context(
            pending_choice=_candidate_snapshot(
                expires=NOW - timedelta(seconds=1),
            )
        ),
    ).steps[0]
    assert step.disposition == "clarify"
    assert step.write_intent is None
    assert step.facts == {}


def test_selected_appointment_cancel_targets_exact_verified_candidate() -> None:
    target = _candidate_snapshot(purpose="appointment_target")
    target = target.model_copy(update={"lifecycle_action": "cancel_appointment"})
    operation = TurnOperation(
        type="cancel_appointment",
        entities=TurnEntities(service=EntityReference(ref="S1")),
    )
    step = plan_turn(
        TiaTurnUnderstanding(operations=[operation], safety_signals=[]),
        _context(pending_choice=target),
    ).steps[0]
    assert step.reads[0].parameters == {"appointment_id": "apt-2"}
    assert step.write_intent is not None
    assert step.write_intent.parameters == {"appointment_id": "apt-2"}

    ready = advance_step_after_verification(
        step,
        VerificationFacts(
            appointment_match_count=1,
            verified_parameters={"appointment_id": "apt-2"},
        ),
    )
    assert ready.disposition == "write_ready"
    assert ready.write_intent is not None
    assert ready.write_intent.parameters["appointment_id"] == "apt-2"


def test_selected_appointment_reschedule_uses_target_and_new_replacement() -> None:
    operation = TurnOperation(
        type="reschedule",
        entities=TurnEntities(
            service=EntityReference(ref="S2"),
            date=DateConstraint(mode="exact", start_date="2026-10-02"),
            time=TimeConstraint(mode="exact", start_time="14:00"),
        ),
    )
    step = plan_turn(
        TiaTurnUnderstanding(operations=[operation], safety_signals=[]),
        _context(pending_choice=_candidate_snapshot(purpose="appointment_target")),
    ).steps[0]
    assert step.reads[0].parameters == {"appointment_id": "apt-2"}
    replacement = step.reads[1].parameters
    assert replacement["service_id"] == "svc-bikini"
    assert replacement["date"]["start_date"] == "2026-10-02"
    assert replacement["time"]["start_time"] == "14:00"
    assert step.write_intent is not None
    assert step.write_intent.parameters["service_id"] == "svc-bikini"


def test_pending_appointment_target_beats_conflicting_catalog_scope() -> None:
    target = _candidate_snapshot(purpose="appointment_target")
    target = target.model_copy(update={"lifecycle_action": "cancel_appointment"})
    operation = TurnOperation(
        type="cancel_appointment",
        source_appointment=AppointmentSelector(service=EntityReference(ref="S2")),
        entities=TurnEntities(service=EntityReference(ref="S2")),
    )
    step = plan_turn(
        TiaTurnUnderstanding(operations=[operation], safety_signals=[]),
        _context(pending_choice=target),
    ).steps[0]
    assert step.reads[0].parameters == {"appointment_id": "apt-2"}
    assert "service_id" not in step.reads[0].parameters


def test_pending_appointment_choice_exposes_only_ephemeral_appointment_refs() -> None:
    from app.agents.v2.semantic_state_view import with_safe_task_context

    snapshot = _candidate_snapshot()
    safe = with_safe_task_context(
        _semantic(),
        pending_choice=snapshot.model_dump(mode="json"),
    )
    pending = safe.model_input["pending_choice"]
    assert pending["purpose"] == "appointment"
    assert pending["lifecycle_action"] == "reschedule"
    assert pending["options"][1]["appointment_ref"] == "A2"
    assert "appointment_id" not in pending["options"][1]
    assert "apt-2" not in repr(pending)


def test_source_selector_preserves_current_time_without_polluting_replacement() -> None:
    operation = TurnOperation(
        type="reschedule",
        source_appointment=AppointmentSelector(
            date=DateConstraint(mode="exact", start_date="2026-09-28"),
            time=TimeConstraint(mode="exact", start_time="12:00"),
        ),
        entities=TurnEntities(
            date=DateConstraint(mode="exact", start_date="2026-10-02"),
            time=TimeConstraint(mode="exact", start_time="14:00"),
        ),
    )
    step = plan_turn(
        TiaTurnUnderstanding(operations=[operation], safety_signals=[]),
        _context(),
    ).steps[0]
    source = step.reads[0].parameters
    replacement = step.reads[1].parameters
    assert source["date"]["start_date"] == "2026-09-28"
    assert source["time"]["start_time"] == "12:00"
    assert replacement["date"]["start_date"] == "2026-10-02"
    assert replacement["time"]["start_time"] == "14:00"
