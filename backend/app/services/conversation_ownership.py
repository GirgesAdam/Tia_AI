from __future__ import annotations

from datetime import UTC, datetime, timedelta
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session, object_session

from app.models.channel_inbound_event import ChannelInboundEvent
from app.models.conversation import Conversation
from app.models.handoff_request import HandoffRequest
from app.models.message import Message
from app.models.message_dispatch import MessageDispatch

OWNER_AI = "ai"
OWNER_HUMAN = "human"


DISPATCH_SEND_LEASE = timedelta(minutes=10)
_AGENT_OWNERSHIP_EPOCH_ATTR = "_tia_agent_ownership_epoch"


class OwnershipTransitionBlockedError(RuntimeError):
    """Raised when ownership cannot safely change while a provider send is in flight."""


def _as_utc(value: datetime) -> datetime:
    if value.tzinfo is None:
        return value.replace(tzinfo=UTC)
    return value.astimezone(UTC)


def _timestamp_not_after(value: datetime, boundary: datetime) -> bool:
    return _as_utc(value) <= _as_utc(boundary)


def _suppress_pre_resume_inbound_events(conversation: Conversation) -> int:
    """Finalize queued customer events from the human-owned period without replying.

    The messages stay in conversation history so the next real customer turn can
    see the full human exchange. Only their old processing triggers are consumed.
    Events already being processed are protected by the ownership-epoch guard in
    `agent_can_reply` when that run reaches its final ownership check.
    """
    if not isinstance(conversation, Conversation):
        return 0
    db = object_session(conversation)
    if db is None:
        return 0

    events = list(
        db.scalars(
            select(ChannelInboundEvent)
            .join(Message, Message.id == ChannelInboundEvent.message_id)
            .where(
                ChannelInboundEvent.workspace_id == conversation.workspace_id,
                Message.workspace_id == conversation.workspace_id,
                Message.conversation_id == conversation.id,
                Message.sender_type == "patient",
                Message.direction == "inbound",
                ChannelInboundEvent.status.in_(("received", "failed")),
            )
            .with_for_update()
        )
    )
    for event in events:
        event.status = "processed"
        event.outbound_message_id = None
        event.last_error = None
    return len(events)


def ai_dispatch_is_sendable(
    *,
    conversation: Conversation,
    message: Message,
    active_handoff: HandoffRequest | None,
) -> bool:
    """Return whether an AI outbound still has authority to reach the provider."""
    if message.sender_type != "ai":
        return True

    metadata = message.metadata_json or {}
    if metadata.get("handoff_ack") is True:
        return (
            conversation.owner_type == OWNER_HUMAN
            and conversation.status == "pending"
            and active_handoff is not None
            and active_handoff.source == "ai"
            and active_handoff.status == "pending"
            and active_handoff.assigned_user_id is None
        )

    # Conversational AI replies are tied to the ownership epoch in which they
    # were created. If a human takeover/resume happened afterwards, the old reply
    # must never become sendable again. Templates/automations do not carry an
    # in-reply-to customer message id and are intentionally unaffected.
    if metadata.get("in_reply_to_message_id"):
        created_at = getattr(message, "created_at", None)
        ownership_changed_at = getattr(conversation, "ownership_changed_at", None)
        if (
            isinstance(created_at, datetime)
            and isinstance(ownership_changed_at, datetime)
            and _timestamp_not_after(created_at, ownership_changed_at)
        ):
            return False

    return agent_can_reply(conversation) and active_handoff is None


def cancel_dispatch_for_ownership(
    dispatch: MessageDispatch,
    message: Message,
    *,
    reason: str,
) -> None:
    """Cancel an outbound row that became invalid after an ownership change."""
    dispatch.status = "cancelled"
    dispatch.last_error = reason[:2000]
    dispatch.next_attempt_at = None
    dispatch.locked_at = None
    dispatch.metadata_json = {
        **(dispatch.metadata_json or {}),
        "cancelled_by_ownership": True,
        "cancel_reason": reason[:500],
    }
    message.delivery_status = "cancelled"
    message.metadata_json = {
        **(message.metadata_json or {}),
        "cancelled_by_ownership": True,
        "cancel_reason": reason[:500],
    }


def _fresh_processing_dispatch(
    dispatch: MessageDispatch,
    *,
    now: datetime,
) -> bool:
    return (
        dispatch.status == "processing"
        and dispatch.locked_at is not None
        and dispatch.locked_at > now - DISPATCH_SEND_LEASE
    )


def quiesce_ai_dispatches_for_human(
    db: Session,
    *,
    conversation: Conversation,
    now: datetime | None = None,
    allow_inflight: bool = False,
) -> int:
    """Cancel queued/stale AI sends before staff can answer.

    Callers must lock the conversation first. A fresh `processing` dispatch is a
    short provider-send lease: staff cannot race it. AI-triggered handoff creation
    may keep that lease alive, but claim/assign/reply must wait for it to finish.
    """
    current = now or _now()
    rows = list(
        db.execute(
            select(MessageDispatch, Message)
            .join(Message, Message.id == MessageDispatch.message_id)
            .where(
                Message.workspace_id == conversation.workspace_id,
                Message.conversation_id == conversation.id,
                Message.sender_type == "ai",
                Message.direction == "outbound",
                MessageDispatch.status.in_(("queued", "processing")),
            )
            .with_for_update()
        )
    )

    cancelled = 0
    for dispatch, message in rows:
        if _fresh_processing_dispatch(dispatch, now=current):
            if allow_inflight:
                continue
            raise OwnershipTransitionBlockedError(
                "An AI reply is already being delivered. Retry after provider delivery completes."
            )
        cancel_dispatch_for_ownership(
            dispatch,
            message,
            reason="Cancelled because the conversation is moving to human ownership.",
        )
        cancelled += 1
    return cancelled


