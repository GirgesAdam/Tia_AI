from datetime import UTC, datetime

import pytest
from pydantic import ValidationError

from app.agents.v2.availability_reference_interpreter import _SYSTEM_PROMPT as REFERENCE_PROMPT
from app.agents.v2.semantic_context import SemanticContext, build_semantic_context
from app.agents.v2.turn_contract import (
    DateConstraint,
    EntityReference,
    TimeConstraint,
    TurnEntities,
    TurnOperation,
)
from app.agents.v2.turn_interpreter import _interpreter_system_prompt
from app.services.agent_v2.active_task_progress import adapt_matching_active_task_step
from app.services.agent_v2.planner import PlanStep
from app.services.agent_v2.state import BookingTaskState, CustomerConstraints, WriteAuthorization
from app.services.agent_v2.state_executor import apply_step_state

NOW = datetime(2026, 10, 11, 10, 0, tzinfo=UTC)


def _context(*, two_alternatives: bool = True) -> SemanticContext:
    doctors = [
        {"id": "doc-maha", "name": "Maha", "service_ids": ["svc-prp"]},
        {"id": "doc-ahmed", "name": "Ahmed", "service_ids": ["svc-prp"]},
        {"id": "doc-hydra", "name": "Hydra", "service_ids": ["svc-hydra"]},
    ]
    if two_alternatives:
        doctors.insert(2, {"id": "doc-maryam", "name": "Maryam", "service_ids": ["svc-prp"]})
    return build_semantic_context(
        {
            "services": [
                {"id": "svc-prp", "name": "PRP", "requires_laser_device": False},
                {"id": "svc-hydra", "name": "Hydra", "requires_laser_device": False},
            ],
            "doctors": doctors,
            "appointments": [],
        }
    )


def _ref(context: SemanticContext, kind: str, canonical_id: str) -> str:
    return next(
        ref
        for ref, target in context.reference_map.items()
        if target.kind == kind and target.canonical_id == canonical_id
    )


def _state(*, doctor_id: str | None = "doc-maha") -> BookingTaskState:
    return BookingTaskState(
        write_authorization=WriteAuthorization(
            operation="booking",
            authorized=True,
            source_turn_id="turn-start",
            granted_at=NOW,
        ),
        constraints=CustomerConstraints(
            service_id="svc-prp",
            doctor_id=doctor_id,
            date=DateConstraint(mode="exact", start_date="2026-10-17"),
            time=TimeConstraint(mode="exact", start_time="15:00"),
            package_usage="unspecified",
        ),
    )


def _step(operation_type: str = "book", *, clarify_doctor: bool = False) -> PlanStep:
    return PlanStep(
        operation_index=0,
        operation_type=operation_type,
        disposition="clarify" if clarify_doctor else "state_update",
        state_action="none" if clarify_doctor else "update_active",
        response_goal="ask_doctor_choice" if clarify_doctor else "clarification",
        clarification_field="doctor" if clarify_doctor else None,
    )


def _apply(
    state: BookingTaskState,
    operation: TurnOperation,
    step: PlanStep,
    context: SemanticContext,
):
    adapted = adapt_matching_active_task_step(
        step,
        operation=operation,
        active_task=state,
        context=context,
        now=NOW,
    )
    transition = apply_step_state(
        state,
        step=adapted,
        operation=operation,
        reads=None,
        now=NOW,
        turn_id="turn-correction",
    )
    return adapted, transition.active_task


def test_explicit_doctor_clear_preserves_other_constraints() -> None:
    context = _context()
    state = _state()
    operation = TurnOperation(
        type="continue_active",
        entities=TurnEntities(),
        execution_intent="execute",
        cleared_active_task_fields=["doctor"],
    )
    adapted, updated = _apply(state, operation, _step("continue_active"), context)
    assert adapted.facts["doctor_id"] is None
    assert isinstance(updated, BookingTaskState)
    assert updated.constraints.doctor_id is None
    assert updated.constraints.service_id == state.constraints.service_id
    assert updated.constraints.date == state.constraints.date
    assert updated.constraints.time == state.constraints.time


def test_clear_marker_rejects_contradictory_doctor_entity() -> None:
    context = _context()
    with pytest.raises(ValidationError):
        TurnOperation(
            type="book",
            entities=TurnEntities(
                doctor=EntityReference(
                    text="Maha",
                    ref=_ref(context, "doctor", "doc-maha"),
                )
            ),
            execution_intent="execute",
            cleared_active_task_fields=["doctor"],
        )


def test_unknown_doctor_is_not_clear_and_does_not_mutate_current_doctor() -> None:
    context = _context()
    state = _state()
    operation = TurnOperation(
        type="book",
        entities=TurnEntities(doctor=EntityReference(text="XYZ")),
        execution_intent="execute",
        active_task_relationship="continue",
    )
    adapted = adapt_matching_active_task_step(
        _step("book"),
        operation=operation,
        active_task=state,
        context=context,
        now=NOW,
    )
    assert operation.cleared_active_task_fields == []
    assert adapted.disposition == "clarify"
    assert adapted.clarification_field == "doctor"
    assert adapted.state_action == "none"
    assert state.constraints.doctor_id == "doc-maha"


