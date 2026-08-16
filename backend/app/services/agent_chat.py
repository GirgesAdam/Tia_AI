from __future__ import annotations

import json
from datetime import datetime, timezone
from uuid import UUID, uuid4

from langchain_core.messages import AIMessage, BaseMessage, HumanMessage
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.agents.capability_policy import (
    CapabilityPolicyDecision,
    ToolAuthorizationError,
    authorize_tool_execution,
    resolve_capability_policy,
)
from app.agents.flow_interpreter import FlowTurnDecision, interpret_active_flow_turn
from app.agents.response_guard import sanitize_customer_reply
from app.agents.semantic_actions import (
    booking_tool_args,
    format_booking_success,
    format_handoff_reply,
    reschedule_tool_args,
    select_slot_from_structured_selection,
)
from app.agents.semantic_router import (
    SemanticCapabilityDecision,
    SemanticEntityHints,
    route_customer_message,
)
from app.agents.tia_customer_agent import run_tia_customer_agent
from app.agents.tools.clinic_tools import AgentToolContext, build_clinic_tools
from app.core.config import settings
from app.models.agent_action import AgentAction
from app.models.conversation import Conversation
from app.models.conversation_flow_state import ConversationFlowState
from app.models.message import Message
from app.models.patient import Patient
from app.models.workspace import Workspace
from app.schemas.agent import AgentChatRequest, AgentChatResponse
from app.services.conversation_flows import (
    FlowStateConflictError,
    cancel_flow,
    complete_flow,
    get_active_flow,
    interrupt_flow,
    record_write_authorized,
    record_write_completed,
    start_flow,
    sync_flow_from_agent_run,
    transition_flow,
)
from app.services.handoffs import get_active_handoff


class AgentChatError(ValueError):
    pass


def _get_patient(db: Session, workspace_id: UUID, patient_id: UUID) -> Patient:
    patient = db.scalar(
        select(Patient).where(
            Patient.workspace_id == workspace_id,
            Patient.id == patient_id,
        )
    )
    if patient is None:
        raise AgentChatError("Patient not found in this workspace.")
    if patient.status == "blocked":
        raise AgentChatError("Blocked patients cannot use the automated customer agent.")
    return patient


def _get_or_create_conversation(
    db: Session,
    *,
    workspace: Workspace,
    patient: Patient,
    payload: AgentChatRequest,
    now: datetime,
) -> Conversation:
    if payload.conversation_id is not None:
        conversation = db.scalar(
            select(Conversation).where(
                Conversation.workspace_id == workspace.id,
                Conversation.id == payload.conversation_id,
                Conversation.patient_id == patient.id,
            )
        )
        if conversation is None:
            raise AgentChatError("Conversation not found for this patient.")
        if conversation.status == "closed":
            conversation.status = "open"
            conversation.closed_at = None
        return conversation

    conversation = Conversation(
        workspace_id=workspace.id,
        patient_id=patient.id,
        channel=payload.channel,
        status="open",
        started_at=now,
        last_message_at=now,
    )
    db.add(conversation)
    db.flush()
    return conversation


def _history_from_db(
    db: Session,
    conversation: Conversation,
    limit: int | None = None,
) -> list[BaseMessage]:
    limit = limit or settings.agent_history_messages
    rows = list(
        db.scalars(
            select(Message)
            .where(
                Message.workspace_id == conversation.workspace_id,
                Message.conversation_id == conversation.id,
                Message.content.is_not(None),
                Message.sender_type.in_(("patient", "ai", "staff")),
            )
            .order_by(Message.created_at.desc())
            .limit(limit)
        )
    )
    rows.reverse()

    history: list[BaseMessage] = []
    for row in rows:
        if not row.content:
            continue
        if row.sender_type == "patient":
            history.append(HumanMessage(content=row.content))
        else:
            history.append(AIMessage(content=row.content))
    return history