def ensure_staff_outbox_drained_before_ai(
    db: Session,
    *,
    conversation: Conversation,
) -> None:
    """Do not resume AI while a human reply is still queued or being sent."""
    pending = db.scalar(
        select(MessageDispatch.id)
        .join(Message, Message.id == MessageDispatch.message_id)
        .where(
            Message.workspace_id == conversation.workspace_id,
            Message.conversation_id == conversation.id,
            Message.sender_type == "staff",
            Message.direction == "outbound",
            MessageDispatch.status.in_(("queued", "processing")),
        )
        .limit(1)
    )
    if pending is not None:
        raise OwnershipTransitionBlockedError(
            "A staff reply is still waiting for provider delivery. Retry after it is sent."
        )


def _now() -> datetime:
    return datetime.now(UTC)


def agent_can_reply(conversation: Conversation) -> bool:
    """Return whether this AI run still owns a customer-triggered turn.

    Returning a handoff to AI deliberately arms a silent state: the conversation
    remains open, but AI cannot reply until a newer customer inbound updates
    `last_message_at`. The transient ownership epoch also prevents an LLM run that
    started before a takeover from becoming valid again after a fast hand-back.
    """
    if conversation.owner_type != OWNER_AI or conversation.status != "open":
        return False

    ownership_changed_at = getattr(conversation, "ownership_changed_at", None)
    last_message_at = getattr(conversation, "last_message_at", None)
    if (
        isinstance(ownership_changed_at, datetime)
        and isinstance(last_message_at, datetime)
        and _timestamp_not_after(last_message_at, ownership_changed_at)
    ):
        return False

    if not isinstance(ownership_changed_at, datetime):
        return True

    run_epoch = getattr(conversation, _AGENT_OWNERSHIP_EPOCH_ATTR, None)
    if run_epoch is None:
        setattr(conversation, _AGENT_OWNERSHIP_EPOCH_ATTR, ownership_changed_at)
        return True
    if not isinstance(run_epoch, datetime):
        return False
    return _as_utc(run_epoch) == _as_utc(ownership_changed_at)


def transfer_to_human(
    conversation: Conversation,
    *,
    assigned_user_id: UUID | None = None,
    now: datetime | None = None,
) -> None:
    conversation.owner_type = OWNER_HUMAN
    conversation.assigned_user_id = assigned_user_id
    conversation.status = "pending"
    conversation.closed_at = None
    conversation.ownership_changed_at = now or _now()


def return_to_ai(
    conversation: Conversation,
    *,
    close: bool = False,
    now: datetime | None = None,
) -> None:
    changed_at = now or _now()
    resuming_from_human = conversation.owner_type == OWNER_HUMAN and not close
    if resuming_from_human:
        _suppress_pre_resume_inbound_events(conversation)

    conversation.owner_type = OWNER_AI
    conversation.assigned_user_id = None
    conversation.status = "closed" if close else "open"
    conversation.closed_at = changed_at if close else None
    conversation.ownership_changed_at = changed_at
    if resuming_from_human:
        # Do not let old customer activity unlock AI after hand-back. The next
        # real customer inbound will move last_message_at past this resume epoch.
        conversation.last_message_at = changed_at


def record_customer_inbound(
    conversation: Conversation,
    *,
    now: datetime | None = None,
) -> None:
    current = now or _now()
    conversation.unread_count = max(0, int(conversation.unread_count or 0)) + 1
    conversation.last_message_at = current
    ownership_changed_at = getattr(conversation, "ownership_changed_at", None)
    if isinstance(ownership_changed_at, datetime):
        # A genuinely new customer turn starts a fresh run under the current
        # ownership epoch. This is transient per SQLAlchemy session/run.
        setattr(conversation, _AGENT_OWNERSHIP_EPOCH_ATTR, ownership_changed_at)


def record_outbound_activity(
    conversation: Conversation,
    *,
    now: datetime | None = None,
) -> None:
    conversation.last_message_at = now or _now()


def mark_conversation_read(conversation: Conversation) -> None:
    conversation.unread_count = 0


def lock_conversation_ownership(
    db: Session,
    *,
    workspace_id: UUID,
    conversation_id: UUID,
) -> Conversation | None:
    """Reload and lock a conversation before an ownership-sensitive write.

    `populate_existing=True` is deliberate: the same SQLAlchemy session may have
    loaded the Conversation before an LLM call. A staff member can take over
    during that latency, so the final AI write must refresh ownership from the DB.
    """
    stmt = (
        select(Conversation)
        .where(
            Conversation.workspace_id == workspace_id,
            Conversation.id == conversation_id,
        )
        .with_for_update()
        .execution_options(populate_existing=True)
    )
    return db.scalar(stmt)
