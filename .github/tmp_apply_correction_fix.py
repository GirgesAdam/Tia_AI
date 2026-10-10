from pathlib import Path

ROOT = Path("backend")


def patch(path: str, old: str, new: str) -> None:
    p = ROOT / path
    text = p.read_text(encoding="utf-8")
    if old not in text:
        raise RuntimeError(f"missing patch anchor in {path}: {old[:100]!r}")
    p.write_text(text.replace(old, new, 1), encoding="utf-8")


patch(
    "app/agents/v2/turn_contract.py",
    'ActiveTaskExplicitField = Literal["date", "time"]\nResponseDisposition = Literal["reply", "no_reply"]',
    'ActiveTaskExplicitField = Literal["date", "time"]\nActiveTaskClearField = Literal["doctor"]\nResponseDisposition = Literal["reply", "no_reply"]',
)
patch(
    "app/agents/v2/turn_contract.py",
    '''    active_task_explicit_fields: list[ActiveTaskExplicitField] = Field(\n        default_factory=list,\n        description=(\n            "For active_task_relationship=continue with reschedule only, list replacement date "\n            "and/or time exactly when that dimension is explicitly supplied in the latest customer "\n            "message. Never mark model-inferred/default constraints, values inherited from active_task, "\n            "source appointment facts, verified context, assistant prose, or older dialogue. Python "\n            "uses this provenance to distinguish customer-grounded replacement constraints from "\n            "model defaults while keeping active-task lifecycle deterministic."\n        ),\n    )\n''',
    '''    active_task_explicit_fields: list[ActiveTaskExplicitField] = Field(\n        default_factory=list,\n        description=(\n            "For active_task_relationship=continue with reschedule only, list replacement date "\n            "and/or time exactly when that dimension is explicitly supplied in the latest customer "\n            "message. Never mark model-inferred/default constraints, values inherited from active_task, "\n            "source appointment facts, verified context, assistant prose, or older dialogue. Python "\n            "uses this provenance to distinguish customer-grounded replacement constraints from "\n            "model defaults while keeping active-task lifecycle deterministic."\n        ),\n    )\n    cleared_active_task_fields: list[ActiveTaskClearField] = Field(\n        default_factory=list,\n        description=(\n            "Explicit sparse-patch CLEAR provenance for the supplied active task. In this contract "\n            "only doctor is supported: use doctor only when the latest customer message explicitly "\n            "removes any doctor preference while continuing the same booking/reschedule task. Do not "\n            "use this for an unknown/ungrounded doctor, a choice between doctors, or a request for a "\n            "different doctor. A cleared doctor must have entities.doctor=null; omission alone means KEEP."\n        ),\n    )\n''',
)
patch(
    "app/agents/v2/turn_contract.py",
    '''    @model_validator(mode="after")\n    def validate_automation_context_relationship(self) -> TurnOperation:\n''',
    '''    @model_validator(mode="after")\n    def validate_cleared_active_task_fields(self) -> TurnOperation:\n        cleared = set(self.cleared_active_task_fields)\n        if not cleared:\n            return self\n        if self.type not in {"book", "reschedule", "continue_active"}:\n            raise ValueError(\n                "cleared_active_task_fields is only valid for active booking/reschedule continuations."\n            )\n        if "doctor" in cleared and self.entities.doctor is not None:\n            raise ValueError("cleared active-task doctor requires entities.doctor=null.")\n        return self\n\n    @model_validator(mode="after")\n    def validate_automation_context_relationship(self) -> TurnOperation:\n''',
)

