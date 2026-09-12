from __future__ import annotations

from datetime import UTC, datetime
from uuid import UUID, uuid4

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import settings
from app.integrations.clinic.registry import get_clinic_adapter
from app.models.conversation import Conversation
from app.models.message import Message
from app.models.patient import Patient
from app.models.workspace import Workspace
from app.schemas.agent import AgentChatRequest, AgentChatResponse
from app.services.agent_chat import (
    AgentChatError,
    _existing_agent_response_for_inbound,
    _get_or_create_conversation,
    _history_from_db,
    _uuid_from_metadata,
    _workspace_clock,
)
from app.services.agent_chat import (
    run_agent_chat as run_agent_chat_v1,
)
from app.services.agent_chat import (
    run_agent_for_existing_inbound as run_agent_for_existing_inbound_v1,
)
from app.services.agent_v2.orchestrator import V2OrchestratedTurn, orchestrate_v2_turn
from app.services.agent_v2.write_executor import execute_write_ready_step
from app.services.conversation_ownership import (
    OWNER_HUMAN,
    agent_can_reply,
    lock_conversation_ownership,
    record_customer_inbound,
)
from app.services.handoffs import create_handoff, get_active_handoff


def _get_patient_v2(db: Session, *, workspace_id: UUID, patient_id: UUID) -> Patient:
    patient = db.scalar(
        select(Patient).where(
            Patient.workspace_id == workspace_id,
            Patient.id == patient_id,
        )
    )
    if patient is None:
        raise AgentChatError("Patient not found in this workspace.")
    # Do not reject blocked patients globally. V2's verified write executor blocks
    # new bookings while still allowing cancellation/reschedule of existing visits.
    return patient


def _handoff_reason(turn: V2OrchestratedTurn) -> str:
    for outcome in turn.outcomes:
        if outcome.status != "handoff":
            continue
        detail = outcome.action_result.get("detail")
        if detail:
            return str(detail)[:4000]
    return "human_handoff_requested"


def _v2_handoff_ack_allowed(handoff: object | None, *, created_this_turn: bool) -> bool:
    if not created_this_turn or handoff is None:
        return False
    return (
        getattr(handoff, "source", None) == "ai"
        and getattr(handoff, "status", None) == "pending"
        and getattr(handoff, "assigned_user_id", None) is None
    )


