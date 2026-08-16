from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from uuid import UUID

from sqlalchemy import and_, or_, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.core.channel_adapter import (
    channel_to_patient_source,
    hash_adapter_token,
)
from app.core.channel_delivery import apply_provider_delivery_status
from app.models.channel_connection import ChannelConnection
from app.models.channel_delivery_event import ChannelDeliveryEvent
from app.models.channel_identity import ChannelIdentity
from app.models.channel_inbound_event import ChannelInboundEvent
from app.models.conversation import Conversation
from app.models.message import Message
from app.models.message_dispatch import MessageDispatch
from app.models.patient import Patient
from app.models.workspace import Workspace
from app.schemas.agent import AgentChatResponse
from app.schemas.channel import DispatchClaimItem, NormalizedInboundMessage
from app.schemas.crm import normalize_email, normalize_phone
from app.services.agent_chat import run_agent_for_existing_inbound


class ChannelError(ValueError):
    pass


class ChannelConflictError(ChannelError):
    pass


@dataclass(frozen=True)
class AcceptedInbound:
    event: ChannelInboundEvent
    message: Message
    patient: Patient
    conversation: Conversation
    duplicate: bool


@dataclass(frozen=True)
class ProcessedInbound:
    event: ChannelInboundEvent
    agent_response: AgentChatResponse
    dispatch: MessageDispatch | None


@dataclass(frozen=True)
class RecordedProviderStatus:
    event: ChannelDeliveryEvent
    dispatch: MessageDispatch | None
    duplicate: bool


def get_connection_by_adapter_token(
    db: Session,
    raw_token: str,
) -> ChannelConnection | None:
    """
    Authenticate a channel adapter using the raw X-Channel-Token.

    Only the SHA-256 hash is stored in PostgreSQL. Paused or disconnected
    connections are intentionally rejected so adapters cannot ingest/process
    traffic while a channel is disabled.
    """
    token = raw_token.strip() if isinstance(raw_token, str) else ""
    if not token:
        return None

    return db.scalar(
        select(ChannelConnection).where(
            ChannelConnection.adapter_token_hash == hash_adapter_token(token),
            ChannelConnection.status == "active",
        )
    )


def _patient_display_name(payload: NormalizedInboundMessage, channel: str) -> str:
    if payload.display_name:
        return payload.display_name[:120]
    if payload.phone:
        return payload.phone[:120]
    return f"عميل {channel}"[:120]


def _resolve_patient_for_new_identity(
    db: Session,
    *,
    connection: ChannelConnection,
    payload: NormalizedInboundMessage,
) -> Patient:
    display_phone, normalized_phone = normalize_phone(payload.phone)
    normalized_email = normalize_email(payload.email)

    patient = None
    if normalized_phone:
        patient = db.scalar(
            select(Patient).where(
                Patient.workspace_id == connection.workspace_id,
                Patient.phone_normalized == normalized_phone,
            )
        )

    if patient is None and normalized_email:
        email_matches = list(
            db.scalars(
                select(Patient)
                .where(
                    Patient.workspace_id == connection.workspace_id,
                    Patient.email == normalized_email,
                )
                .limit(2)
            )
        )
        if len(email_matches) == 1:
            patient = email_matches[0]

    if patient is not None:
        if patient.phone is None and display_phone:
            patient.phone = display_phone
            patient.phone_normalized = normalized_phone
        if patient.email is None and normalized_email:
            patient.email = normalized_email
        return patient

    patient = Patient(
        workspace_id=connection.workspace_id,
        first_name=_patient_display_name(payload, connection.channel),
        last_name=None,
        phone=display_phone,
        phone_normalized=normalized_phone,
        email=normalized_email,
        preferred_language="ar",
        source=channel_to_patient_source(connection.channel),
        source_detail=f"{connection.provider}:{connection.display_name}"[:200],
        status="active",
        marketing_consent=False,
    )
    db.add(patient)
    db.flush()
    return patient