patch(
    "app/agents/v2/turn_interpreter.py",
    '''  message only authorizes/acknowledges the change without restating either dimension, leave this list\n  empty even if an inferred/default date or time entity is emitted.\n- Independently set fresh_task=true when the latest customer message explicitly opens a new/separate\n''',
    '''  message only authorizes/acknowledges the change without restating either dimension, leave this list\n  empty even if an inferred/default date or time entity is emitted.\n- cleared_active_task_fields is explicit CLEAR provenance, not omission. In this contract only doctor is\n  supported. When the customer explicitly removes any doctor preference for the current unfinished task,\n  set cleared_active_task_fields=[doctor] and leave entities.doctor null. Do not use CLEAR for an unknown or\n  ungrounded doctor name, a choice between doctors, or a request for a different doctor. For a different-doctor\n  request, leave doctor.ref null and use grounded doctor candidate_refs that reflect the requested alternatives;\n  do not include the currently selected doctor merely because it exists in active_task. Python verifies service\n  compatibility and never guesses among multiple alternatives.\n- Independently set fresh_task=true when the latest customer message explicitly opens a new/separate\n''',
)
patch(
    "app/agents/v2/turn_interpreter.py",
    '''  old device/date/time/doctor unless the latest message itself states them. Later answers inside the\n  new active task use fresh_task=false and active_task_relationship=continue where applicable.\n- When a customer corrects or changes a requirement in an active task, represent the new semantic\n''',
    '''  old device/date/time/doctor unless the latest message itself states them. Later answers inside the\n  new active task use fresh_task=false and active_task_relationship=continue where applicable.\n  Distinguish a correction of one requirement inside the same requested appointment from explicit abandonment\n  plus a new booking goal. If the customer says the prior service identification was wrong but is still working\n  on the same appointment, that is continue and only the service is replaced. If the customer explicitly drops\n  or abandons the unfinished booking and asks to book a different treatment instead, that is replace + fresh_task,\n  and only fields explicitly stated in that latest message belong in fresh_task_explicit_fields. Never infer\n  replacement merely because the service changed.\n- When a customer corrects or changes a requirement in an active task, represent the new semantic\n''',
)

patch(
    "app/agents/v2/availability_reference_interpreter.py",
    '''- Natural 12-hour clock wording without a colon/explicit AM-PM marker is semantic, not 24-hour authority.\n  If exactly one displayed option corresponds to that natural clock reading, select that supplied option_ref.\n  If more than one displayed option could correspond to it (for example both 03:00 and 15:00), clarify rather\n  than guessing. This preserves the conversational meaning of a displayed 3 PM option when the customer says\n  "3", without Python parsing the phrase.\n''',
    '''- Natural 12-hour clock wording without a colon/explicit AM-PM marker is semantic, not 24-hour authority.\n  If exactly one displayed option corresponds to that natural clock reading, select that supplied option_ref.\n  If more than one displayed option could correspond to it (for example both 03:00 and 15:00), clarify rather\n  than guessing. This preserves the conversational meaning of a displayed 3 PM option when the customer says\n  "3", without Python parsing the phrase.\n- A short/bare customer expression can sometimes reasonably denote both a displayed ordinal and a natural\n  clock time relevant to the displayed availability (for example a fourth option exists while 4 PM is also a\n  plausible time inside a displayed window). In that case return clarify. Do not choose the ordinal or the clock\n  interpretation, and do not mutate last_selected_option_ref based on a guess. Explicit ordinal wording remains\n  a displayed-option selection; an otherwise unambiguous clock-only correction remains a clock meaning.\n''',
)

