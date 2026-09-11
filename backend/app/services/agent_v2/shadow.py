from __future__ import annotations

from datetime import datetime
from typing import Any
from zoneinfo import ZoneInfo

from langchain_core.messages import BaseMessage
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy.orm import Session

from app.agents.clinic_grounding import build_clinic_catalog
from app.agents.v2.responder import compose_v2_customer_reply
from app.agents.v2.semantic_context import SemanticContext, build_semantic_context
from app.agents.v2.semantic_state_view import with_safe_task_context
from app.agents.v2.turn_contract import TiaTurnUnderstanding
from app.agents.v2.turn_interpreter import interpret_customer_turn_v2
from app.integrations.clinic.base import AppointmentReadRequest, ClinicCapability
from app.integrations.clinic.registry import get_clinic_adapter
from app.models.patient import Patient
from app.models.workspace import Workspace
from app.services.agent_v2.outcome import TurnOutcome
from app.services.agent_v2.outcome_builder import build_handoff_outcome, build_step_outcome
from app.services.agent_v2.planner import (
    PlannerContext,
    PlanStep,
    TurnPlan,
    VerificationFacts,
    plan_turn,
)
from app.services.agent_v2.read_executor import (
    ReadExecutionBundle,
    ReadExecutionContext,
    execute_step_reads,
)
from app.services.agent_v2.state import ActiveTaskState
from app.services.agent_v2.write_policy import advance_step_with_write_policies
from app.services.patient_packages import list_patient_packages


class StrictShadowModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


class ShadowStepTrace(StrictShadowModel):
    operation_index: int
    operation_type: str
    disposition_before: str
    disposition_after: str
    verification: VerificationFacts = Field(default_factory=VerificationFacts)
    read_kinds: list[str] = Field(default_factory=list)
    outcome: TurnOutcome | None = None
    write_preview: dict[str, object] | None = None
    skip_reason: str | None = None


class ShadowTurnResult(StrictShadowModel):
    understanding: TiaTurnUnderstanding
    plan: TurnPlan
    step_traces: list[ShadowStepTrace] = Field(default_factory=list)
    outcomes: list[TurnOutcome] = Field(default_factory=list)
    reply: str | None = None
    responder_model: str | None = None
    reply_skipped_reason: str | None = None


def _appointment_catalog_rows(
    *,
    db: Session,
    workspace: Workspace,
    patient: Patient,
    now: datetime,
) -> list[dict[str, object]]:
    adapter = get_clinic_adapter(db=db, workspace=workspace)
    adapter.require_capability(ClinicCapability.APPOINTMENTS_READ)
    response = adapter.get_patient_appointments(
        AppointmentReadRequest(
            patient_id=str(patient.id),
            include_past=False,
            now=now,
        )
    )
    timezone = ZoneInfo(workspace.timezone)
    rows: list[dict[str, object]] = []
    for item in response.appointments[:10]:
        start_local = (
            item.start_at.astimezone(timezone).isoformat()
            if item.start_at.tzinfo is not None
            else item.start_at.isoformat()
        )
        rows.append(
            {
                "appointment_id": item.appointment_id,
                "service_id": item.service_id,
                "service_name": item.service_name,
                "doctor_id": item.doctor_id,
                "doctor_name": item.doctor_name,
                "status": item.status,
                "start_local": start_local,
                "laser_device_key": item.laser_device_key,
                "laser_device_name": item.laser_device_name,
            }
        )
    return rows


def _package_catalog_rows(
    *,
    db: Session,
    workspace: Workspace,
    patient: Patient,
) -> list[dict[str, object]]:
    packages = list_patient_packages(
        db,
        workspace_id=workspace.id,
        patient_id=patient.id,
        usable_only=False,
        include_financials=False,
    )
    return [
        {
            "id": row.id,
            "name": row.name,
            "service_id": row.service_id,
            "laser_device_key": row.laser_device_key,
            "remaining_sessions": row.sessions_remaining,
            "total_sessions": row.sessions_purchased,
            "status": row.effective_status,
        }
        for row in packages[:20]
    ]


def build_patient_semantic_catalog_v2(
    *,
    db: Session,
    workspace: Workspace,
    patient: Patient,
    now: datetime,
) -> dict[str, Any]:
    """Add current-patient read facts to the clinic catalog for semantic grounding only."""
    catalog = build_clinic_catalog(db, workspace)
    enriched = dict(catalog)
    enriched["appointments"] = _appointment_catalog_rows(
        db=db,
        workspace=workspace,
        patient=patient,
        now=now,
    )
    enriched["packages"] = _package_catalog_rows(
        db=db,
        workspace=workspace,
        patient=patient,
    )
    return enriched


def _active_task_dict(active_task: ActiveTaskState | None) -> dict[str, Any] | None:
    if active_task is None:
        return None
    return active_task.model_dump(mode="json")


