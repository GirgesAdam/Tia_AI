from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Any
from uuid import UUID

from langchain_core.messages import BaseMessage
from sqlalchemy.orm import Session

from app.agents.clinic_grounding import build_clinic_catalog
from app.agents.v2.responder import compose_v2_customer_reply
from app.agents.v2.semantic_context import SemanticContext, build_semantic_context
from app.agents.v2.semantic_state_view import with_safe_task_context
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
    load_active_task,
    save_active_task,
)


@dataclass(frozen=True)
class PendingV2Write:
    """Verified write boundary that this isolated runtime deliberately does not execute."""

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
) -> PersistedActiveTask | None:
    initial_task = initial.active_task if initial is not None else None
    if final_task == initial_task:
        return initial

    if final_task is None:
        if initial is not None:
            if not cancelled_existing_task:
                raise RuntimeError(
                    "V2 runtime may clear persisted state only through an explicit active-task cancellation."
                )
            cancel_active_task(
                db,
                workspace_id=workspace_id,
                conversation_id=conversation_id,
                patient_id=patient_id,
                expected=initial,
                run_id=run_id,
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
) -> V2OrchestratedTurn:
    """Run one isolated, stateful V2 turn without executing any business write.

    This coordinator owns no semantic or business rules. It loads durable V2 task state before
    interpretation, delegates language understanding to the structured interpreter, executes only
    deterministic reads/state transitions, persists the final verified task transition once, and
    renders a customer reply only when no real write is still required.

    The caller owns the outer database transaction. This function never commits and is not wired
    into production chat/customer delivery.
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

    if plan.handoff_category is not None:
        outcome = build_handoff_outcome(plan)
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
            active_task=initial_task,
            persisted_task=persisted,
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
    current_task = initial_task
    traces: list[V2RuntimeStepTrace] = []
    outcomes: list[TurnOutcome] = []
    pending_write: PendingV2Write | None = None
    cancelled_existing_task = False

    for planned_step in plan.steps:
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
        advanced = _advance_after_reads(effective_step, reads)
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

        outcome = build_step_outcome(
            advanced,
            turn=understanding,
            semantic_context=semantic_context,
            reads=reads if reads.results else None,
            action_result=None,
            active_task_summary=None,
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

    persisted_after = _persist_final_task(
        db=db,
        workspace_id=workspace.id,
        conversation_id=conversation_id,
        patient_id=patient.id,
        run_id=run_id,
        initial=persisted,
        final_task=current_task,
        cancelled_existing_task=cancelled_existing_task,
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