def _resolve_identity(
    db: Session,
    *,
    connection: ChannelConnection,
    payload: NormalizedInboundMessage,
) -> tuple[ChannelIdentity, Patient]:
    identity = db.scalar(
        select(ChannelIdentity).where(
            ChannelIdentity.workspace_id == connection.workspace_id,
            ChannelIdentity.channel_connection_id == connection.id,
            ChannelIdentity.external_user_id == payload.external_user_id,
        )
    )

    if identity is not None:
        patient = db.scalar(
            select(Patient).where(
                Patient.workspace_id == connection.workspace_id,
                Patient.id == identity.patient_id,
            )
        )
        if patient is None:
            raise ChannelError("Channel identity references a missing patient.")

        if payload.display_name:
            identity.display_name = payload.display_name
        if payload.phone:
            identity.phone = payload.phone
        if payload.email:
            identity.email = normalize_email(payload.email)
        identity.metadata_json = {**(identity.metadata_json or {}), **payload.metadata}
        return identity, patient

    patient = _resolve_patient_for_new_identity(
        db,
        connection=connection,
        payload=payload,
    )
    identity = ChannelIdentity(
        workspace_id=connection.workspace_id,
        channel_connection_id=connection.id,
        patient_id=patient.id,
        external_user_id=payload.external_user_id,
        display_name=payload.display_name,
        phone=payload.phone,
        email=normalize_email(payload.email),
        metadata_json=payload.metadata,
    )
    db.add(identity)
    db.flush()
    return identity, patient


def _resolve_conversation(
    db: Session,
    *,
    connection: ChannelConnection,
    patient: Patient,
    payload: NormalizedInboundMessage,
) -> Conversation:
    external_conversation_id = (
        payload.external_conversation_id or payload.external_user_id
    )
    conversation = db.scalar(
        select(Conversation).where(
            Conversation.workspace_id == connection.workspace_id,
            Conversation.channel_connection_id == connection.id,
            Conversation.external_conversation_id == external_conversation_id,
        )
    )

    now = datetime.now(timezone.utc)
    if conversation is not None:
        if conversation.patient_id != patient.id:
            raise ChannelConflictError(
                "External conversation is already linked to another patient."
            )
        if conversation.status == "closed":
            conversation.status = "open"
            conversation.closed_at = None
        return conversation

    conversation = Conversation(
        workspace_id=connection.workspace_id,
        patient_id=patient.id,
        channel=connection.channel,
        channel_connection_id=connection.id,
        external_conversation_id=external_conversation_id,
        status="open",
        started_at=now,
        last_message_at=now,
    )
    db.add(conversation)
    db.flush()
    return conversation


