from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import UTC, datetime
from uuid import UUID, uuid4

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.agents.semantic_actions import format_booking_success
from app.agents.tools.clinic_tools import AgentToolContext, build_clinic_tools
from app.models.agent_action import AgentAction
from app.models.conversation import Conversation
from app.models.message import Message
from app.models.patient import Patient
from app.models.workspace import Workspace
from app.schemas.agent import AgentChatResponse
from app.services.conversation_flows import start_flow
from app.services.conversation_ownership import OWNER_HUMAN, agent_can_reply
from app.services.handoffs import get_active_handoff

_CONFIRM_PREFIX = "tia.booking.confirm:"
_RESCHEDULE_PREFIX = "tia.booking.reschedule:"
_MAX_APPOINTMENT_REF_LENGTH = 180


@dataclass(frozen=True)
class WhatsAppBookingAction:
    action: str
    appointment_id: str


def parse_whatsapp_booking_action(metadata: object) -> WhatsAppBookingAction | None:
    """Parse only a structured Meta button reply; customer-visible text is never routing input."""
    if not isinstance(metadata, dict):
        return None
    reply = metadata.get("interactive_reply")
    if not isinstance(reply, dict) or reply.get("type") != "button_reply":
        return None
    raw_id = reply.get("id")
    if not isinstance(raw_id, str):
        return None
    raw_id = raw_id.strip()

    for prefix, action in (
        (_CONFIRM_PREFIX, "confirm"),
        (_RESCHEDULE_PREFIX, "reschedule"),
    ):
        if not raw_id.startswith(prefix):
            continue
        appointment_id = raw_id[len(prefix) :].strip()
        if not appointment_id or len(appointment_id) > _MAX_APPOINTMENT_REF_LENGTH:
            return None
        return WhatsAppBookingAction(action=action, appointment_id=appointment_id)
    return None


def _uuid(value: object) -> UUID | None:
    try:
        return UUID(str(value))
    except (TypeError, ValueError):
        return None


def _invoke_tool(ctx: AgentToolContext, tool_name: str, arguments: dict) -> dict | None:
    tool = next((item for item in build_clinic_tools(ctx) if item.name == tool_name), None)
    if tool is None:
        return None
    raw = tool.invoke(arguments)
    try:
        value = json.loads(raw)
    except (TypeError, json.JSONDecodeError):
        return None
    return value if isinstance(value, dict) else None


def _existing_response(
    db: Session,
    *,
    conversation: Conversation,
    inbound: Message,
    run_id: UUID,
) -> AgentChatResponse | None:
    outbound = db.scalar(
        select(Message)
        .where(
            Message.workspace_id == conversation.workspace_id,
            Message.conversation_id == conversation.id,
            Message.sender_type == "ai",
            Message.direction == "outbound",
            Message.metadata_json["in_reply_to_message_id"].as_string() == str(inbound.id),
        )
        .order_by(Message.created_at.desc())
        .limit(1)
    )
    if outbound is None:
        return None
    metadata = outbound.metadata_json or {}
    return AgentChatResponse(
        run_id=_uuid(metadata.get("agent_run_id")) or run_id,
        conversation_id=conversation.id,
        inbound_message_id=inbound.id,
        outbound_message_id=outbound.id,
        reply=outbound.content,
        handoff_required=conversation.owner_type == OWNER_HUMAN,
        agent_paused=False,
        model=metadata.get("model"),
    )


def _persist_reply(
    db: Session,
    *,
    conversation: Conversation,
    inbound: Message,
    run_id: UUID,
    reply: str,
    action: str,
) -> AgentChatResponse:
    now = datetime.now(UTC)
    outbound = Message(
        workspace_id=conversation.workspace_id,
        conversation_id=conversation.id,
        channel_connection_id=conversation.channel_connection_id,
        sender_type="ai",
        direction="outbound",
        message_type="text",
        content=reply,
        delivery_status="queued",
        metadata_json={
            "agent_run_id": str(run_id),
            "model": "structured:whatsapp-button",
            "source": "whatsapp_interactive",
            "in_reply_to_message_id": str(inbound.id),
            "dispatch_required": True,
            "interactive_action": action,
        },
    )
    conversation.last_message_at = now
    db.add(outbound)
    db.commit()
    return AgentChatResponse(
        run_id=run_id,
        conversation_id=conversation.id,
        inbound_message_id=inbound.id,
        outbound_message_id=outbound.id,
        reply=reply,
        handoff_required=False,
        agent_paused=False,
        model="structured:whatsapp-button",
    )


