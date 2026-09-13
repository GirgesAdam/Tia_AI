from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

from app.agents.v2.semantic_context import SemanticContext
from app.agents.v2.turn_contract import TiaTurnUnderstanding, TurnOperation
from app.services.agent_v2.outcome import ResponseGoal
from app.services.agent_v2.state import ActiveTaskState, OptionChoice
from app.services.agent_v2.state_rules import option_snapshot_is_current

PlanDisposition = Literal[
    "read",
    "clarify",
    "state_update",
    "write_ready",
    "handoff",
    "respond",
    "blocked",
]
ReadKind = Literal[
    "service_catalog",
    "clinic_info",
    "doctors",
    "availability",
    "appointments",
    "customer_profile",
    "customer_history",
    "customer_packages",
    "package_offers",
    "package_refund_quote",
]
WriteKind = Literal[
    "booking",
    "confirm_appointment",
    "cancel_appointment",
    "reschedule",
    "buy_package",
    "follow_up",
    "marketing_update",
]
StateAction = Literal[
    "none",
    "start_booking",
    "start_reschedule",
    "update_active",
    "select_active",
    "cancel_active",
]
ClarificationField = Literal[
    "service",
    "doctor",
    "device",
    "date",
    "time",
    "appointment",
    "package",
    "selection",
    "follow_up_time",
    "marketing_consent",
    "intent",
]


class StrictPlannerModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


class ReadRequest(StrictPlannerModel):
    kind: ReadKind
    parameters: dict[str, object] = Field(default_factory=dict)


class WriteIntent(StrictPlannerModel):
    kind: WriteKind
    authorized: bool
    parameters: dict[str, object] = Field(default_factory=dict)
    requires_verification: bool = True


class PlanStep(StrictPlannerModel):
    operation_index: int
    operation_type: str
    disposition: PlanDisposition
    reads: list[ReadRequest] = Field(default_factory=list)
    write_intent: WriteIntent | None = None
    state_action: StateAction = "none"
    response_goal: ResponseGoal | None = None
    clarification_field: ClarificationField | None = None
    facts: dict[str, object] = Field(default_factory=dict)


class TurnPlan(StrictPlannerModel):
    steps: list[PlanStep] = Field(default_factory=list)
    handoff_category: str | None = None
    handoff_priority: str | None = None


class VerificationFacts(StrictPlannerModel):
    appointment_match_count: int | None = None
    exact_slot_match_count: int | None = None
    package_offer_match_count: int | None = None
    requires_human: bool = False
    verified_parameters: dict[str, object] = Field(default_factory=dict)


@dataclass(frozen=True)
class PlannerContext:
    semantic_context: SemanticContext
    active_task: ActiveTaskState | None
    now: datetime


def _canonical_entity(
    operation: TurnOperation,
    field: str,
    *,
    kind: str,
    semantic_context: SemanticContext,
) -> tuple[str | None, bool, list[str]]:
    entity = getattr(operation.entities, field)
    if entity is None:
        return None, False, []
    if entity.ref:
        resolved = semantic_context.resolve(entity.ref, expected_kind=kind)
        if resolved is not None:
            return resolved, False, []
    grounded = [
        item
        for ref in entity.candidate_refs
        if (item := semantic_context.resolve(ref, expected_kind=kind)) is not None
    ]
    if entity.candidate_mode == "set" and grounded:
        return None, False, list(dict.fromkeys(grounded))
    return None, bool(grounded), []


def _base_parameters(
    operation: TurnOperation,
    context: PlannerContext,
) -> tuple[dict[str, object], dict[str, bool]]:
    values: dict[str, object] = {}
    ambiguous: dict[str, bool] = {}
    for field, kind, output_key, set_key in (
        ("service", "service", "service_id", "service_ids"),
        ("doctor", "doctor", "doctor_id", "doctor_ids"),
        ("device", "device", "device_key", "device_keys"),
        ("appointment", "appointment", "appointment_id", "appointment_ids"),
        ("package", "package", "package_id", "package_ids"),
    ):
        value, is_ambiguous, requested_set = _canonical_entity(
            operation,
            field,
            kind=kind,
            semantic_context=context.semantic_context,
        )
        if value is not None:
            values[output_key] = value
        if requested_set:
            values[set_key] = requested_set
        ambiguous[field] = is_ambiguous

    if operation.entities.date is not None:
        values["date"] = operation.entities.date.model_dump(mode="json")
    if operation.entities.time is not None:
        values["time"] = operation.entities.time.model_dump(mode="json")
    if operation.entities.package_sessions is not None:
        values["package_sessions"] = operation.entities.package_sessions
    if operation.entities.marketing_consent is not None:
        values["marketing_consent"] = operation.entities.marketing_consent
    if operation.entities.follow_up_at_local is not None:
        values["follow_up_at_local"] = operation.entities.follow_up_at_local
    values["package_usage"] = operation.package_usage
    return values, ambiguous


