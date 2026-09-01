from __future__ import annotations

from datetime import UTC, datetime, timedelta
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.conversation import Conversation
from app.models.handoff_request import HandoffRequest
from app.models.message import Message
from app.models.message_dispatch import MessageDispatch

OWNER_AI = "ai"
OWNER_HUMAN = "human"


DISPATCH_SEND_LEASE = timedelta(minutes=10)


class OwnershipTransitionBlockedError(RuntimeError):
    """Raised when ownership cannot safely change while a provider send is in flight."""


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
    """Return whether the AI currently owns an open conversation.

    `status=pending` remains a compatibility guard for conversations created
    before first-class ownership existed. New runtime routing should use
    `owner_type` as the source of truth.
    """
    return conversation.owner_type == OWNER_AI and conversation.status == "open"


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
    conversation.owner_type = OWNER_AI
    conversation.assigned_user_id = None
    conversation.status = "closed" if close else "open"
    conversation.closed_at = changed_at if close else None
    conversation.ownership_changed_at = changed_at


def record_customer_inbound(
    conversation: Conversation,
    *,
    now: datetime | None = None,
) -> None:
    conversation.unread_count = max(0, int(conversation.unread_count or 0)) + 1
    conversation.last_message_at = now or _now()


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