def _compact_context_value(
    value: object,
    *,
    list_limit: int = 5,
    depth: int = 0,
) -> object:
    if depth >= 5:
        if isinstance(value, (dict, list)):
            return "[truncated]"
        return value

    if isinstance(value, dict):
        result: dict[str, object] = {}
        for key, item in value.items():
            if (
                key in {"slots", "appointments", "branches", "services", "doctors"}
                and isinstance(item, list)
            ):
                result[key] = [
                    _compact_context_value(child, list_limit=list_limit, depth=depth + 1)
                    for child in item[:list_limit]
                ]
            else:
                result[key] = _compact_context_value(
                    item,
                    list_limit=list_limit,
                    depth=depth + 1,
                )
        return result

    if isinstance(value, list):
        return [
            _compact_context_value(child, list_limit=list_limit, depth=depth + 1)
            for child in value[:list_limit]
        ]

    if isinstance(value, str) and len(value) > 1200:
        return value[:1200] + "…"
    return value


def _recent_operational_context(
    db: Session,
    conversation: Conversation,
    flow: ConversationFlowState | None,
) -> str | None:
    context: dict[str, object] = {}
    if flow is not None:
        context["workflow"] = {
            "flow_type": flow.flow_type,
            "status": flow.status,
            "capabilities": flow.capabilities,
            "entity_state": _compact_context_value(flow.entity_state),
            "missing_information": flow.missing_information,
            "option_snapshot": _compact_context_value(flow.option_snapshot),
            "version": flow.version,
        }

    rows = list(
        db.scalars(
            select(AgentAction)
            .where(
                AgentAction.workspace_id == conversation.workspace_id,
                AgentAction.conversation_id == conversation.id,
                AgentAction.status == "success",
                AgentAction.tool_name.in_(
                    (
                        "get_booking_options",
                        "get_reschedule_options",
                        "get_customer_appointments",
                    )
                ),
            )
            .order_by(AgentAction.created_at.desc())
            .limit(max(settings.agent_operational_context_items * 2, 4))
        )
    )

    latest: dict[str, object] = {}
    for row in rows:
        if row.tool_name in latest:
            continue
        latest[row.tool_name] = {
            "input": _compact_context_value(row.input_json),
            "output": _compact_context_value(row.output_json),
        }
        if len(latest) >= settings.agent_operational_context_items:
            break
    if latest:
        context["recent_tools"] = latest

    if not context:
        return None

    encoded = json.dumps(
        context,
        ensure_ascii=False,
        default=str,
        separators=(",", ":"),
    )
    return encoded[: settings.agent_operational_context_max_chars]


def _invoke_authorized_tool(
    *,
    tool_context: AgentToolContext,
    policy: CapabilityPolicyDecision,
    tool_name: str,
    arguments: dict,
) -> dict | None:
    authorize_tool_execution(policy, tool_name)
    tool = next(
        item
        for item in build_clinic_tools(tool_context)
        if item.name == tool_name
    )
    raw = tool.invoke(arguments)
    try:
        value = json.loads(raw)
    except (TypeError, json.JSONDecodeError):
        return None
    return value if isinstance(value, dict) else None


def _decision_payload(decision: SemanticCapabilityDecision) -> dict:
    return decision.model_dump(mode="json")


def _flow_turn_as_capability_decision(
    turn: FlowTurnDecision,
) -> SemanticCapabilityDecision:
    return SemanticCapabilityDecision(
        domains=[],
        capabilities=turn.capabilities,
        risk_flags=turn.risk_flags,
        flow_signal="interrupt" if turn.action == "interrupt" else "none",
        entity_hints=turn.entity_hints,
        missing_information=turn.missing_information,
        recommended_handoff_category=turn.recommended_handoff_category,
        recommended_handoff_priority=turn.recommended_handoff_priority,
        confidence=turn.confidence,
        reason=turn.reason,
    )


def _flow_type_from_capabilities(capabilities: set[str]) -> str | None:
    if "appointment_reschedule" in capabilities:
        return "appointment_reschedule"
    if (
        "availability_discovery" in capabilities
        or "appointment_creation" in capabilities
    ):
        return "booking"
    return None