def _service_requires_laser_device(
    operation: TurnOperation,
    context: PlannerContext,
) -> bool:
    service = operation.entities.service
    if service is None or service.ref is None:
        return False
    rows = context.semantic_context.model_input.get("services")
    if not isinstance(rows, list):
        return False
    for row in rows:
        if not isinstance(row, dict) or row.get("ref") != service.ref:
            continue
        return row.get("requires_laser_device") is True
    return False


def _slot_ambiguity_field(step: PlanStep) -> ClarificationField:
    params = step.write_intent.parameters if step.write_intent is not None else {}
    if "doctor_id" not in params:
        return "doctor"
    if bool(step.facts.get("service_requires_laser_device")) and "device_key" not in params:
        return "device"
    return "selection"


def _clarify(
    *,
    index: int,
    operation: TurnOperation,
    field: ClarificationField,
    goal: ResponseGoal = "clarification",
    facts: dict[str, object] | None = None,
) -> PlanStep:
    return PlanStep(
        operation_index=index,
        operation_type=operation.type,
        disposition="clarify",
        response_goal=goal,
        clarification_field=field,
        facts=dict(facts or {}),
    )


def _safety_handoff(turn: TiaTurnUnderstanding) -> TurnPlan | None:
    signals = set(turn.safety_signals)
    if "urgent_medical" in signals:
        return TurnPlan(steps=[], handoff_category="medical", handoff_priority="urgent")
    if "medical" in signals:
        return TurnPlan(steps=[], handoff_category="medical", handoff_priority="high")
    if "payment_dispute" in signals:
        return TurnPlan(steps=[], handoff_category="payment", handoff_priority="normal")
    if "complaint" in signals:
        return TurnPlan(steps=[], handoff_category="complaint", handoff_priority="high")
    if "privacy_issue" in signals:
        return TurnPlan(steps=[], handoff_category="customer_request", handoff_priority="high")
    return None


def _selected_snapshot_option(
    operation: TurnOperation,
    context: PlannerContext,
) -> OptionChoice | None:
    state = context.active_task
    if state is None or not option_snapshot_is_current(state, now=context.now):
        return None
    snapshot = state.option_snapshot
    if snapshot is None or operation.selection is None:
        return None

    selection = operation.selection
    if selection.kind == "index" and selection.index is not None:
        index = selection.index - 1
        if 0 <= index < len(snapshot.options):
            return snapshot.options[index]
        return None
    if selection.kind == "ref" and selection.ref is not None:
        matches = [item for item in snapshot.options if item.ref == selection.ref]
        return matches[0] if len(matches) == 1 else None
    if selection.kind == "time" and selection.time is not None:
        matches = [
            item
            for item in snapshot.options
            if str(item.payload.get("start_time_24h") or "")[:5] == selection.time[:5]
        ]
        return matches[0] if len(matches) == 1 else None
    return None