def _run_v2_after_inbound(
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
    if not agent_can_reply(conversation) or active_handoff is not None:
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
    timezone_name, local_now = _workspace_clock(workspace)
    adapter = get_clinic_adapter(db=db, workspace=workspace)

    def live_write(step):
        return execute_write_ready_step(
            db,
            workspace=workspace,
            patient=patient,
            step=step,
            idempotency_key=f"v2:{inbound.id}:{step.operation_index}",
            commit=False,
        )

    turn = orchestrate_v2_turn(
        db=db,
        workspace=workspace,
        patient=patient,
        conversation_id=conversation.id,
        run_id=run_id,
        history=history,
        local_now=local_now,
        timezone_name=timezone_name,
        clinic_name=workspace.name,
        adapter=adapter,
        turn_id=str(inbound.id),
        write_executor=live_write,
    )
    if turn.pending_write is not None:
        raise RuntimeError("Live V2 turn returned an unexecuted verified write.")
    if not turn.reply:
        raise RuntimeError("Live V2 turn produced no customer reply.")

    created_handoff_this_turn = any(outcome.status == "handoff" for outcome in turn.outcomes)
    if created_handoff_this_turn:
        create_handoff(
            db,
            workspace_id=workspace.id,
            conversation=conversation,
            patient=patient,
            reason=_handoff_reason(turn),
            category=turn.plan.handoff_category or "other",
            priority="normal",
            source="ai",
            commit=False,
        )

    # A staff member may take ownership while the model is running. Re-lock and
    # re-check immediately before creating the outbound message. The one exception
    # is the acknowledgement for a handoff created by this V2 turn itself.
    locked_conversation = lock_conversation_ownership(
        db,
        workspace_id=workspace.id,
        conversation_id=conversation.id,
    )
    if locked_conversation is None:
        raise AgentChatError("Conversation disappeared before the agent response was persisted.")
    conversation = locked_conversation
    active_handoff = get_active_handoff(
        db,
        workspace_id=workspace.id,
        conversation_id=conversation.id,
    )
    handoff_ack_allowed = _v2_handoff_ack_allowed(
        active_handoff,
        created_this_turn=created_handoff_this_turn,
    )
    if (not agent_can_reply(conversation) or active_handoff is not None) and not handoff_ack_allowed:
        # Roll back the entire V2 turn so a staff takeover cannot leave a clinic write
        # committed without the state/outbound part of the same turn.
        db.rollback()
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

    outbound_now = datetime.now(UTC)
    outbound = Message(
        workspace_id=workspace.id,
        conversation_id=conversation.id,
        channel_connection_id=conversation.channel_connection_id,
        sender_type="ai",
        direction="outbound",
        created_at=outbound_now,
        message_type="text",
        content=turn.reply,
        delivery_status=outbound_delivery_status,
        metadata_json={
            "agent_run_id": str(run_id),
            "model": turn.responder_model,
            "source": source,
            "runtime": "v2",
            "in_reply_to_message_id": str(inbound.id),
            "dispatch_required": outbound_delivery_status == "queued",
            "handoff_ack": handoff_ack_allowed,
        },
    )
    conversation.last_message_at = outbound_now
    db.add(outbound)
    db.commit()

    return AgentChatResponse(
        run_id=run_id,
        conversation_id=conversation.id,
        inbound_message_id=inbound.id,
        outbound_message_id=outbound.id,
        reply=turn.reply,
        handoff_required=conversation.owner_type == OWNER_HUMAN,
        agent_paused=False,
        model=turn.responder_model,
    )


def run_agent_chat(
    *,
    db: Session,
    workspace: Workspace,
    payload: AgentChatRequest,
) -> AgentChatResponse:
    if not settings.agent_v2_live_enabled:
        return run_agent_chat_v1(db=db, workspace=workspace, payload=payload)

    now = datetime.now(UTC)
    run_id = uuid4()
    patient = _get_patient_v2(db, workspace_id=workspace.id, patient_id=payload.patient_id)
    conversation = _get_or_create_conversation(
        db,
        workspace=workspace,
        patient=patient,
        payload=payload,
        now=now,
    )
    activity_now = datetime.now(UTC)
    inbound = Message(
        workspace_id=workspace.id,
        conversation_id=conversation.id,
        channel_connection_id=conversation.channel_connection_id,
        sender_type="patient",
        direction="inbound",
        created_at=activity_now,
        message_type="text",
        content=payload.message,
        delivery_status="received",
        metadata_json={"agent_run_id": str(run_id), "source": "agent_api"},
    )
    record_customer_inbound(conversation, now=activity_now)
    patient.last_contact_at = activity_now
    db.add(inbound)
    db.commit()
    db.refresh(inbound)
    db.refresh(conversation)
    db.refresh(patient)
    return _run_v2_after_inbound(
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
    if not settings.agent_v2_live_enabled:
        return run_agent_for_existing_inbound_v1(
            db=db,
            workspace=workspace,
            patient=patient,
            conversation=conversation,
            inbound=inbound,
            source=source,
        )

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

    metadata = dict(inbound.metadata_json or {})
    existing_run_id = _uuid_from_metadata(metadata.get("agent_run_id"))
    run_id = existing_run_id or uuid4()
    metadata["agent_run_id"] = str(run_id)
    try:
        prior_attempts = int(metadata.get("agent_processing_attempts") or 0)
    except (TypeError, ValueError):
        prior_attempts = 0
    metadata["agent_processing_attempts"] = prior_attempts + 1
    inbound.metadata_json = metadata
    patient.last_contact_at = inbound.created_at
    db.commit()
    db.refresh(inbound)

    if existing_run_id is not None:
        existing_response = _existing_agent_response_for_inbound(
            db,
            conversation=conversation,
            inbound=inbound,
            run_id=run_id,
        )
        if existing_response is not None:
            return existing_response

    return _run_v2_after_inbound(
        db=db,
        workspace=workspace,
        patient=patient,
        conversation=conversation,
        inbound=inbound,
        run_id=run_id,
        outbound_delivery_status="queued",
        source=source,
    )