def _write_preview(step: PlanStep) -> dict[str, object] | None:
    intent = step.write_intent
    if intent is None:
        return None
    return {
        "kind": intent.kind,
        "authorized": intent.authorized,
        "requires_verification": intent.requires_verification,
        "parameters": dict(intent.parameters),
    }


def _execute_shadow_step(
    *,
    step: PlanStep,
    turn: TiaTurnUnderstanding,
    semantic_context: SemanticContext,
    read_context: ReadExecutionContext,
) -> tuple[ShadowStepTrace, TurnOutcome | None]:
    bundle = execute_step_reads(step, read_context) if step.reads else ReadExecutionBundle()
    advanced = advance_step_with_write_policies(step, bundle)

    if advanced.disposition == "write_ready":
        return (
            ShadowStepTrace(
                operation_index=advanced.operation_index,
                operation_type=advanced.operation_type,
                disposition_before=step.disposition,
                disposition_after=advanced.disposition,
                verification=bundle.verification,
                read_kinds=[result.kind for result in bundle.results],
                write_preview=_write_preview(advanced),
                skip_reason="write_execution_required",
            ),
            None,
        )

    if advanced.disposition == "state_update":
        return (
            ShadowStepTrace(
                operation_index=advanced.operation_index,
                operation_type=advanced.operation_type,
                disposition_before=step.disposition,
                disposition_after=advanced.disposition,
                verification=bundle.verification,
                read_kinds=[result.kind for result in bundle.results],
                skip_reason="state_persistence_required",
            ),
            None,
        )

    outcome = build_step_outcome(
        advanced,
        turn=turn,
        semantic_context=semantic_context,
        reads=bundle if bundle.results else None,
    )
    return (
        ShadowStepTrace(
            operation_index=advanced.operation_index,
            operation_type=advanced.operation_type,
            disposition_before=step.disposition,
            disposition_after=advanced.disposition,
            verification=bundle.verification,
            read_kinds=[result.kind for result in bundle.results],
            outcome=outcome,
        ),
        outcome,
    )


def run_v2_shadow_turn(
    *,
    db: Session,
    workspace: Workspace,
    patient: Patient,
    history: list[BaseMessage],
    local_now: datetime,
    active_task: ActiveTaskState | None = None,
    render_reply: bool = True,
) -> ShadowTurnResult:
    """Run V2 beside production without writes, persistence, or customer delivery."""
    clinic_catalog = build_patient_semantic_catalog_v2(
        db=db,
        workspace=workspace,
        patient=patient,
        now=local_now,
    )
    semantic_context = build_semantic_context(clinic_catalog)
    semantic_context = with_safe_task_context(
        semantic_context,
        active_task=_active_task_dict(active_task),
    )
    turn = interpret_customer_turn_v2(
        history=history,
        semantic_context=semantic_context,
        timezone_name=workspace.timezone,
        local_now=local_now,
    )
    plan = plan_turn(
        turn,
        PlannerContext(
            semantic_context=semantic_context,
            active_task=active_task,
            now=local_now,
        ),
    )

    if plan.handoff_category is not None:
        outcome = build_handoff_outcome(plan)
        reply = None
        model = None
        if render_reply:
            reply, model = compose_v2_customer_reply(
                clinic_name=workspace.name,
                timezone_name=workspace.timezone,
                local_now=local_now,
                history=history,
                outcomes=[outcome],
            )
        return ShadowTurnResult(
            understanding=turn,
            plan=plan,
            outcomes=[outcome],
            reply=reply,
            responder_model=model,
        )

    read_context = ReadExecutionContext(
        db=db,
        workspace=workspace,
        patient=patient,
        now=local_now,
        catalog=clinic_catalog,
    )
    traces: list[ShadowStepTrace] = []
    outcomes: list[TurnOutcome] = []
    skip_reasons: list[str] = []
    for step in plan.steps:
        trace, outcome = _execute_shadow_step(
            step=step,
            turn=turn,
            semantic_context=semantic_context,
            read_context=read_context,
        )
        traces.append(trace)
        if trace.skip_reason:
            skip_reasons.append(trace.skip_reason)
        if outcome is not None:
            outcomes.append(outcome)

    reply = None
    model = None
    skipped = ",".join(dict.fromkeys(skip_reasons)) if skip_reasons else None
    if render_reply and outcomes and skipped is None:
        reply, model = compose_v2_customer_reply(
            clinic_name=workspace.name,
            timezone_name=workspace.timezone,
            local_now=local_now,
            history=history,
            outcomes=outcomes,
        )

    return ShadowTurnResult(
        understanding=turn,
        plan=plan,
        step_traces=traces,
        outcomes=outcomes,
        reply=reply,
        responder_model=model,
        reply_skipped_reason=skipped,
    )