def _plan_select_active(index: int, operation: TurnOperation, context: PlannerContext) -> PlanStep:
    state = context.active_task
    selected = _selected_snapshot_option(operation, context)
    if state is None or state.option_snapshot is None or selected is None:
        return _clarify(index=index, operation=operation, field="selection")

    purpose = state.option_snapshot.purpose
    if purpose == "booking_slot":
        authorized = (
            operation.execution_intent == "execute"
            and state.task_type == "booking"
            and state.write_authorization.authorized
            and state.write_authorization.operation == "booking"
        )
        if not authorized:
            return PlanStep(
                operation_index=index,
                operation_type=operation.type,
                disposition="respond",
                state_action="select_active",
                response_goal="present_availability",
                facts={"selected_option": selected.model_dump(mode="json")},
            )
        return PlanStep(
            operation_index=index,
            operation_type=operation.type,
            disposition="write_ready",
            state_action="select_active",
            write_intent=WriteIntent(
                kind="booking",
                authorized=True,
                parameters=dict(selected.payload),
                requires_verification=True,
            ),
            response_goal="booking_completed",
            facts={"selected_option_ref": selected.ref},
        )

    if purpose == "reschedule_slot":
        authorized = (
            operation.execution_intent == "execute"
            and state.task_type == "reschedule"
            and state.write_authorization.authorized
            and state.write_authorization.operation == "reschedule"
        )
        if not authorized:
            return _clarify(index=index, operation=operation, field="selection")
        return PlanStep(
            operation_index=index,
            operation_type=operation.type,
            disposition="write_ready",
            state_action="select_active",
            write_intent=WriteIntent(
                kind="reschedule",
                authorized=True,
                parameters=dict(selected.payload),
                requires_verification=True,
            ),
            response_goal="reschedule_completed",
            facts={"selected_option_ref": selected.ref},
        )

    return PlanStep(
        operation_index=index,
        operation_type=operation.type,
        disposition="state_update",
        state_action="select_active",
        facts={
            "choice_purpose": purpose,
            "selected_option": selected.model_dump(mode="json"),
        },
    )


def _informational_write_read(
    index: int,
    operation: TurnOperation,
    params: dict[str, object],
) -> PlanStep | None:
    """Fail closed to reads when the semantic action is mentioned without execution authority."""
    if operation.execution_intent == "execute":
        return None
    if operation.type == "book":
        if "service_id" not in params:
            return _clarify(index=index, operation=operation, field="service")
        if "date" in params:
            return PlanStep(
                operation_index=index,
                operation_type=operation.type,
                disposition="read",
                reads=[ReadRequest(kind="availability", parameters=params)],
                response_goal="present_availability",
                facts=params,
            )
        return PlanStep(
            operation_index=index,
            operation_type=operation.type,
            disposition="read",
            reads=[ReadRequest(kind="service_catalog", parameters={"service_id": params["service_id"]})],
            response_goal="answer_service",
            facts=params,
        )
    if operation.type in {"confirm_appointment", "cancel_appointment"}:
        return PlanStep(
            operation_index=index,
            operation_type=operation.type,
            disposition="read",
            reads=[ReadRequest(kind="appointments", parameters=params)],
            response_goal="answer_customer_history",
            facts=params,
        )
    if operation.type == "reschedule":
        reads = [ReadRequest(kind="appointments", parameters=params)]
        if "date" in params and "service_id" in params:
            reads.append(ReadRequest(kind="availability", parameters={**params, "reschedule": True}))
        return PlanStep(
            operation_index=index,
            operation_type=operation.type,
            disposition="read",
            reads=reads,
            response_goal="present_availability" if len(reads) > 1 else "answer_customer_history",
            facts=params,
        )
    if operation.type == "buy_package":
        return PlanStep(
            operation_index=index,
            operation_type=operation.type,
            disposition="read",
            reads=[ReadRequest(kind="package_offers", parameters=params)],
            response_goal="package_information",
            facts=params,
        )
    if operation.type in {"follow_up", "marketing_update"}:
        return _clarify(index=index, operation=operation, field="intent")
    return None