def test_ambiguous_doctor_choice_including_current_is_not_clear() -> None:
    context = _context()
    state = _state()
    operation = TurnOperation(
        type="book",
        entities=TurnEntities(
            doctor=EntityReference(
                text="Maha or Maryam",
                candidate_refs=[
                    _ref(context, "doctor", "doc-maha"),
                    _ref(context, "doctor", "doc-maryam"),
                ],
            )
        ),
        execution_intent="execute",
        active_task_relationship="continue",
    )
    adapted = adapt_matching_active_task_step(
        _step("book", clarify_doctor=True),
        operation=operation,
        active_task=state,
        context=context,
        now=NOW,
    )
    assert adapted.disposition == "clarify"
    assert adapted.state_action == "none"
    assert operation.cleared_active_task_fields == []


def test_another_doctor_one_compatible_candidate_resolves_without_guessing() -> None:
    context = _context(two_alternatives=False)
    state = _state()
    operation = TurnOperation(
        type="book",
        entities=TurnEntities(
            doctor=EntityReference(
                text="another doctor",
                candidate_refs=[
                    _ref(context, "doctor", "doc-ahmed"),
                    _ref(context, "doctor", "doc-hydra"),
                ],
            )
        ),
        execution_intent="execute",
        active_task_relationship="continue",
    )
    adapted, updated = _apply(state, operation, _step("book", clarify_doctor=True), context)
    assert adapted.disposition == "state_update"
    assert adapted.facts["doctor_id"] == "doc-ahmed"
    assert isinstance(updated, BookingTaskState)
    assert updated.constraints.doctor_id == "doc-ahmed"


def test_another_doctor_multiple_compatible_candidates_clears_old_and_clarifies() -> None:
    context = _context(two_alternatives=True)
    state = _state()
    ahmed_ref = _ref(context, "doctor", "doc-ahmed")
    maryam_ref = _ref(context, "doctor", "doc-maryam")
    operation = TurnOperation(
        type="book",
        entities=TurnEntities(
            doctor=EntityReference(
                text="another doctor",
                candidate_refs=[
                    ahmed_ref,
                    maryam_ref,
                    _ref(context, "doctor", "doc-hydra"),
                ],
            )
        ),
        execution_intent="execute",
        active_task_relationship="continue",
    )
    adapted, updated = _apply(state, operation, _step("book", clarify_doctor=True), context)
    assert adapted.disposition == "clarify"
    assert adapted.state_action == "update_active"
    assert adapted.clarification_field == "doctor"
    assert adapted.facts["doctor_id"] is None
    assert adapted.facts["_verified_candidate_refs"] == [ahmed_ref, maryam_ref]
    assert isinstance(updated, BookingTaskState)
    assert updated.constraints.doctor_id is None


def test_another_doctor_zero_compatible_candidates_clears_old_and_fails_closed() -> None:
    context = _context(two_alternatives=False)
    state = _state()
    operation = TurnOperation(
        type="continue_active",
        entities=TurnEntities(
            doctor=EntityReference(
                text="another doctor",
                candidate_refs=[_ref(context, "doctor", "doc-hydra")],
            )
        ),
        execution_intent="execute",
    )
    adapted, updated = _apply(state, operation, _step("continue_active"), context)
    assert adapted.disposition == "clarify"
    assert adapted.facts["_verified_candidate_refs"] == []
    assert isinstance(updated, BookingTaskState)
    assert updated.constraints.doctor_id is None


def test_clear_then_specific_doctor_sets_new_doctor() -> None:
    context = _context()
    state = _state()
    clear = TurnOperation(
        type="continue_active",
        entities=TurnEntities(),
        execution_intent="execute",
        cleared_active_task_fields=["doctor"],
    )
    _, cleared = _apply(state, clear, _step("continue_active"), context)
    assert isinstance(cleared, BookingTaskState)
    set_doctor = TurnOperation(
        type="book",
        entities=TurnEntities(
            doctor=EntityReference(
                text="Ahmed",
                ref=_ref(context, "doctor", "doc-ahmed"),
            )
        ),
        execution_intent="execute",
        active_task_relationship="continue",
    )
    _, updated = _apply(cleared, set_doctor, _step("book"), context)
    assert isinstance(updated, BookingTaskState)
    assert updated.constraints.doctor_id == "doc-ahmed"


def test_specific_doctor_then_clear_removes_preference() -> None:
    context = _context()
    state = _state(doctor_id="doc-ahmed")
    clear = TurnOperation(
        type="book",
        entities=TurnEntities(),
        execution_intent="execute",
        active_task_relationship="continue",
        cleared_active_task_fields=["doctor"],
    )
    _, updated = _apply(state, clear, _step("book"), context)
    assert isinstance(updated, BookingTaskState)
    assert updated.constraints.doctor_id is None


def test_prompts_require_ambiguity_clarification_and_fresh_task_replacement() -> None:
    assert "both a displayed ordinal and a natural" in REFERENCE_PROMPT
    assert "return clarify" in REFERENCE_PROMPT
    prompt = _interpreter_system_prompt(timezone_name="Africa/Cairo", local_now=NOW)
    assert "cleared_active_task_fields" in prompt
    assert "replace + fresh_task" in prompt
    assert "Never infer" in prompt
    assert "replacement merely because the service changed" in prompt