def accept_normalized_inbound(
    db: Session,
    *,
    connection: ChannelConnection,
    payload: NormalizedInboundMessage,
) -> AcceptedInbound:
    existing_event = db.scalar(
        select(ChannelInboundEvent).where(
            ChannelInboundEvent.channel_connection_id == connection.id,
            ChannelInboundEvent.external_event_id == payload.external_event_id,
        )
    )
    if existing_event is not None:
        message = db.get(Message, existing_event.message_id)
        if message is None:
            raise ChannelError("Existing inbound event references a missing message.")
        conversation = db.scalar(
            select(Conversation).where(
                Conversation.workspace_id == connection.workspace_id,
                Conversation.id == message.conversation_id,
            )
        )
        patient = (
            db.get(Patient, conversation.patient_id) if conversation is not None else None
        )
        if conversation is None or patient is None:
            raise ChannelError("Existing inbound event references missing CRM data.")
        return AcceptedInbound(
            event=existing_event,
            message=message,
            patient=patient,
            conversation=conversation,
            duplicate=True,
        )

    existing_message = db.scalar(
        select(Message).where(
            Message.workspace_id == connection.workspace_id,
            Message.channel_connection_id == connection.id,
            Message.external_message_id == payload.external_message_id,
        )
    )
    if existing_message is not None:
        event = db.scalar(
            select(ChannelInboundEvent).where(
                ChannelInboundEvent.message_id == existing_message.id
            )
        )
        conversation = db.scalar(
            select(Conversation).where(
                Conversation.workspace_id == connection.workspace_id,
                Conversation.id == existing_message.conversation_id,
            )
        )
        patient = (
            db.get(Patient, conversation.patient_id) if conversation is not None else None
        )
        if event is None or conversation is None or patient is None:
            raise ChannelConflictError(
                "External message id already exists but cannot be safely replayed."
            )
        return AcceptedInbound(
            event=event,
            message=existing_message,
            patient=patient,
            conversation=conversation,
            duplicate=True,
        )

    _, patient = _resolve_identity(
        db,
        connection=connection,
        payload=payload,
    )
    conversation = _resolve_conversation(
        db,
        connection=connection,
        patient=patient,
        payload=payload,
    )

    now = datetime.now(timezone.utc)
    inbound = Message(
        workspace_id=connection.workspace_id,
        conversation_id=conversation.id,
        channel_connection_id=connection.id,
        sender_type="patient",
        direction="inbound",
        message_type=payload.message_type,
        content=payload.text,
        external_message_id=payload.external_message_id,
        delivery_status="received",
        metadata_json={
            "source": "channel_adapter",
            "provider": connection.provider,
            "external_event_id": payload.external_event_id,
            "external_user_id": payload.external_user_id,
            **payload.metadata,
        },
    )
    conversation.last_message_at = now
    patient.last_contact_at = now
    db.add(inbound)
    db.flush()

    event = ChannelInboundEvent(
        workspace_id=connection.workspace_id,
        channel_connection_id=connection.id,
        message_id=inbound.id,
        external_event_id=payload.external_event_id,
        status="received",
        attempts=0,
        payload_json=payload.model_dump(mode="json"),
    )
    db.add(event)

    try:
        db.commit()
    except IntegrityError as exc:
        db.rollback()
        raise ChannelConflictError(
            "Inbound event collided with an existing provider event/message id."
        ) from exc

    db.refresh(event)
    db.refresh(inbound)
    db.refresh(patient)
    db.refresh(conversation)
    return AcceptedInbound(
        event=event,
        message=inbound,
        patient=patient,
        conversation=conversation,
        duplicate=False,
    )


def queue_message_dispatch(
    db: Session,
    *,
    message: Message,
    conversation: Conversation,
    commit: bool = True,
) -> MessageDispatch | None:
    connection_id = message.channel_connection_id or conversation.channel_connection_id
    if connection_id is None:
        return None
    if message.direction != "outbound":
        raise ChannelError("Only outbound messages can be queued for dispatch.")

    existing = db.scalar(
        select(MessageDispatch).where(
            MessageDispatch.workspace_id == message.workspace_id,
            MessageDispatch.message_id == message.id,
        )
    )
    if existing is not None:
        return existing

    message.channel_connection_id = connection_id
    message.delivery_status = "queued"
    dispatch = MessageDispatch(
        workspace_id=message.workspace_id,
        channel_connection_id=connection_id,
        message_id=message.id,
        status="queued",
        attempts=0,
        metadata_json={
            "conversation_id": str(conversation.id),
            "sender_type": message.sender_type,
        },
    )
    db.add(dispatch)
    if commit:
        db.commit()
        db.refresh(dispatch)
        db.refresh(message)
    else:
        db.flush()
    return dispatch


def _processed_event_response(
    db: Session,
    *,
    event: ChannelInboundEvent,
) -> ProcessedInbound | None:
    if event.status != "processed":
        return None

    inbound = db.get(Message, event.message_id)
    if inbound is None:
        raise ChannelError("Processed inbound event references a missing message.")
    conversation = db.get(Conversation, inbound.conversation_id)
    if conversation is None:
        raise ChannelError("Processed inbound event references a missing conversation.")

    outbound = db.get(Message, event.outbound_message_id) if event.outbound_message_id else None
    dispatch = None
    if outbound is not None:
        dispatch = db.scalar(
            select(MessageDispatch).where(MessageDispatch.message_id == outbound.id)
        )

    response = AgentChatResponse(
        run_id=UUID(str((inbound.metadata_json or {}).get("agent_run_id")))
        if (inbound.metadata_json or {}).get("agent_run_id")
        else UUID(int=0),
        conversation_id=conversation.id,
        inbound_message_id=inbound.id,
        outbound_message_id=outbound.id if outbound else None,
        reply=outbound.content if outbound else None,
        handoff_required=conversation.status == "pending",
        agent_paused=outbound is None and conversation.status == "pending",
        model=(outbound.metadata_json or {}).get("model") if outbound else None,
    )
    return ProcessedInbound(event=event, agent_response=response, dispatch=dispatch)