def _plan_operation(
    index: int,
    operation: TurnOperation,
    context: PlannerContext,
    *,
    compound_book: bool = False,
) -> PlanStep:
    params, ambiguous = _base_parameters(operation, context)

    if operation.type == "human_support":
        return PlanStep(
            operation_index=index,
            operation_type=operation.type,
            disposition="handoff",
            response_goal="handoff",
            facts={"category": "customer_request", "priority": "normal"},
        )
    if operation.type == "social":
        return PlanStep(
            operation_index=index,
            operation_type=operation.type,
            disposition="respond",
            response_goal="social_ack",
        )
    if operation.type == "unclear":
        return _clarify(index=index, operation=operation, field="intent")
    if operation.type == "cancel_active":
        return PlanStep(
            operation_index=index,
            operation_type=operation.type,
            disposition="state_update",
            state_action="cancel_active",
            response_goal="clarification",
        )
    if operation.type == "select_active":
        return _plan_select_active(index, operation, context)
    if operation.type == "continue_active":
        if context.active_task is None:
            return _clarify(index=index, operation=operation, field="intent")
        return PlanStep(
            operation_index=index,
            operation_type=operation.type,
            disposition="state_update",
            state_action="update_active",
            facts=params,
        )

    informational = _informational_write_read(index, operation, params)
    if informational is not None:
        return informational

    if ambiguous.get("service"):
        return _clarify(index=index, operation=operation, field="service", goal="ask_service_choice")
    if ambiguous.get("doctor") and not (compound_book and operation.type == "book"):
        return _clarify(index=index, operation=operation, field="doctor", goal="ask_doctor_choice")
    if ambiguous.get("device") and operation.type in {
        "doctor_info",
        "availability",
        "book",
        "package_info",
        "buy_package",
        "refund_quote",
        "reschedule",
    }:
        return _clarify(index=index, operation=operation, field="device")
    if ambiguous.get("appointment"):
        return _clarify(
            index=index,
            operation=operation,
            field="appointment",
            goal="ask_appointment_choice",
        )
    if ambiguous.get("package"):
        return _clarify(index=index, operation=operation, field="package", goal="ask_package_choice")

    if operation.type in {"service_info", "pricing"}:
        if "service_id" not in params:
            return _clarify(index=index, operation=operation, field="service")
        return PlanStep(
            operation_index=index,
            operation_type=operation.type,
            disposition="read",
            reads=[ReadRequest(kind="service_catalog", parameters={"service_id": params["service_id"]})],
            response_goal="answer_price" if operation.type == "pricing" else "answer_service",
            facts=params,
        )

    if operation.type == "doctor_info":
        return PlanStep(
            operation_index=index,
            operation_type=operation.type,
            disposition="read",
            reads=[ReadRequest(kind="doctors", parameters=params)],
            response_goal="answer_doctor",
            facts=params,
        )

    if operation.type == "clinic_info":
        return PlanStep(
            operation_index=index,
            operation_type=operation.type,
            disposition="read",
            reads=[ReadRequest(kind="clinic_info")],
            response_goal="answer_clinic_info",
        )

    if operation.type == "availability":
        if "service_id" not in params:
            return _clarify(index=index, operation=operation, field="service")
        return PlanStep(
            operation_index=index,
            operation_type=operation.type,
            disposition="read",
            reads=[ReadRequest(kind="availability", parameters=params)],
            response_goal="present_availability",
            facts=params,
        )

    if operation.type == "book":
        # A same-turn multi-service visit must select one common doctor deterministically.
        # Single-service bookings keep the existing explicit doctor-choice behavior.
        if "doctor_ids" in params and not compound_book:
            return _clarify(index=index, operation=operation, field="doctor", goal="ask_doctor_choice")
        if "service_id" not in params:
            return _clarify(index=index, operation=operation, field="service")
        if "date" not in params:
            return _clarify(index=index, operation=operation, field="date")
        exact_time = operation.entities.time is not None and operation.entities.time.mode == "exact"
        requires_device = _service_requires_laser_device(operation, context)
        return PlanStep(
            operation_index=index,
            operation_type=operation.type,
            disposition="read",
            reads=[ReadRequest(kind="availability", parameters=params)],
            write_intent=WriteIntent(
                kind="booking",
                authorized=True,
                parameters=params,
                requires_verification=True,
            ),
            state_action="start_booking",
            response_goal="present_availability",
            facts={
                **params,
                "exact_time_requested": exact_time,
                "service_requires_laser_device": requires_device,
            },
        )

    if operation.type == "appointment_list":
        return PlanStep(
            operation_index=index,
            operation_type=operation.type,
            disposition="read",
            reads=[ReadRequest(kind="appointments")],
            response_goal="answer_customer_history",
        )

    if operation.type in {"confirm_appointment", "cancel_appointment"}:
        if "appointment_ids" in params:
            return _clarify(index=index, operation=operation, field="appointment", goal="ask_appointment_choice")
        kind: WriteKind = (
            "confirm_appointment" if operation.type == "confirm_appointment" else "cancel_appointment"
        )
        goal: ResponseGoal = (
            "appointment_confirmed" if operation.type == "confirm_appointment" else "cancellation_completed"
        )
        return PlanStep(
            operation_index=index,
            operation_type=operation.type,
            disposition="read",
            reads=[ReadRequest(kind="appointments", parameters=params)],
            write_intent=WriteIntent(kind=kind, authorized=True, parameters=params),
            response_goal=goal,
            facts=params,
        )

    if operation.type == "reschedule":
        if "doctor_ids" in params or "appointment_ids" in params:
            field: ClarificationField = "appointment" if "appointment_ids" in params else "doctor"
            return _clarify(index=index, operation=operation, field=field)
        if "date" not in params:
            return _clarify(index=index, operation=operation, field="date")
        exact_time = operation.entities.time is not None and operation.entities.time.mode == "exact"
        requires_device = _service_requires_laser_device(operation, context)
        return PlanStep(
            operation_index=index,
            operation_type=operation.type,
            disposition="read",
            reads=[
                ReadRequest(kind="appointments", parameters=params),
                ReadRequest(kind="availability", parameters={**params, "reschedule": True}),
            ],
            write_intent=WriteIntent(kind="reschedule", authorized=True, parameters=params),
            state_action="start_reschedule",
            response_goal="present_availability",
            facts={
                **params,
                "exact_time_requested": exact_time,
                "service_requires_laser_device": requires_device,
            },
        )

    if operation.type == "customer_profile":
        return PlanStep(
            operation_index=index,
            operation_type=operation.type,
            disposition="read",
            reads=[ReadRequest(kind="customer_profile")],
            response_goal="answer_customer_profile",
        )

    if operation.type == "customer_history":
        return PlanStep(
            operation_index=index,
            operation_type=operation.type,
            disposition="read",
            reads=[ReadRequest(kind="customer_history")],
            response_goal="answer_customer_history",
        )

    if operation.type == "package_info":
        return PlanStep(
            operation_index=index,
            operation_type=operation.type,
            disposition="read",
            reads=[ReadRequest(kind="customer_packages", parameters=params)],
            response_goal="package_information",
            facts=params,
        )

    if operation.type == "buy_package":
        return PlanStep(
            operation_index=index,
            operation_type=operation.type,
            disposition="read",
            reads=[ReadRequest(kind="package_offers", parameters=params)],
            write_intent=WriteIntent(kind="buy_package", authorized=True, parameters=params),
            response_goal="package_purchased",
            facts=params,
        )

    if operation.type == "refund_quote":
        return PlanStep(
            operation_index=index,
            operation_type=operation.type,
            disposition="read",
            reads=[ReadRequest(kind="package_refund_quote", parameters=params)],
            response_goal="package_refund_quote",
            facts=params,
        )

    if operation.type == "follow_up":
        if "follow_up_at_local" not in params:
            return _clarify(index=index, operation=operation, field="follow_up_time")
        return PlanStep(
            operation_index=index,
            operation_type=operation.type,
            disposition="write_ready",
            write_intent=WriteIntent(
                kind="follow_up",
                authorized=True,
                parameters=params,
                requires_verification=False,
            ),
            response_goal="follow_up_created",
            facts=params,
        )

    if operation.type == "marketing_update":
        if "marketing_consent" not in params:
            return _clarify(index=index, operation=operation, field="marketing_consent")
        return PlanStep(
            operation_index=index,
            operation_type=operation.type,
            disposition="write_ready",
            write_intent=WriteIntent(
                kind="marketing_update",
                authorized=True,
                parameters=params,
                requires_verification=False,
            ),
            response_goal="marketing_updated",
            facts=params,
        )

    return _clarify(index=index, operation=operation, field="intent")


