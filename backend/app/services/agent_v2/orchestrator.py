from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime
from typing import Any
from uuid import NAMESPACE_URL, UUID, uuid5

from langchain_core.messages import BaseMessage
from sqlalchemy.orm import Session

from app.agents.clinic_grounding import build_clinic_catalog
from app.agents.v2.responder import compose_v2_customer_reply
from app.agents.v2.semantic_context import SemanticContext, build_semantic_context
from app.agents.v2.semantic_state_view import with_safe_read_context, with_safe_task_context
from app.agents.v2.turn_contract import TiaTurnUnderstanding, TurnOperation
from app.agents.v2.turn_interpreter import interpret_customer_turn_v2
from app.integrations.clinic.base import ClinicAdapter
from app.models.patient import Patient
from app.models.workspace import Workspace
from app.services.agent_v2.active_task_progress import (
    adapt_matching_active_task_step,
    persist_initial_task_intent,
    plan_active_task_progress,
)
from app.services.agent_v2.compound_turn_policy import (
    apply_compound_runtime_cursor,
    completed_compound_booking_end,
    compound_anchor_key,
    compound_write_group,
    normalize_compound_turn_plan,
    resolve_compound_followup_after_reads,
)
from app.services.agent_v2.compound_visit_preflight import preflight_compound_visit_plan
from app.services.agent_v2.outcome import TurnOutcome
from app.services.agent_v2.outcome_builder import build_handoff_outcome, build_step_outcome
from app.services.agent_v2.planner import (
    PlannerContext,
    PlanStep,
    TurnPlan,
    advance_step_after_verification,
    plan_turn,
)
from app.services.agent_v2.read_executor import (
    ReadExecutionBundle,
    ReadExecutionContext,
    execute_step_reads,
)
from app.services.agent_v2.state import ActiveTaskState
from app.services.agent_v2.state_executor import (
    apply_step_state,
    finalize_step_after_state_transition,
)
from app.services.agent_v2.state_persistence import (
    PersistedActiveTask,
    cancel_active_task,
    complete_active_task,
    load_active_task,
    save_active_task,
)

V2WriteExecutor = Callable[[PlanStep], dict[str, object]]


@dataclass(frozen=True)
class PendingV2Write:
    """Verified write boundary returned when no real executor is supplied."""

    step: PlanStep
    reads: ReadExecutionBundle


@dataclass(frozen=True)
class V2RuntimeStepTrace:
    operation_index: int
    operation_type: str
    disposition_before: str
    disposition_after: str
    read_kinds: tuple[str, ...]
    outcome: TurnOutcome | None = None
    pending_write: bool = False


@dataclass(frozen=True)
class V2OrchestratedTurn:
    understanding: TiaTurnUnderstanding
    plan: TurnPlan
    traces: tuple[V2RuntimeStepTrace, ...]
    outcomes: tuple[TurnOutcome, ...]
    reply: str | None
    responder_model: str | None
    active_task: ActiveTaskState | None
    persisted_task: PersistedActiveTask | None
    pending_write: PendingV2Write | None


def _task_dict(active_task: ActiveTaskState | None) -> dict[str, Any] | None:
    return active_task.model_dump(mode="json") if active_task is not None else None


def _operation_for_step(
    understanding: TiaTurnUnderstanding,
    step: PlanStep,
) -> TurnOperation:
    try:
        return understanding.operations[step.operation_index]
    except IndexError as exc:
        raise RuntimeError("V2 plan referenced an operation outside the structured turn.") from exc


def _advance_after_reads(step: PlanStep, reads: ReadExecutionBundle) -> PlanStep:
    if step.write_intent is None or not step.reads:
        return step
    return advance_step_after_verification(step, reads.verification)