def process_inbound_event(
    db: Session,
    *,
    connection: ChannelConnection,
    event_id: UUID,
) -> ProcessedInbound:
    event = db.scalar(
        select(ChannelInboundEvent)
        .where(
            ChannelInboundEvent.id == event_id,
            ChannelInboundEvent.workspace_id == connection.workspace_id,
            ChannelInboundEvent.channel_connection_id == connection.id,
        )
        .with_for_update()
    )
    if event is None:
        raise ChannelError("Inbound event not found for this channel connection.")

    already_processed = _processed_event_response(db, event=event)
    if already_processed is not None:
        db.rollback()
        return already_processed

    stale_before = datetime.now(timezone.utc) - timedelta(minutes=5)
    if event.status == "processing" and event.updated_at > stale_before:
        db.rollback()
        raise ChannelConflictError("Inbound event is already being processed.")

    event.status = "processing"
    event.attempts += 1
    event.last_error = None
    db.commit()

    try:
        inbound = db.get(Message, event.message_id)
        if inbound is None:
            raise ChannelError("Inbound event references a missing message.")
        conversation = db.scalar(
            select(Conversation).where(
                Conversation.workspace_id == connection.workspace_id,
                Conversation.id == inbound.conversation_id,
            )
        )
        if conversation is None:
            raise ChannelError("Inbound event references a missing conversation.")
        patient = db.scalar(
            select(Patient).where(
                Patient.workspace_id == connection.workspace_id,
                Patient.id == conversation.patient_id,
            )
        )
        workspace = db.get(Workspace, connection.workspace_id)
        if patient is None or workspace is None:
            raise ChannelError("Inbound event references missing workspace CRM data.")

        agent_response = run_agent_for_existing_inbound(
            db=db,
            workspace=workspace,
            patient=patient,
            conversation=conversation,
            inbound=inbound,
        )

        dispatch = None
        if agent_response.outbound_message_id is not None:
            outbound = db.get(Message, agent_response.outbound_message_id)
            if outbound is None:
                raise ChannelError("Agent created an outbound id but the message is missing.")
            dispatch = queue_message_dispatch(
                db,
                message=outbound,
                conversation=conversation,
                commit=False,
            )
            event.outbound_message_id = outbound.id

        event.status = "processed"
        event.last_error = None
        db.commit()
        db.refresh(event)
        if dispatch is not None:
            db.refresh(dispatch)

        return ProcessedInbound(
            event=event,
            agent_response=agent_response,
            dispatch=dispatch,
        )
    except Exception as exc:
        db.rollback()
        failed_event = db.get(ChannelInboundEvent, event_id)
        if failed_event is not None:
            failed_event.status = "failed"
            failed_event.last_error = f"{type(exc).__name__}: {exc}"[:2000]
            db.commit()
        raise