def plan_turn(turn: TiaTurnUnderstanding, context: PlannerContext) -> TurnPlan:
    safety = _safety_handoff(turn)
    if safety is not None:
        return safety

    steps: list[PlanStep] = []
    executable_book_indexes = {
        index
        for index, operation in enumerate(turn.operations)
        if operation.type == "book" and operation.execution_intent == "execute"
    }
    compound_booking = len(executable_book_indexes) >= 2
    for index, operation in enumerate(turn.operations):
        step = _plan_operation(
            index,
            operation,
            context,
            compound_book=compound_booking and index in executable_book_indexes,
        )
        if step.disposition == "handoff":
            return TurnPlan(
                steps=[step],
                handoff_category=str(step.facts.get("category") or "customer_request"),
                handoff_priority=str(step.facts.get("priority") or "normal"),
            )
        steps.append(step)
    return TurnPlan(steps=steps)


def advance_step_after_verification(
    step: PlanStep,
    verification: VerificationFacts,
) -> PlanStep:
    """Promote an authorized semantic write only after deterministic verification."""
    if step.write_intent is None or not step.write_intent.authorized:
        return step
    if verification.requires_human:
        return step.model_copy(
            update={
                "disposition": "handoff",
                "response_goal": "handoff",
                "facts": {**step.facts, **verification.verified_parameters},
            }
        )

    kind = step.write_intent.kind
    verified_parameters = {
        **step.write_intent.parameters,
        **verification.verified_parameters,
    }

    if kind == "booking":
        if not bool(step.facts.get("exact_time_requested")):
            return step
        count = verification.exact_slot_match_count
        if count == 1:
            if (
                bool(step.facts.get("service_requires_laser_device"))
                and not verified_parameters.get("device_key")
            ):
                return step.model_copy(
                    update={
                        "disposition": "clarify",
                        "clarification_field": "device",
                        "response_goal": "clarification",
                    }
                )
            return step.model_copy(
                update={
                    "disposition": "write_ready",
                    "write_intent": step.write_intent.model_copy(
                        update={"parameters": verified_parameters}
                    ),
                }
            )
        if count == 0:
            return step.model_copy(
                update={"disposition": "blocked", "response_goal": "requested_time_unavailable"}
            )
        if count is not None and count > 1:
            field = _slot_ambiguity_field(step)
            return step.model_copy(
                update={
                    "disposition": "clarify",
                    "clarification_field": field,
                    "response_goal": "ask_doctor_choice" if field == "doctor" else "clarification",
                }
            )
        return step

    if kind in {"confirm_appointment", "cancel_appointment"}:
        count = verification.appointment_match_count
        if count == 1:
            return step.model_copy(
                update={
                    "disposition": "write_ready",
                    "write_intent": step.write_intent.model_copy(
                        update={"parameters": verified_parameters}
                    ),
                }
            )
        if count == 0:
            return step.model_copy(
                update={"disposition": "blocked", "response_goal": "clarification"}
            )
        if count is not None and count > 1:
            return step.model_copy(
                update={
                    "disposition": "clarify",
                    "clarification_field": "appointment",
                    "response_goal": "ask_appointment_choice",
                }
            )
        return step

    if kind == "reschedule":
        appointment_count = verification.appointment_match_count
        if appointment_count is not None and appointment_count != 1:
            if appointment_count > 1:
                return step.model_copy(
                    update={
                        "disposition": "clarify",
                        "clarification_field": "appointment",
                        "response_goal": "ask_appointment_choice",
                    }
                )
            return step.model_copy(
                update={"disposition": "blocked", "response_goal": "clarification"}
            )
        if not bool(step.facts.get("exact_time_requested")):
            return step
        slot_count = verification.exact_slot_match_count
        if slot_count == 1 and appointment_count == 1:
            if (
                bool(step.facts.get("service_requires_laser_device"))
                and not verified_parameters.get("device_key")
            ):
                return step.model_copy(
                    update={
                        "disposition": "clarify",
                        "clarification_field": "device",
                        "response_goal": "clarification",
                    }
                )
            return step.model_copy(
                update={
                    "disposition": "write_ready",
                    "write_intent": step.write_intent.model_copy(
                        update={"parameters": verified_parameters}
                    ),
                }
            )
        if slot_count == 0:
            return step.model_copy(
                update={"disposition": "blocked", "response_goal": "requested_time_unavailable"}
            )
        if slot_count is not None and slot_count > 1:
            field = _slot_ambiguity_field(step)
            return step.model_copy(
                update={
                    "disposition": "clarify",
                    "clarification_field": field,
                    "response_goal": "ask_doctor_choice" if field == "doctor" else "clarification",
                }
            )
        return step

    if kind == "buy_package":
        count = verification.package_offer_match_count
        if count == 1:
            return step.model_copy(
                update={
                    "disposition": "write_ready",
                    "write_intent": step.write_intent.model_copy(
                        update={"parameters": verified_parameters}
                    ),
                }
            )
        if count == 0:
            return step.model_copy(
                update={"disposition": "blocked", "response_goal": "package_information"}
            )
        if count is not None and count > 1:
            return step.model_copy(
                update={
                    "disposition": "clarify",
                    "clarification_field": "package",
                    "response_goal": "ask_package_choice",
                }
            )
        return step

    return step.model_copy(
        update={
            "disposition": "write_ready",
            "write_intent": step.write_intent.model_copy(update={"parameters": verified_parameters}),
        }
    )