def _handoff_direct(
    *,
    db: Session,
    tool_context: AgentToolContext,
    policy: CapabilityPolicyDecision,
    reason: str,
    run_id: UUID,
    flow: ConversationFlowState | None,
) -> tuple[str, str] | None:
    try:
        result = _invoke_authorized_tool(
            tool_context=tool_context,
            policy=policy,
            tool_name="escalate_to_human",
            arguments={
                "reason": reason or "Semantic safety policy requested human ownership.",
                "category": policy.handoff_category,
                "priority": policy.handoff_priority,
            },
        )
    except ToolAuthorizationError:
        return None

    if not result or result.get("ok") is not True:
        return None

    if flow is not None and flow.is_active:
        try:
            interrupt_flow(
                db,
                flow,
                run_id=run_id,
                reason=f"handoff:{policy.handoff_category}",
            )
        except FlowStateConflictError:
            # The handoff itself is already authoritative and pauses the agent.
            # Re-load the newest active flow version and interrupt that version so
            # resolving the handoff later cannot accidentally resume stale work.
            latest = get_active_flow(
                db,
                workspace_id=flow.workspace_id,
                conversation_id=flow.conversation_id,
                patient_id=flow.patient_id,
                run_id=run_id,
            )
            if latest is not None:
                interrupt_flow(
                    db,
                    latest,
                    run_id=run_id,
                    reason=f"handoff:{policy.handoff_category}",
                )
    return (
        format_handoff_reply(policy.handoff_category),
        "capability-policy:handoff",
    )


def _structured_flow_write(
    *,
    db: Session,
    flow: ConversationFlowState,
    turn: FlowTurnDecision,
    policy: CapabilityPolicyDecision,
    tool_context: AgentToolContext,
    run_id: UUID,
) -> tuple[str, str] | None:
    if turn.action != "select_option":
        return None

    slot = select_slot_from_structured_selection(
        flow.option_snapshot,
        selection_index=turn.selection_index,
        selection_time=turn.selection_time,
    )
    if slot is None:
        return None

    if flow.flow_type == "booking":
        tool_name = "book_appointment"
        arguments = booking_tool_args(slot)
    elif flow.flow_type == "appointment_reschedule":
        current = (flow.option_snapshot or {}).get("current_appointment")
        if not isinstance(current, dict) or not current.get("appointment_id"):
            return None
        tool_name = "reschedule_appointment"
        arguments = reschedule_tool_args(
            current_appointment_id=str(current["appointment_id"]),
            slot=slot,
        )
    else:
        return None

    try:
        authorize_tool_execution(policy, tool_name)
    except ToolAuthorizationError:
        return None

    # Optimistic state guard BEFORE the write. If another turn changed the
    # workflow after the interpreter saw it, this CAS fails and no booking /
    # reschedule tool is executed against stale state.
    flow = transition_flow(
        db,
        flow,
        actor_type="flow_interpreter",
        event_type="updated",
        run_id=run_id,
        status="ready_to_execute",
        pending_action={
            "tool_name": tool_name,
            "selection_index": turn.selection_index,
            "selection_time": turn.selection_time,
            "start_local": slot.get("start_local"),
        },
        last_decision=turn.model_dump(mode="json"),
    )

    record_write_authorized(
        db,
        flow,
        run_id=run_id,
        tool_name=tool_name,
    )
    result = _invoke_authorized_tool(
        tool_context=tool_context,
        policy=policy,
        tool_name=tool_name,
        arguments=arguments,
    )
    if not result or result.get("ok") is not True:
        return None

    record_write_completed(
        db,
        flow,
        run_id=run_id,
        tool_name=tool_name,
        result=result,
    )

    if flow.flow_type == "booking":
        appointment = result.get("appointment")
        if not isinstance(appointment, dict):
            return None
        complete_flow(
            db,
            flow,
            run_id=run_id,
            result={"tool": tool_name, "output": result},
        )
        return (
            format_booking_success(appointment),
            "flow-interpreter:deterministic-booking",
        )

    complete_flow(
        db,
        flow,
        run_id=run_id,
        result={"tool": tool_name, "output": result},
    )
    return (
        "تمام، الموعد اتغيّر للميعاد الجديد بنجاح.",
        "flow-interpreter:deterministic-reschedule",
    )