def claim_dispatches(
    db: Session,
    *,
    connection: ChannelConnection,
    limit: int,
) -> list[DispatchClaimItem]:
    now = datetime.now(timezone.utc)
    stale_before = now - timedelta(minutes=10)

    stmt = (
        select(MessageDispatch)
        .where(
            MessageDispatch.workspace_id == connection.workspace_id,
            MessageDispatch.channel_connection_id == connection.id,
            or_(
                and_(
                    MessageDispatch.status == "queued",
                    or_(
                        MessageDispatch.next_attempt_at.is_(None),
                        MessageDispatch.next_attempt_at <= now,
                    ),
                ),
                and_(
                    MessageDispatch.status == "processing",
                    MessageDispatch.locked_at.is_not(None),
                    MessageDispatch.locked_at <= stale_before,
                ),
            ),
        )
        .order_by(MessageDispatch.created_at)
        .with_for_update(skip_locked=True)
        .limit(limit)
    )
    dispatches = list(db.scalars(stmt))
    claimed: list[DispatchClaimItem] = []

    for dispatch in dispatches:
        message = db.get(Message, dispatch.message_id)
        if message is None:
            dispatch.status = "failed"
            dispatch.last_error = "Outbound message no longer exists."
            continue

        conversation = db.scalar(
            select(Conversation).where(
                Conversation.workspace_id == connection.workspace_id,
                Conversation.id == message.conversation_id,
            )
        )
        if conversation is None:
            dispatch.status = "failed"
            dispatch.last_error = "Conversation no longer exists."
            continue

        identity = db.scalar(
            select(ChannelIdentity).where(
                ChannelIdentity.workspace_id == connection.workspace_id,
                ChannelIdentity.channel_connection_id == connection.id,
                ChannelIdentity.patient_id == conversation.patient_id,
            )
        )
        if identity is None:
            dispatch.status = "failed"
            dispatch.last_error = "No channel identity found for conversation patient."
            continue

        dispatch.status = "processing"
        dispatch.attempts += 1
        dispatch.locked_at = now
        dispatch.last_error = None
        dispatch.next_attempt_at = None

        claimed.append(
            DispatchClaimItem(
                dispatch_id=dispatch.id,
                message_id=message.id,
                channel=connection.channel,
                provider=connection.provider,
                external_account_id=connection.external_account_id,
                external_user_id=identity.external_user_id,
                external_conversation_id=(
                    conversation.external_conversation_id or identity.external_user_id
                ),
                message_type=message.message_type,
                content=message.content,
                metadata=message.metadata_json or {},
                attempt=dispatch.attempts,
            )
        )

    db.commit()
    return claimed



def _reconcile_pending_delivery_events(
    db: Session,
    *,
    connection: ChannelConnection,
    dispatch: MessageDispatch,
    message: Message,
) -> None:
    if not dispatch.provider_message_id:
        return

    events = list(
        db.scalars(
            select(ChannelDeliveryEvent)
            .where(
                ChannelDeliveryEvent.workspace_id == connection.workspace_id,
                ChannelDeliveryEvent.channel_connection_id == connection.id,
                ChannelDeliveryEvent.provider_message_id == dispatch.provider_message_id,
                ChannelDeliveryEvent.processed_at.is_(None),
            )
            .order_by(
                ChannelDeliveryEvent.occurred_at.asc().nulls_last(),
                ChannelDeliveryEvent.created_at,
            )
            .with_for_update()
        )
    )

    for event in events:
        payload = event.payload_json or {}
        apply_provider_delivery_status(
            dispatch=dispatch,
            message=message,
            provider_status=event.status,
            occurred_at=event.occurred_at,
            error=payload.get("error") if isinstance(payload, dict) else None,
            metadata=payload.get("metadata", {}) if isinstance(payload, dict) else {},
        )
        event.processed_at = datetime.now(timezone.utc)