patch(
    "app/services/agent_v2/active_task_progress.py",
    '''def _invalidate_incompatible_booking_identities(\n''',
    '''def _apply_explicit_active_task_clears(\n    params: dict[str, object],\n    *,\n    operation: TurnOperation,\n) -> dict[str, object]:\n    if "doctor" not in set(operation.cleared_active_task_fields):\n        return params\n    cleared = dict(params)\n    cleared["doctor_id"] = None\n    return cleared\n\n\ndef _verified_alternative_doctor_candidates(\n    operation: TurnOperation,\n    *,\n    service_id: str | None,\n    current_doctor_id: str | None,\n    context: SemanticContext,\n) -> list[tuple[str, str]] | None:\n    """Return server-compatible alternatives only when candidates explicitly exclude current doctor."""\n    entity = operation.entities.doctor\n    if (\n        entity is None\n        or entity.ref is not None\n        or entity.candidate_mode != "ambiguous"\n        or not entity.candidate_refs\n        or current_doctor_id is None\n        or service_id is None\n    ):\n        return None\n\n    grounded: list[tuple[str, str]] = []\n    for ref in dict.fromkeys(entity.candidate_refs):\n        target = context.reference_map.get(ref)\n        if target is None or target.kind != "doctor":\n            continue\n        grounded.append((ref, target.canonical_id))\n    if not grounded:\n        return None\n    if any(canonical_id == current_doctor_id for _, canonical_id in grounded):\n        return None\n\n    compatible: list[tuple[str, str]] = []\n    for ref, canonical_id in grounded:\n        if (\n            _identity_compatible_with_service(\n                context,\n                service_id=service_id,\n                identity_kind="doctor",\n                identity_id=canonical_id,\n            )\n            is True\n        ):\n            compatible.append((ref, canonical_id))\n    return compatible\n\n\ndef _explicit_unresolved_doctor(operation: TurnOperation) -> bool:\n    entity = operation.entities.doctor\n    return bool(\n        entity is not None\n        and entity.ref is None\n        and not entity.candidate_refs\n        and entity.text not in (None, "")\n        and "doctor" not in set(operation.cleared_active_task_fields)\n    )\n\n\ndef _doctor_choice_step(\n    step: PlanStep,\n    *,\n    params: dict[str, object],\n    verified_refs: list[str],\n) -> PlanStep:\n    return step.model_copy(\n        update={\n            "disposition": "clarify",\n            "state_action": "update_active",\n            "response_goal": "ask_doctor_choice",\n            "clarification_field": "doctor",\n            "facts": {\n                **params,\n                "doctor_id": None,\n                "_verified_candidate_refs": verified_refs,\n            },\n        }\n    )\n\n\ndef _invalidate_incompatible_booking_identities(\n''',
)
patch(
    "app/services/agent_v2/active_task_progress.py",
    '''    params = {\n        **_past_temporal_resume_updates(active_task, now=now),\n        **params,\n    }\n    return _invalidate_incompatible_booking_identities(\n''',
    '''    params = {\n        **_past_temporal_resume_updates(active_task, now=now),\n        **params,\n    }\n    params = _apply_explicit_active_task_clears(params, operation=operation)\n    return _invalidate_incompatible_booking_identities(\n''',
)
patch(
    "app/services/agent_v2/active_task_progress.py",
    '''    if isinstance(active_task, BookingTaskState):\n        if active_task.grouped is not None and operation.type in {"continue_active", "book"}:\n            return step.model_copy(update={"state_action": "none"})\n        if operation.type == "continue_active":\n''',
    '''    if isinstance(active_task, BookingTaskState):\n        if active_task.grouped is not None and operation.type in {"continue_active", "book"}:\n            return step.model_copy(update={"state_action": "none"})\n        if operation.type in {"continue_active", "book"}:\n            alternatives = _verified_alternative_doctor_candidates(\n                operation,\n                service_id=active_task.constraints.service_id,\n                current_doctor_id=active_task.constraints.doctor_id,\n                context=context,\n            )\n            if alternatives is not None:\n                params = _booking_followup_parameters(\n                    operation,\n                    active_task=active_task,\n                    context=context,\n                    now=now,\n                )\n                if len(alternatives) == 1:\n                    params["doctor_id"] = alternatives[0][1]\n                    return PlanStep(\n                        operation_index=step.operation_index,\n                        operation_type=operation.type,\n                        disposition="state_update",\n                        state_action="update_active",\n                        response_goal="clarification",\n                        facts=params,\n                    )\n                return _doctor_choice_step(\n                    step,\n                    params=params,\n                    verified_refs=[ref for ref, _ in alternatives],\n                )\n            doctor_entity = operation.entities.doctor\n            if (\n                doctor_entity is not None\n                and doctor_entity.ref is None\n                and doctor_entity.candidate_refs\n            ):\n                return step.model_copy(\n                    update={\n                        "disposition": "clarify",\n                        "state_action": "none",\n                        "response_goal": "ask_doctor_choice",\n                        "clarification_field": "doctor",\n                    }\n                )\n            if _explicit_unresolved_doctor(operation):\n                return step.model_copy(\n                    update={\n                        "disposition": "clarify",\n                        "state_action": "none",\n                        "response_goal": "clarification",\n                        "clarification_field": "doctor",\n                    }\n                )\n        if operation.type == "continue_active":\n''',
)
patch(
    "app/services/agent_v2/active_task_progress.py",
    '''    params = resolved_operation_parameters(operation, context=context)\n    explicit_target = params.pop("appointment_id", None)\n''',
    '''    alternatives = _verified_alternative_doctor_candidates(\n        operation,\n        service_id=active_task.replacement.service_id,\n        current_doctor_id=active_task.replacement.doctor_id,\n        context=context,\n    )\n    if alternatives is not None:\n        params = _apply_explicit_active_task_clears(\n            resolved_operation_parameters(operation, context=context),\n            operation=operation,\n        )\n        params.pop("appointment_id", None)\n        if len(alternatives) == 1:\n            params["doctor_id"] = alternatives[0][1]\n        else:\n            return _doctor_choice_step(\n                step,\n                params=params,\n                verified_refs=[ref for ref, _ in alternatives],\n            )\n    elif operation.entities.doctor is not None and operation.entities.doctor.ref is None:\n        if operation.entities.doctor.candidate_refs or _explicit_unresolved_doctor(operation):\n            return step.model_copy(\n                update={\n                    "disposition": "clarify",\n                    "state_action": "none",\n                    "response_goal": (\n                        "ask_doctor_choice"\n                        if operation.entities.doctor.candidate_refs\n                        else "clarification"\n                    ),\n                    "clarification_field": "doctor",\n                }\n            )\n        params = _apply_explicit_active_task_clears(\n            resolved_operation_parameters(operation, context=context),\n            operation=operation,\n        )\n    else:\n        params = _apply_explicit_active_task_clears(\n            resolved_operation_parameters(operation, context=context),\n            operation=operation,\n        )\n    explicit_target = params.pop("appointment_id", None)\n''',
)