def process_whatsapp_booking_action(
    db: Session,
    *,
    workspace: Workspace,
    patient: Patient,
    conversation: Conversation,
    inbound: Message,
) -> AgentChatResponse | None:
    """Execute a trusted structured WhatsApp booking action without text/keyword routing."""
    action = parse_whatsapp_booking_action(inbound.metadata_json or {})
    if action is None:
        return None
    if not agent_can_reply(conversation):
        return None
    if get_active_handoff(
        db,
        workspace_id=workspace.id,
        conversation_id=conversation.id,
    ) is not None:
        return None

    inbound_metadata = dict(inbound.metadata_json or {})
    run_id = _uuid(inbound_metadata.get("agent_run_id")) or uuid4()
    inbound_metadata["agent_run_id"] = str(run_id)
    inbound.metadata_json = inbound_metadata

    recovered = _existing_response(
        db,
        conversation=conversation,
        inbound=inbound,
        run_id=run_id,
    )
    if recovered is not None:
        return recovered

    ctx = AgentToolContext(
        db=db,
        workspace=workspace,
        patient=patient,
        conversation=conversation,
        run_id=run_id,
    )

    if action.action == "confirm":
        result = _invoke_tool(
            ctx,
            "confirm_appointment",
            {"appointment_id": action.appointment_id},
        )
        appointment = result.get("appointment") if isinstance(result, dict) else None
        if isinstance(appointment, dict) and result.get("ok") is True:
            reply = format_booking_success(appointment)
        else:
            reply = "معلش، مقدرتش أأكد الحجز ده دلوقتي. ممكن أراجعلك مواعيدك الحالية."
        return _persist_reply(
            db,
            conversation=conversation,
            inbound=inbound,
            run_id=run_id,
            reply=reply,
            action="confirm",
        )

    appointments_result = _invoke_tool(ctx, "get_customer_appointments", {"include_past": False})
    appointments = (
        appointments_result.get("appointments")
        if isinstance(appointments_result, dict) and appointments_result.get("ok") is True
        else None
    )
    current = next(
        (
            item
            for item in appointments or []
            if isinstance(item, dict)
            and str(item.get("appointment_id") or "") == action.appointment_id
            and str(item.get("status") or "") in {"pending", "confirmed"}
        ),
        None,
    )
    if current is None:
        return _persist_reply(
            db,
            conversation=conversation,
            inbound=inbound,
            run_id=run_id,
            reply="مش لاقي الحجز ده ضمن مواعيدك القادمة. ممكن أراجعلك المواعيد الحالية.",
            action="reschedule",
        )

    start_flow(
        db,
        workspace_id=workspace.id,
        conversation_id=conversation.id,
        patient_id=patient.id,
        flow_type="appointment_reschedule",
        capabilities=["appointment_reschedule"],
        entity_state={
            "appointment_id": action.appointment_id,
            "current_appointment": current,
        },
        missing_information=["requested_date"],
        last_decision={
            "source": "whatsapp_interactive",
            "action": "reschedule",
            "appointment_id": action.appointment_id,
        },
        run_id=run_id,
    )
    return _persist_reply(
        db,
        conversation=conversation,
        inbound=inbound,
        run_id=run_id,
        reply="تمام، تحب تغيّر الموعد ليوم إيه ووقت كام؟",
        action="reschedule",
    )


def whatsapp_booking_dispatch_metadata(
    db: Session,
    *,
    message: Message,
) -> dict:
    """Offer only pending-booking confirmation; rescheduling stays natural-text only."""
    metadata = dict(message.metadata_json or {})
    run_id = _uuid(metadata.get("agent_run_id"))
    if run_id is None or message.sender_type != "ai":
        return metadata

    action = db.scalar(
        select(AgentAction)
        .where(
            AgentAction.workspace_id == message.workspace_id,
            AgentAction.conversation_id == message.conversation_id,
            AgentAction.run_id == run_id,
            AgentAction.tool_name == "book_appointment",
            AgentAction.status == "success",
        )
        .order_by(AgentAction.created_at.desc())
        .limit(1)
    )
    output = action.output_json if action is not None else None
    appointment = output.get("appointment") if isinstance(output, dict) else None
    if not isinstance(appointment, dict):
        return metadata
    appointment_id = str(appointment.get("appointment_id") or "").strip()
    if not appointment_id or len(appointment_id) > _MAX_APPOINTMENT_REF_LENGTH:
        return metadata

    buttons: list[dict[str, str]] = []
    if str(appointment.get("status") or "") == "pending":
        buttons.append(
            {
                "id": f"{_CONFIRM_PREFIX}{appointment_id}",
                "title": "تأكيد الحجز",
            }
        )
    if not buttons:
        return metadata
    metadata["whatsapp_interactive"] = {
        "type": "button",
        "buttons": buttons,
    }
    return metadata