def record_provider_status(
    db: Session,
    *,
    connection: ChannelConnection,
    external_event_id: str,
    provider_message_id: str,
    provider_status: str,
    occurred_at: datetime | None,
    error: str | None,
    metadata: dict,
) -> RecordedProviderStatus:
    existing = db.scalar(
        select(ChannelDeliveryEvent).where(
            ChannelDeliveryEvent.channel_connection_id == connection.id,
            ChannelDeliveryEvent.external_event_id == external_event_id,
        )
    )
    if existing is not None:
        dispatch = db.scalar(
            select(MessageDispatch).where(
                MessageDispatch.workspace_id == connection.workspace_id,
                MessageDispatch.channel_connection_id == connection.id,
                MessageDispatch.provider_message_id == existing.provider_message_id,
            )
        )
        return RecordedProviderStatus(
            event=existing,
            dispatch=dispatch,
            duplicate=True,
        )

    event = ChannelDeliveryEvent(
        workspace_id=connection.workspace_id,
        channel_connection_id=connection.id,
        provider_message_id=provider_message_id,
        external_event_id=external_event_id,
        status=provider_status,
        occurred_at=occurred_at,
        processed_at=None,
        payload_json={
            "error": error,
            "metadata": metadata,
        },
    )
    db.add(event)

    try:
        db.flush()
    except IntegrityError:
        db.rollback()
        existing = db.scalar(
            select(ChannelDeliveryEvent).where(
                ChannelDeliveryEvent.channel_connection_id == connection.id,
                ChannelDeliveryEvent.external_event_id == external_event_id,
            )
        )
        if existing is None:
            raise
        dispatch = db.scalar(
            select(MessageDispatch).where(
                MessageDispatch.workspace_id == connection.workspace_id,
                MessageDispatch.channel_connection_id == connection.id,
                MessageDispatch.provider_message_id == existing.provider_message_id,
            )
        )
        return RecordedProviderStatus(
            event=existing,
            dispatch=dispatch,
            duplicate=True,
        )

    dispatch = db.scalar(
        select(MessageDispatch)
        .where(
            MessageDispatch.workspace_id == connection.workspace_id,
            MessageDispatch.channel_connection_id == connection.id,
            MessageDispatch.provider_message_id == provider_message_id,
        )
        .with_for_update()
    )

    if dispatch is not None:
        message = db.get(Message, dispatch.message_id)
        if message is None:
            raise ChannelError("Provider delivery event references a dispatch with no message.")
        apply_provider_delivery_status(
            dispatch=dispatch,
            message=message,
            provider_status=provider_status,
            occurred_at=occurred_at,
            error=error,
            metadata=metadata,
        )
        event.processed_at = datetime.now(timezone.utc)

    db.commit()
    db.refresh(event)
    if dispatch is not None:
        db.refresh(dispatch)

    return RecordedProviderStatus(
        event=event,
        dispatch=dispatch,
        duplicate=False,
    )


def record_dispatch_result(
    db: Session,
    *,
    connection: ChannelConnection,
    dispatch_id: UUID,
    result_status: str,
    provider_message_id: str | None,
    error: str | None,
    retry_after_seconds: int | None,
    metadata: dict,
) -> MessageDispatch:
    dispatch = db.scalar(
        select(MessageDispatch)
        .where(
            MessageDispatch.id == dispatch_id,
            MessageDispatch.workspace_id == connection.workspace_id,
            MessageDispatch.channel_connection_id == connection.id,
        )
        .with_for_update()
    )
    if dispatch is None:
        raise ChannelError("Dispatch not found for this channel connection.")

    if dispatch.status in {"cancelled", "read"}:
        raise ChannelConflictError(
            f"Dispatch is already terminal with status '{dispatch.status}'."
        )

    message = db.get(Message, dispatch.message_id)
    if message is None:
        raise ChannelError("Dispatch references a missing outbound message.")

    now = datetime.now(timezone.utc)
    if provider_message_id:
        if (
            dispatch.provider_message_id is not None
            and dispatch.provider_message_id != provider_message_id
        ):
            raise ChannelConflictError(
                "Dispatch is already mapped to a different provider message id."
            )
        dispatch.provider_message_id = provider_message_id
        message.external_message_id = provider_message_id

    dispatch.metadata_json = {**(dispatch.metadata_json or {}), **metadata}
    dispatch.locked_at = None

    if result_status in {"sent", "delivered", "read"}:
        apply_provider_delivery_status(
            dispatch=dispatch,
            message=message,
            provider_status=result_status,
            occurred_at=now,
            error=None,
            metadata=metadata,
        )
    elif result_status == "failed":
        dispatch.last_error = (error or "Provider dispatch failed.")[:2000]
        if retry_after_seconds:
            dispatch.status = "queued"
            dispatch.next_attempt_at = now + timedelta(seconds=retry_after_seconds)
            message.delivery_status = "queued"
        else:
            dispatch.status = "failed"
            dispatch.next_attempt_at = None
            message.delivery_status = "failed"
    else:
        raise ChannelError("Unsupported dispatch result status.")

    _reconcile_pending_delivery_events(
        db,
        connection=connection,
        dispatch=dispatch,
        message=message,
    )

    try:
        db.commit()
    except IntegrityError as exc:
        db.rollback()
        raise ChannelConflictError(
            "Provider message id is already mapped to another dispatch."
        ) from exc

    db.refresh(dispatch)
    db.refresh(message)
    return dispatch