patch(
    "app/services/agent_v2/orchestrator.py",
    '''            current_task = initial_transition.active_task\n            if current_task is not None:\n                effective_step = plan_active_task_progress(\n''',
    '''            current_task = initial_transition.active_task\n            if current_task is not None and effective_step.disposition != "clarify":\n                effective_step = plan_active_task_progress(\n''',
)

patch(
    "app/services/agent_v2/outcome_builder.py",
    '''    choices: list[OutcomeChoice] = []\n    for ref in entity.candidate_refs:\n''',
    '''    choices: list[OutcomeChoice] = []\n    verified_refs = step.facts.get("_verified_candidate_refs")\n    candidate_refs = verified_refs if isinstance(verified_refs, list) else entity.candidate_refs\n    for ref in candidate_refs:\n''',
)

TEST = r'''from datetime import UTC, datetime

import pytest
from pydantic import ValidationError

from app.agents.v2.availability_reference_interpreter import _SYSTEM_PROMPT as REFERENCE_PROMPT
from app.agents.v2.semantic_context import SemanticContext, build_semantic_context
from app.agents.v2.turn_contract import DateConstraint, EntityReference, TimeConstraint, TurnEntities, TurnOperation
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
    return next(ref for ref, target in context.reference_map.items() if target.kind == kind and target.canonical_id == canonical_id)


def _state(*, doctor_id: str | None = "doc-maha") -> BookingTaskState:
    return BookingTaskState(
        write_authorization=WriteAuthorization(operation="booking", authorized=True, source_turn_id="turn-start", granted_at=NOW),
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


def _apply(state: BookingTaskState, operation: TurnOperation, step: PlanStep, context: SemanticContext):
    adapted = adapt_matching_active_task_step(step, operation=operation, active_task=state, context=context, now=NOW)
    transition = apply_step_state(state, step=adapted, operation=operation, reads=None, now=NOW, turn_id="turn-correction")
    return adapted, transition.active_task


def test_explicit_doctor_clear_preserves_other_constraints() -> None:
    context = _context()
    state = _state()
    operation = TurnOperation(type="continue_active", entities=TurnEntities(), execution_intent="execute", cleared_active_task_fields=["doctor"])
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
        TurnOperation(type="book", entities=TurnEntities(doctor=EntityReference(text="Maha", ref=_ref(context, "doctor", "doc-maha"))), execution_intent="execute", cleared_active_task_fields=["doctor"])


def test_unknown_doctor_is_not_clear_and_does_not_mutate_current_doctor() -> None:
    context = _context()
    state = _state()
    operation = TurnOperation(type="book", entities=TurnEntities(doctor=EntityReference(text="XYZ")), execution_intent="execute", active_task_relationship="continue")
    adapted = adapt_matching_active_task_step(_step("book"), operation=operation, active_task=state, context=context, now=NOW)
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
        entities=TurnEntities(doctor=EntityReference(text="Maha or Maryam", candidate_refs=[_ref(context, "doctor", "doc-maha"), _ref(context, "doctor", "doc-maryam")])),
        execution_intent="execute",
        active_task_relationship="continue",
    )
    adapted = adapt_matching_active_task_step(_step("book", clarify_doctor=True), operation=operation, active_task=state, context=context, now=NOW)
    assert adapted.disposition == "clarify"
    assert adapted.state_action == "none"
    assert operation.cleared_active_task_fields == []


def test_another_doctor_one_compatible_candidate_resolves_without_guessing() -> None:
    context = _context(two_alternatives=False)
    state = _state()
    operation = TurnOperation(
        type="book",
        entities=TurnEntities(doctor=EntityReference(text="another doctor", candidate_refs=[_ref(context, "doctor", "doc-ahmed"), _ref(context, "doctor", "doc-hydra")])),
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
        entities=TurnEntities(doctor=EntityReference(text="another doctor", candidate_refs=[ahmed_ref, maryam_ref, _ref(context, "doctor", "doc-hydra")])),
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
    operation = TurnOperation(type="continue_active", entities=TurnEntities(doctor=EntityReference(text="another doctor", candidate_refs=[_ref(context, "doctor", "doc-hydra")])), execution_intent="execute")
    adapted, updated = _apply(state, operation, _step("continue_active"), context)
    assert adapted.disposition == "clarify"
    assert adapted.facts["_verified_candidate_refs"] == []
    assert isinstance(updated, BookingTaskState)
    assert updated.constraints.doctor_id is None


def test_clear_then_specific_doctor_sets_new_doctor() -> None:
    context = _context()
    state = _state()
    clear = TurnOperation(type="continue_active", entities=TurnEntities(), execution_intent="execute", cleared_active_task_fields=["doctor"])
    _, cleared = _apply(state, clear, _step("continue_active"), context)
    assert isinstance(cleared, BookingTaskState)
    set_doctor = TurnOperation(type="book", entities=TurnEntities(doctor=EntityReference(text="Ahmed", ref=_ref(context, "doctor", "doc-ahmed"))), execution_intent="execute", active_task_relationship="continue")
    _, updated = _apply(cleared, set_doctor, _step("book"), context)
    assert isinstance(updated, BookingTaskState)
    assert updated.constraints.doctor_id == "doc-ahmed"


def test_specific_doctor_then_clear_removes_preference() -> None:
    context = _context()
    state = _state(doctor_id="doc-ahmed")
    clear = TurnOperation(type="book", entities=TurnEntities(), execution_intent="execute", active_task_relationship="continue", cleared_active_task_fields=["doctor"])
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
'''

(ROOT / "tests/test_v2_correction_semantics_fix.py").write_text(TEST, encoding="utf-8")
print("focused correction patch applied")