def _run_after_inbound(
    *,
    db: Session,
    workspace: Workspace,
    patient: Patient,
    conversation: Conversation,
    inbound: Message,
    run_id: UUID,
    outbound_delivery_status: str,
    source: str,
) -> AgentChatResponse:
    active_handoff = get_active_handoff(
        db,
        workspace_id=workspace.id,
        conversation_id=conversation.id,
    )
    if conversation.status == "pending" or active_handoff is not None:
        return AgentChatResponse(
            run_id=run_id,
            conversation_id=conversation.id,
            inbound_message_id=inbound.id,
            outbound_message_id=None,
            reply=None,
            handoff_required=True,
            agent_paused=True,
            model=None,
        )

    history = _history_from_db(db, conversation)
    flow = get_active_flow(
        db,
        workspace_id=workspace.id,
        conversation_id=conversation.id,
        patient_id=patient.id,
        run_id=run_id,
    )

    flow_turn: FlowTurnDecision | None = None
    if flow is not None:
        flow_turn = interpret_active_flow_turn(
            flow=flow,
            history=history,
        )
        semantic_decision = _flow_turn_as_capability_decision(flow_turn)
        inherited_capabilities = flow.capabilities if flow_turn.action != "interrupt" else []
    else:
        semantic_decision = route_customer_message(history=history)
        inherited_capabilities = []

    policy = resolve_capability_policy(
        semantic_decision,
        inherited_capabilities=inherited_capabilities,
    )

    if flow is None:
        flow_type = _flow_type_from_capabilities(set(policy.capabilities))
        if flow_type is not None and not policy.requires_human:
            flow = start_flow(
                db,
                workspace_id=workspace.id,
                conversation_id=conversation.id,
                patient_id=patient.id,
                flow_type=flow_type,
                capabilities=sorted(policy.capabilities),
                entity_state=semantic_decision.entity_hints.model_dump(
                    mode="json",
                    exclude_none=True,
                ),
                missing_information=semantic_decision.missing_information,
                last_decision=_decision_payload(semantic_decision),
                run_id=run_id,
            )
    elif flow_turn is not None and flow_turn.action in {"continue", "modify"}:
        flow = transition_flow(
            db,
            flow,
            actor_type="flow_interpreter",
            event_type="updated",
            run_id=run_id,
            capabilities=sorted(policy.capabilities),
            entity_state={
                **(flow.entity_state or {}),
                **flow_turn.entity_hints.model_dump(
                    mode="json",
                    exclude_none=True,
                ),
            },
            missing_information=flow_turn.missing_information,
            last_decision=flow_turn.model_dump(mode="json"),
        )

    tool_context = AgentToolContext(
        db=db,
        workspace=workspace,
        patient=patient,
        conversation=conversation,
        run_id=run_id,
    )

    direct: tuple[str, str] | None = None

    if policy.requires_human:
        direct = _handoff_direct(
            db=db,
            tool_context=tool_context,
            policy=policy,
            reason=semantic_decision.reason,
            run_id=run_id,
            flow=flow,
        )
    elif flow is not None and flow_turn is not None:
        if flow_turn.action == "cancel_flow":
            cancel_flow(
                db,
                flow,
                run_id=run_id,
                reason=flow_turn.reason or "customer_cancelled_flow",
            )
            direct = (
                "تمام، وقفت العملية الحالية. لو محتاج حاجة تانية أنا معاك.",
                "flow-interpreter:cancelled",
            )
        elif flow_turn.action == "interrupt":
            interrupt_flow(
                db,
                flow,
                run_id=run_id,
                reason=flow_turn.reason or "customer_interrupted_flow",
            )
            flow = None
        elif flow_turn.action == "select_option":
            direct = _structured_flow_write(
                db=db,
                flow=flow,
                turn=flow_turn,
                policy=policy,
                tool_context=tool_context,
                run_id=run_id,
            )

    if direct is not None:
        reply, model_name = direct
    else:
        operational_context = _recent_operational_context(
            db,
            conversation,
            flow,
        )
        agent_allowed_tools = set(policy.allowed_tools)
        # While a persisted booking/reschedule flow is active, write execution
        # is state-driven only. The main LLM can discover/reason, but cannot
        # bypass the workflow snapshot by calling the write tool directly.
        if flow is not None and flow.is_active:
            if flow.flow_type == "booking":
                agent_allowed_tools.discard("book_appointment")
            elif flow.flow_type == "appointment_reschedule":
                agent_allowed_tools.discard("reschedule_appointment")

        reply, model_name = run_tia_customer_agent(
            history=history,
            tool_context=tool_context,
            operational_context=operational_context,
            allowed_tool_names=agent_allowed_tools,
        )
        flow = sync_flow_from_agent_run(
            db,
            flow=flow,
            workspace_id=workspace.id,
            conversation_id=conversation.id,
            run_id=run_id,
        )

    reply = sanitize_customer_reply(reply)

    db.refresh(conversation)
    outbound_now = datetime.now(timezone.utc)
    outbound = Message(
        workspace_id=workspace.id,
        conversation_id=conversation.id,
        channel_connection_id=conversation.channel_connection_id,
        sender_type="ai",
        direction="outbound",
        message_type="text",
        content=reply,
        delivery_status=outbound_delivery_status,
        metadata_json={
            "agent_run_id": str(run_id),
            "model": model_name,
            "source": source,
            "in_reply_to_message_id": str(inbound.id),
            "dispatch_required": outbound_delivery_status == "queued",
            "capabilities": sorted(policy.capabilities),
            "risk_flags": sorted(policy.risk_flags),
            "flow_id": str(flow.id) if flow is not None else None,
            "flow_version": flow.version if flow is not None else None,
        },
    )
    conversation.last_message_at = outbound_now
    db.add(outbound)
    db.commit()
    db.refresh(outbound)
    db.refresh(conversation)

    return AgentChatResponse(
        run_id=run_id,
        conversation_id=conversation.id,
        inbound_message_id=inbound.id,
        outbound_message_id=outbound.id,
        reply=reply,
        handoff_required=conversation.status == "pending",
        agent_paused=False,
        model=model_name,
    )