def _persist_final_task(
    *,
    db: Session,
    workspace_id: UUID,
    conversation_id: UUID,
    patient_id: UUID,
    run_id: UUID,
    initial: PersistedActiveTask | None,
    final_task: ActiveTaskState | None,
    cancelled_existing_task: bool,
    completed_existing_task_result: dict[str, object] | None,
) -> PersistedActiveTask | None:
    initial_task = initial.active_task if initial is not None else None
    if final_task == initial_task and completed_existing_task_result is None:
        return initial

    if final_task is None:
        if initial is not None:
            if completed_existing_task_result is not None:
                complete_active_task(
                    db,
                    workspace_id=workspace_id,
                    conversation_id=conversation_id,
                    patient_id=patient_id,
                    expected=initial,
                    run_id=run_id,
                    result=completed_existing_task_result,
                )
            elif cancelled_existing_task:
                cancel_active_task(
                    db,
                    workspace_id=workspace_id,
                    conversation_id=conversation_id,
                    patient_id=patient_id,
                    expected=initial,
                    run_id=run_id,
                )
            else:
                raise RuntimeError(
                    "V2 runtime may clear persisted state only through an explicit cancellation "
                    "or a completed terminal write."
                )
        return None

    return save_active_task(
        db,
        workspace_id=workspace_id,
        conversation_id=conversation_id,
        patient_id=patient_id,
        active_task=final_task,
        run_id=run_id,
        expected=initial,
    )


