from __future__ import annotations

from app.agents.v2.semantic_context import SemanticContext
from app.agents.v2.turn_contract import TurnOperation
from app.services.agent_v2.planner import PlanStep, ReadRequest, WriteIntent
from app.services.agent_v2.state import ActiveTaskState, BookingTaskState, RescheduleTaskState


def _canonical_ref(
    operation: TurnOperation,
    *,
    field: str,
    kind: str,
    context: SemanticContext,
) -> str | None:
    entity = getattr(operation.entities, field)
    if entity is None or entity.ref is None:
        return None
    return context.resolve(entity.ref, expected_kind=kind)


def resolved_operation_parameters(
    operation: TurnOperation,
    *,
    context: SemanticContext,
) -> dict[str, object]:
    """Resolve only structured ephemeral refs; never inspect customer text."""
    params: dict[str, object] = {}
    for field, kind, key in (
        ("service", "service", "service_id"),
        ("doctor", "doctor", "doctor_id"),
        ("device", "device", "device_key"),
        ("appointment", "appointment", "appointment_id"),
        ("package", "package", "package_id"),
    ):
        value = _canonical_ref(operation, field=field, kind=kind, context=context)
        if value is not None:
            params[key] = value
    if operation.entities.date is not None:
        params["date"] = operation.entities.date.model_dump(mode="json")
    if operation.entities.time is not None:
        params["time"] = operation.entities.time.model_dump(mode="json")
    if operation.entities.package_sessions is not None:
        params["package_sessions"] = operation.entities.package_sessions
    if operation.package_usage != "unspecified":
        params["package_usage"] = operation.package_usage
    return params


def adapt_matching_active_task_step(
    step: PlanStep,
    *,
    operation: TurnOperation,
    active_task: ActiveTaskState | None,
    context: SemanticContext,
) -> PlanStep:
    """Treat a repeated structured reschedule intent as an update to its verified active target.

    The semantic model may emit ``reschedule`` again on a natural follow-up instead of
    ``continue_active``. Once Python has already verified and persisted one reschedule target, a
    follow-up that does not identify a different appointment must mutate only the replacement
    constraints. This prevents a replacement date from being reused to search for the original
    appointment. An explicit different appointment remains a fresh workflow request.
    """
    if not isinstance(active_task, RescheduleTaskState) or operation.type != "reschedule":
        return step
    if step.clarification_field == "appointment":
        return step

    appointment = operation.entities.appointment
    if appointment is not None and appointment.candidate_refs:
        return step

    params = resolved_operation_parameters(operation, context=context)
    explicit_target = params.pop("appointment_id", None)
    if explicit_target is not None and str(explicit_target) != active_task.target.appointment_id:
        return step

    return PlanStep(
        operation_index=step.operation_index,
        operation_type=operation.type,
        disposition="state_update",
        state_action="update_active",
        response_goal="clarification",
        facts=params,
    )


def persist_initial_task_intent(
    step: PlanStep,
    *,
    operation: TurnOperation,
    context: SemanticContext,
) -> PlanStep:
    """Keep an explicit booking intent alive even when the first turn needs clarification."""
    if step.disposition != "clarify" or step.state_action != "none":
        return step
    if operation.type != "book":
        return step
    params = resolved_operation_parameters(operation, context=context)
    return step.model_copy(
        update={
            "state_action": "start_booking",
            "facts": {**params, **step.facts},
        }
    )


def _constraint_parameters(state: BookingTaskState | RescheduleTaskState) -> dict[str, object]:
    constraints = state.constraints if state.task_type == "booking" else state.replacement
    dumped = constraints.model_dump(mode="json")
    return {
        key: value
        for key, value in dumped.items()
        if value not in (None, "", {}, [])
    }


def _service_requires_device(service_id: str | None, context: SemanticContext) -> bool:
    if service_id is None:
        return False
    service_ref = next(
        (
            ref
            for ref, target in context.reference_map.items()
            if target.kind == "service" and target.canonical_id == service_id
        ),
        None,
    )
    if service_ref is None:
        return False
    rows = context.model_input.get("services")
    if not isinstance(rows, list):
        return False
    return any(
        isinstance(row, dict)
        and row.get("ref") == service_ref
        and row.get("requires_laser_device") is True
        for row in rows
    )


def _booking_progress(
    state: BookingTaskState,
    *,
    operation_index: int,
    context: SemanticContext,
) -> PlanStep:
    params = _constraint_parameters(state)
    service_id = state.constraints.service_id
    if service_id is None:
        return PlanStep(
            operation_index=operation_index,
            operation_type="continue_active",
            disposition="clarify",
            state_action="update_active",
            response_goal="clarification",
            clarification_field="service",
            facts=params,
        )
    if state.constraints.date is None:
        return PlanStep(
            operation_index=operation_index,
            operation_type="continue_active",
            disposition="clarify",
            state_action="update_active",
            response_goal="clarification",
            clarification_field="date",
            facts=params,
        )

    exact_time = state.constraints.time is not None and state.constraints.time.mode == "exact"
    requires_device = _service_requires_device(service_id, context)
    return PlanStep(
        operation_index=operation_index,
        operation_type="book",
        disposition="read",
        reads=[ReadRequest(kind="availability", parameters=params)],
        write_intent=WriteIntent(
            kind="booking",
            authorized=state.write_authorization.authorized,
            parameters=params,
            requires_verification=True,
        ),
        state_action="update_active",
        response_goal="present_availability",
        facts={
            **params,
            "exact_time_requested": exact_time,
            "service_requires_laser_device": requires_device,
        },
    )


def _reschedule_progress(
    state: RescheduleTaskState,
    *,
    operation_index: int,
    context: SemanticContext,
) -> PlanStep:
    params = _constraint_parameters(state)
    params["appointment_id"] = state.target.appointment_id
    if state.replacement.service_id is None:
        return PlanStep(
            operation_index=operation_index,
            operation_type="continue_active",
            disposition="clarify",
            state_action="update_active",
            response_goal="clarification",
            clarification_field="service",
            facts=params,
        )
    if state.replacement.date is None:
        return PlanStep(
            operation_index=operation_index,
            operation_type="continue_active",
            disposition="clarify",
            state_action="update_active",
            response_goal="clarification",
            clarification_field="date",
            facts=params,
        )

    exact_time = state.replacement.time is not None and state.replacement.time.mode == "exact"
    requires_device = _service_requires_device(state.replacement.service_id, context)
    read_params = {**params, "reschedule": True}
    return PlanStep(
        operation_index=operation_index,
        operation_type="reschedule",
        disposition="read",
        reads=[
            ReadRequest(kind="appointments", parameters={"appointment_id": state.target.appointment_id}),
            ReadRequest(kind="availability", parameters=read_params),
        ],
        write_intent=WriteIntent(
            kind="reschedule",
            authorized=state.write_authorization.authorized,
            parameters=params,
            requires_verification=True,
        ),
        state_action="update_active",
        response_goal="present_availability",
        facts={
            **params,
            "exact_time_requested": exact_time,
            "service_requires_laser_device": requires_device,
        },
    )


def plan_active_task_progress(
    state: ActiveTaskState,
    *,
    operation_index: int,
    context: SemanticContext,
) -> PlanStep:
    """Plan the next deterministic workflow step from persisted state only."""
    if state.task_type == "booking":
        return _booking_progress(state, operation_index=operation_index, context=context)
    return _reschedule_progress(state, operation_index=operation_index, context=context)
