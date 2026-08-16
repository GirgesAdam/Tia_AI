from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.channel_connection import ChannelConnection
from app.models.channel_identity import ChannelIdentity
from app.models.conversation import Conversation
from app.models.message import Message
from app.models.message_dispatch import MessageDispatch
from app.models.patient import Patient
from app.schemas.crm import normalize_email


class OutboundCommunicationError(ValueError):
    pass


@dataclass(frozen=True)
class QueuedEmail:
    connection: ChannelConnection
    identity: ChannelIdentity
    conversation: Conversation
    message: Message
    dispatch: MessageDispatch


def _default_gmail_connection(
    db: Session,
    *,
    workspace_id: UUID,
) -> ChannelConnection:
    rows = list(
        db.scalars(
            select(ChannelConnection)
            .where(
                ChannelConnection.workspace_id == workspace_id,
                ChannelConnection.channel == "email",
                ChannelConnection.provider == "n8n_gmail",
                ChannelConnection.status == "active",
            )
            .order_by(ChannelConnection.created_at)
        )
    )
    if not rows:
        raise OutboundCommunicationError(
            "No active Gmail channel is configured for this workspace."
        )

    defaults = [row for row in rows if bool((row.config_json or {}).get("default"))]
    if len(defaults) == 1:
        return defaults[0]
    if len(rows) == 1:
        return rows[0]
    if len(defaults) > 1:
        raise OutboundCommunicationError(
            "Multiple Gmail channels are marked as default."
        )
    raise OutboundCommunicationError(
        "Multiple Gmail channels are active and none is marked as default."
    )


def _ensure_email_identity(
    db: Session,
    *,
    connection: ChannelConnection,
    patient: Patient,
    email: str,
) -> ChannelIdentity:
    identity = db.scalar(
        select(ChannelIdentity).where(
            ChannelIdentity.workspace_id == connection.workspace_id,
            ChannelIdentity.channel_connection_id == connection.id,
            ChannelIdentity.patient_id == patient.id,
        )
    )
    if identity is not None:
        if identity.external_user_id != email:
            collision = db.scalar(
                select(ChannelIdentity).where(
                    ChannelIdentity.channel_connection_id == connection.id,
                    ChannelIdentity.external_user_id == email,
                    ChannelIdentity.id != identity.id,
                )
            )
            if collision is not None:
                raise OutboundCommunicationError(
                    "The customer's email is already linked to another channel identity."
                )
            identity.external_user_id = email
        identity.email = email
        identity.display_name = (
            f"{patient.first_name or ''} {patient.last_name or ''}".strip()
            or email
        )
        identity.metadata_json = {
            **(identity.metadata_json or {}),
            "source": "patient_profile",
        }
        return identity

    collision = db.scalar(
        select(ChannelIdentity).where(
            ChannelIdentity.channel_connection_id == connection.id,
            ChannelIdentity.external_user_id == email,
        )
    )
    if collision is not None and collision.patient_id != patient.id:
        raise OutboundCommunicationError(
            "The customer's email is already linked to another patient."
        )
    if collision is not None:
        return collision

    identity = ChannelIdentity(
        workspace_id=connection.workspace_id,
        channel_connection_id=connection.id,
        patient_id=patient.id,
        external_user_id=email,
        display_name=(
            f"{patient.first_name or ''} {patient.last_name or ''}".strip()
            or email
        ),
        phone=patient.phone,
        email=email,
        metadata_json={"source": "patient_profile"},
    )
    db.add(identity)
    db.flush()
    return identity


def _ensure_email_conversation(
    db: Session,
    *,
    connection: ChannelConnection,
    patient: Patient,
    email: str,
) -> Conversation:
    external_conversation_id = f"email:{patient.id}"
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
            raise OutboundCommunicationError(
                "Email conversation is already linked to another patient."
            )
        if conversation.status == "closed":
            conversation.status = "open"
            conversation.closed_at = None
        return conversation

    conversation = Conversation(
        workspace_id=connection.workspace_id,
        patient_id=patient.id,
        channel="email",
        channel_connection_id=connection.id,
        external_conversation_id=external_conversation_id,
        status="open",
        subject=None,
        started_at=now,
        last_message_at=None,
    )
    db.add(conversation)
    db.flush()
    return conversation


def queue_patient_email(
    db: Session,
    *,
    workspace_id: UUID,
    patient: Patient,
    subject: str,
    body: str,
    sender_type: str,
    source: str,
    run_id: UUID | None = None,
) -> QueuedEmail:
    """Queue a real Gmail delivery for the current patient's saved email only."""
    subject = " ".join(subject.strip().split())
    body = body.strip()
    if not subject:
        raise OutboundCommunicationError("Email subject cannot be empty.")
    if len(subject) > 200:
        raise OutboundCommunicationError("Email subject is too long.")
    if not body:
        raise OutboundCommunicationError("Email body cannot be empty.")
    if len(body) > 20000:
        raise OutboundCommunicationError("Email body is too long.")

    email = normalize_email(patient.email)
    if not email:
        raise OutboundCommunicationError(
            "The current customer does not have a saved email address."
        )
    if len(email) > 254:
        raise OutboundCommunicationError(
            "The saved email address is too long for provider delivery."
        )

    connection = _default_gmail_connection(db, workspace_id=workspace_id)
    identity = _ensure_email_identity(
        db,
        connection=connection,
        patient=patient,
        email=email,
    )
    conversation = _ensure_email_conversation(
        db,
        connection=connection,
        patient=patient,
        email=email,
    )

    now = datetime.now(timezone.utc)
    metadata = {
        "source": source,
        "email": {
            "subject": subject,
            "recipient": email,
            "sender_account": connection.external_account_id,
        },
    }
    if run_id is not None:
        metadata["agent_run_id"] = str(run_id)

    message = Message(
        workspace_id=workspace_id,
        conversation_id=conversation.id,
        channel_connection_id=connection.id,
        sender_type=sender_type,
        direction="outbound",
        message_type="email",
        content=body,
        delivery_status="queued",
        metadata_json=metadata,
    )
    db.add(message)
    db.flush()

    dispatch = MessageDispatch(
        workspace_id=workspace_id,
        channel_connection_id=connection.id,
        message_id=message.id,
        status="queued",
        attempts=0,
        metadata_json={
            "conversation_id": str(conversation.id),
            "sender_type": sender_type,
            "source": source,
            "transport": "n8n",
            "provider": "gmail",
        },
    )
    db.add(dispatch)
    conversation.subject = subject
    conversation.last_message_at = now
    db.commit()
    db.refresh(identity)
    db.refresh(conversation)
    db.refresh(message)
    db.refresh(dispatch)

    return QueuedEmail(
        connection=connection,
        identity=identity,
        conversation=conversation,
        message=message,
        dispatch=dispatch,
    )