def run_agent_chat(
    *,
    db: Session,
    workspace: Workspace,
    payload: AgentChatRequest,
) -> AgentChatResponse:
    now = datetime.now(timezone.utc)
    run_id = uuid4()
    patient = _get_patient(db, workspace.id, payload.patient_id)
    conversation = _get_or_create_conversation(
        db,
        workspace=workspace,
        patient=patient,
        payload=payload,
        now=now,
    )

    inbound = Message(
        workspace_id=workspace.id,
        conversation_id=conversation.id,
        channel_connection_id=conversation.channel_connection_id,
        sender_type="patient",
        direction="inbound",
        message_type="text",
        content=payload.message,
        delivery_status="received",
        metadata_json={"agent_run_id": str(run_id), "source": "agent_api"},
    )
    conversation.last_message_at = now
    patient.last_contact_at = now
    db.add(inbound)
    db.commit()
    db.refresh(inbound)
    db.refresh(conversation)
    db.refresh(patient)

    return _run_after_inbound(
        db=db,
        workspace=workspace,
        patient=patient,
        conversation=conversation,
        inbound=inbound,
        run_id=run_id,
        outbound_delivery_status="sent",
        source="agent_api",
    )


def run_agent_for_existing_inbound(
    *,
    db: Session,
    workspace: Workspace,
    patient: Patient,
    conversation: Conversation,
    inbound: Message,
    source: str = "channel_adapter",
) -> AgentChatResponse:
    if inbound.workspace_id != workspace.id:
        raise AgentChatError("Inbound message belongs to another workspace.")
    if inbound.conversation_id != conversation.id:
        raise AgentChatError("Inbound message belongs to another conversation.")
    if conversation.patient_id != patient.id:
        raise AgentChatError("Conversation belongs to another patient.")
    if inbound.sender_type != "patient" or inbound.direction != "inbound":
        raise AgentChatError(
            "Only inbound patient messages can be processed by the customer agent."
        )
    if patient.status == "blocked":
        raise AgentChatError("Blocked patients cannot use the automated customer agent.")

    run_id = uuid4()
    metadata = dict(inbound.metadata_json or {})
    metadata["agent_run_id"] = str(run_id)
    inbound.metadata_json = metadata
    patient.last_contact_at = inbound.created_at
    db.commit()
    db.refresh(inbound)

    return _run_after_inbound(
        db=db,
        workspace=workspace,
        patient=patient,
        conversation=conversation,
        inbound=inbound,
        run_id=run_id,
        outbound_delivery_status="queued",
        source=source,
    )