def orchestrate_v2_turn(
    *,
    db: Session,
    workspace: Workspace,
    patient: Patient,
    conversation_id: UUID,
    run_id: UUID,
    history: list[BaseMessage],
    local_now: datetime,
    timezone_name: str,
    clinic_name: str,
    catalog: dict[str, Any] | None = None,
    adapter: ClinicAdapter | None = None,
    turn_id: str | None = None,
    write_executor: V2WriteExecutor | None = None,
    recent_read_context: dict[str, Any] | None = None,
) -> V2OrchestratedTurn:
    """Run one stateful V2 turn with an optional verified-write executor.

    With no executor this preserves the isolated/shadow boundary and returns the first
    ``PendingV2Write`` without mutating clinic business data. Production may supply a
    real executor; successful writes are converted to verified outcomes and compound
    operations continue in order. The caller owns the outer database transaction.
    """
    persisted = load_active_task(
        db,
        workspace_id=workspace.id,
        conversation_id=conversation_id,
        patient_id=patient.id,
        run_id=run_id,
    )
    initial_task = persisted.active_task if persisted is not None else None

    canonical_catalog = catalog or build_clinic_catalog(db, workspace)
    semantic_context: SemanticContext = build_semantic_context(canonical_catalog)
    semantic_context = with_safe_task_context(
        semantic_context,
        active_task=_task_dict(initial_task),
    )
    semantic_context = with_safe_read_context(
        semantic_context,
        read_context=recent_read_context,
    )
    understanding = interpret_customer_turn_v2(
        history=history,
        semantic_context=semantic_context,
        timezone_name=timezone_name,
        local_now=local_now,
    )
    plan = plan_turn(
        understanding,
        PlannerContext(
            semantic_context=semantic_context,
            active_task=initial_task,
            now=local_now,
        ),
    )
    plan = normalize_compound_turn_plan(plan, catalog=canonical_catalog)

    if plan.handoff_category is not None:
        outcome = build_handoff_outcome(plan)
        if persisted is not None:
            cancel_active_task(
                db,
                workspace_id=workspace.id,
                conversation_id=conversation_id,
                patient_id=patient.id,
                expected=persisted,
                run_id=run_id,
                reason="human_handoff_requested",
            )
        reply, model = compose_v2_customer_reply(
            clinic_name=clinic_name,
            timezone_name=timezone_name,
            local_now=local_now,
            history=history,
            outcomes=[outcome],
        )
        return V2OrchestratedTurn(
            understanding=understanding,
            plan=plan,
            traces=(),
            outcomes=(outcome,),
            reply=reply,
            responder_model=model,
            active_task=None,
            persisted_task=None,
            pending_write=None,
        )

    read_context = ReadExecutionContext(
        db=db,
        workspace=workspace,
        patient=patient,
        now=local_now,
        catalog=canonical_catalog,
        adapter=adapter,
    )
    resolved_turn_id = turn_id or str(run_id)
    stable_visit_group_id = str(
        uuid5(NAMESPACE_URL, f"tia-v2-visit:{workspace.id}:{resolved_turn_id}")
    )
    plan = preflight_compound_visit_plan(
        plan,
        context=read_context,
        timezone_name=timezone_name,
        visit_group_id=stable_visit_group_id,
    )
    current_task = initial_task
    traces: list[V2RuntimeStepTrace] = []
    outcomes: list[TurnOutcome] = []
    pending_write: PendingV2Write | None = None
    cancelled_existing_task = False
    completed_existing_task_result: dict[str, object] | None = None
    compound_cursors: dict[str, datetime] = {}
    grouped_positions: dict[str, list[int]] = {}
    for position, grouped_step in enumerate(plan.steps):
        group = compound_write_group(grouped_step)
        if group is not None:
            grouped_positions.setdefault(group, []).append(position)
    active_group_key: str | None = None
    active_group_tx = None
    active_group_outcome_start = 0
    active_group_trace_start = 0

    for step_position, planned_step in enumerate(plan.steps):
        anchor_key = compound_anchor_key(planned_step)
        planned_step = apply_compound_runtime_cursor(
            planned_step,
            previous_end_at=compound_cursors.get(anchor_key) if anchor_key is not None else None,
            timezone_name=timezone_name,
        )
        operation = _operation_for_step(understanding, planned_step)
        effective_step = adapt_matching_active_task_step(
            planned_step,
            operation=operation,
            active_task=current_task,
            context=semantic_context,
        )
        effective_step = persist_initial_task_intent(
            effective_step,
            operation=operation,
            context=semantic_context,
        )
        step_group_key = compound_write_group(effective_step) or compound_write_group(planned_step)

        if effective_step.state_action == "update_active":
            initial_transition = apply_step_state(
                current_task,
                step=effective_step,
                operation=operation,
                reads=None,
                now=local_now,
                turn_id=resolved_turn_id,
            )
            current_task = initial_transition.active_task
            if current_task is not None:
                effective_step = plan_active_task_progress(
                    current_task,
                    operation_index=effective_step.operation_index,
                    context=semantic_context,
                )

        reads = (
            execute_step_reads(effective_step, read_context)
            if effective_step.reads
            else ReadExecutionBundle()
        )
        compound_advanced, reads, compound_handled = resolve_compound_followup_after_reads(
            effective_step,
            reads,
        )
        advanced = compound_advanced if compound_handled else _advance_after_reads(effective_step, reads)
        transition = apply_step_state(
            current_task,
            step=advanced,
            operation=operation,
            reads=reads if reads.results else None,
            now=local_now,
            turn_id=resolved_turn_id,
        )
        advanced = finalize_step_after_state_transition(advanced, transition)
        if (
            advanced.state_action == "cancel_active"
            and transition.changed
            and persisted is not None
            and transition.active_task is None
        ):
            cancelled_existing_task = True
        current_task = transition.active_task

        if advanced.disposition == "write_ready":
            if write_executor is None:
                pending_write = PendingV2Write(step=advanced, reads=reads)
                traces.append(
                    V2RuntimeStepTrace(
                        operation_index=advanced.operation_index,
                        operation_type=advanced.operation_type,
                        disposition_before=planned_step.disposition,
                        disposition_after=advanced.disposition,
                        read_kinds=tuple(result.kind for result in reads.results),
                        pending_write=True,
                    )
                )
                break

            if step_group_key is not None and active_group_tx is None:
                active_group_key = step_group_key
                active_group_outcome_start = len(outcomes)
                active_group_trace_start = len(traces)
                active_group_tx = db.begin_nested()

            action_result = write_executor(advanced)
            outcome = build_step_outcome(
                advanced,
                turn=understanding,
                semantic_context=semantic_context,
                reads=reads if reads.results else None,
                action_result=action_result,
                active_task_summary=_task_dict(current_task),
            )
            traces.append(
                V2RuntimeStepTrace(
                    operation_index=advanced.operation_index,
                    operation_type=advanced.operation_type,
                    disposition_before=planned_step.disposition,
                    disposition_after=advanced.disposition,
                    read_kinds=tuple(result.kind for result in reads.results),
                    outcome=outcome,
                )
            )
            outcomes.append(outcome)

            if outcome.status == "completed":
                if (
                    step_group_key is not None
                    and active_group_key == step_group_key
                    and grouped_positions.get(step_group_key)
                    and step_position == grouped_positions[step_group_key][-1]
                    and active_group_tx is not None
                ):
                    active_group_tx.commit()
                    active_group_tx = None
                    active_group_key = None
                write_kind = advanced.write_intent.kind if advanced.write_intent is not None else None
                if write_kind == "booking" and anchor_key is not None:
                    verified_end = completed_compound_booking_end(reads)
                    if verified_end is not None:
                        compound_cursors[anchor_key] = verified_end
                if current_task is not None and current_task.task_type == write_kind:
                    if (
                        persisted is not None
                        and persisted.active_task.task_type == current_task.task_type
                    ):
                        completed_existing_task_result = dict(action_result)
                    current_task = None
                continue

            if outcome.status == "handoff":
                if current_task is not None:
                    cancelled_existing_task = persisted is not None
                    current_task = None
            if step_group_key is not None and active_group_key == step_group_key and active_group_tx is not None:
                active_group_tx.rollback()
                active_group_tx = None
                active_group_key = None
                outcomes = outcomes[:active_group_outcome_start]
                traces = traces[:active_group_trace_start]
                outcomes.append(outcome)
                traces.append(
                    V2RuntimeStepTrace(
                        operation_index=advanced.operation_index,
                        operation_type=advanced.operation_type,
                        disposition_before=planned_step.disposition,
                        disposition_after=advanced.disposition,
                        read_kinds=tuple(result.kind for result in reads.results),
                        outcome=outcome,
                    )
                )
            break

        outcome = build_step_outcome(
            advanced,
            turn=understanding,
            semantic_context=semantic_context,
            reads=reads if reads.results else None,
            action_result=None,
            active_task_summary=None,
        )
        if step_group_key is not None and active_group_key == step_group_key and active_group_tx is not None:
            active_group_tx.rollback()
            active_group_tx = None
            active_group_key = None
            outcomes = outcomes[:active_group_outcome_start]
            traces = traces[:active_group_trace_start]
        traces.append(
            V2RuntimeStepTrace(
                operation_index=advanced.operation_index,
                operation_type=advanced.operation_type,
                disposition_before=planned_step.disposition,
                disposition_after=advanced.disposition,
                read_kinds=tuple(result.kind for result in reads.results),
                outcome=outcome,
            )
        )
        outcomes.append(outcome)
        if outcome.status == "handoff":
            if current_task is not None:
                cancelled_existing_task = persisted is not None
                current_task = None
            break

    if active_group_tx is not None:
        active_group_tx.rollback()
        outcomes = outcomes[:active_group_outcome_start]
        traces = traces[:active_group_trace_start]
        active_group_tx = None
        active_group_key = None

    persisted_after = _persist_final_task(
        db=db,
        workspace_id=workspace.id,
        conversation_id=conversation_id,
        patient_id=patient.id,
        run_id=run_id,
        initial=persisted,
        final_task=current_task,
        cancelled_existing_task=cancelled_existing_task,
        completed_existing_task_result=completed_existing_task_result,
    )

    if pending_write is not None:
        return V2OrchestratedTurn(
            understanding=understanding,
            plan=plan,
            traces=tuple(traces),
            outcomes=tuple(outcomes),
            reply=None,
            responder_model=None,
            active_task=current_task,
            persisted_task=persisted_after,
            pending_write=pending_write,
        )

    if not outcomes:
        raise RuntimeError("V2 runtime produced neither a customer outcome nor a pending write.")

    reply, model = compose_v2_customer_reply(
        clinic_name=clinic_name,
        timezone_name=timezone_name,
        local_now=local_now,
        history=history,
        outcomes=outcomes,
    )
    return V2OrchestratedTurn(
        understanding=understanding,
        plan=plan,
        traces=tuple(traces),
        outcomes=tuple(outcomes),
        reply=reply,
        responder_model=model,
        active_task=current_task,
        persisted_task=persisted_after,
        pending_write=None,
    )
