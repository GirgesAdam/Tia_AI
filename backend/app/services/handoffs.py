from __future__ import annotations

from datetime import UTC, datetime
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.conversation import Conversation
from app.models.handoff_event import HandoffEvent
from app.models.handoff_request import (
    HANDOFF_CATEGORIES,
    HANDOFF_PRIORITIES,
    HANDOFF_SOURCES,
    HandoffRequest,
)
from app.models.message import Message
from app.models.patient import Patient
from app.models.user import User
from app.models.workspace_member import WorkspaceMember
from app.services.activity import record_activity_event
from app.services.conversation_ownership import (
    OWNER_AI,
    OwnershipTransitionBlockedError,
    ensure_staff_outbox_drained_before_ai,
    lock_conversation_ownership,
    mark_conversation_read,
    quiesce_ai_dispatches_for_human,
    return_to_ai,
    transfer_to_human,
)
from app.services.handoff_intelligence import merge_handoff_context


class HandoffStateError(ValueError):
    pass


_PRIORITY_RANK = {
    "low": 0,
    "normal": 1,
    "high": 2,
    "urgent": 3,
}


def _normalize_choice(value: str, allowed: tuple[str, ...], fallback: str) -> str:
    normalized = value.strip().lower()
    return normalized if normalized in allowed else fallback


def _quiesce_ai_before_staff(
    db: Session,
    *,
    conversation: Conversation,
    allow_inflight: bool = False,
) -> None:
    try:
        quiesce_ai_dispatches_for_human(
            db,
            conversation=conversation,
            allow_inflight=allow_inflight,
        )
    except OwnershipTransitionBlockedError as exc:
        raise HandoffStateError(str(exc)) from exc


def add_handoff_event(
    db: Session,
    *,
    handoff: HandoffRequest,
    event_type: str,
    actor_type: str,
    actor_user_id: UUID | None = None,
    metadata: dict | None = None,
) -> HandoffEvent:
    event = HandoffEvent(
        workspace_id=handoff.workspace_id,
        handoff_request_id=handoff.id,
        conversation_id=handoff.conversation_id,
        event_type=event_type,
        actor_type=actor_type,
        actor_user_id=actor_user_id,
        metadata_json=metadata or {},
    )
    db.add(event)
    return event


def get_active_handoff(
    db: Session,
    *,
    workspace_id: UUID,
    conversation_id: UUID,
    for_update: bool = False,
) -> HandoffRequest | None:
    stmt = select(HandoffRequest).where(
        HandoffRequest.workspace_id == workspace_id,
        HandoffRequest.conversation_id == conversation_id,
        HandoffRequest.status.in_(("pending", "claimed")),
    )
    if for_update:
        stmt = stmt.with_for_update().execution_options(populate_existing=True)
    return db.scalar(stmt)


def create_handoff(
    db: Session,
    *,
    workspace_id: UUID,
    conversation: Conversation,
    patient: Patient,
    reason: str,
    category: str = "other",
    priority: str = "normal",
    source: str = "ai",
    created_by_user_id: UUID | None = None,
    handoff_context: dict | None = None,
    commit: bool = True,
) -> HandoffRequest:
    if conversation.workspace_id != workspace_id or patient.workspace_id != workspace_id:
        raise HandoffStateError("Handoff workspace does not match the conversation and patient.")
    if conversation.patient_id != patient.id:
        raise HandoffStateError("Handoff patient does not match the conversation patient.")

    reason = reason.strip() or "human_handoff_requested"
    category = _normalize_choice(category, HANDOFF_CATEGORIES, "other")
    priority = _normalize_choice(priority, HANDOFF_PRIORITIES, "normal")
    source = source.strip().lower()
    if source not in HANDOFF_SOURCES:
        raise HandoffStateError("Invalid handoff source.")

    # Serialize creation/reuse on the canonical conversation row. The partial
    # unique index remains the database backstop, while this lock prevents two
    # concurrent escalations from racing to create separate active handoffs.
    locked_conversation = lock_conversation_ownership(
        db,
        workspace_id=workspace_id,
        conversation_id=conversation.id,
    )
    if locked_conversation is None:
        raise HandoffStateError("Conversation no longer exists in this workspace.")
    conversation = locked_conversation

    # A manual ownership change must not overtake a queued AI reply. AI-created
    # handoffs may coexist with a reply that was already claimed by the provider,
    # but staff claim/reply remains blocked until that send lease finishes.
    if conversation.owner_type == OWNER_AI:
        _quiesce_ai_before_staff(
            db,
            conversation=conversation,
            allow_inflight=source == "ai",
        )

    existing = get_active_handoff(
        db,
        workspace_id=workspace_id,
        conversation_id=conversation.id,
        for_update=True,
    )

    if existing is not None:
        previous_category = existing.category
        previous_priority = existing.priority
        previous_reason = existing.reason
        previous_context = getattr(existing, "context_json", {}) or {}

        if existing.category == "other" and category != "other":
            existing.category = category
        if _PRIORITY_RANK[priority] > _PRIORITY_RANK[existing.priority]:
            existing.priority = priority
        if reason and reason not in existing.reason:
            existing.reason = f"{existing.reason}\n{reason}"[:4000]
        existing.context_json = merge_handoff_context(previous_context, handoff_context)

        changed = (
            existing.category != previous_category
            or existing.priority != previous_priority
            or existing.reason != previous_reason
            or existing.context_json != previous_context
        )
        if changed:
            event_actor_type = (
                "staff" if created_by_user_id else ("ai" if source == "ai" else "system")
            )
            add_handoff_event(
                db,
                handoff=existing,
                event_type="escalated",
                actor_type=event_actor_type,
                actor_user_id=created_by_user_id,
                metadata={
                    "previous_category": previous_category,
                    "category": existing.category,
                    "previous_priority": previous_priority,
                    "priority": existing.priority,
                    "context": existing.context_json,
                },
            )
            record_activity_event(
                db,
                workspace_id=workspace_id,
                actor_type=event_actor_type,
                actor_user_id=created_by_user_id,
                action="handoff.escalated",
                entity_type="handoff",
                entity_id=existing.id,
                summary="Human handoff escalated",
                metadata={
                    "conversation_id": conversation.id,
                    "category": existing.category,
                    "priority": existing.priority,
                },
            )
        transfer_to_human(
            conversation,
            assigned_user_id=existing.assigned_user_id,
        )
        if commit:
            db.commit()
            db.refresh(existing)
        return existing

    handoff = HandoffRequest(
        workspace_id=workspace_id,
        conversation_id=conversation.id,
        patient_id=patient.id,
        status="pending",
        category=category,
        priority=priority,
        source=source,
        reason=reason,
        context_json=merge_handoff_context({}, handoff_context),
        created_by_user_id=created_by_user_id,
    )
    transfer_to_human(conversation)
    db.add(handoff)
    db.flush()
    event_actor_type = "staff" if created_by_user_id else ("ai" if source == "ai" else "system")
    add_handoff_event(
        db,
        handoff=handoff,
        event_type="created",
        actor_type=event_actor_type,
        actor_user_id=created_by_user_id,
        metadata={
            "category": category,
            "priority": priority,
            "source": source,
            "reason": reason,
            "context": handoff.context_json,
        },
    )
    record_activity_event(
        db,
        workspace_id=workspace_id,
        actor_type=event_actor_type,
        actor_user_id=created_by_user_id,
        action="handoff.created",
        entity_type="handoff",
        entity_id=handoff.id,
        summary="Human handoff created",
        metadata={
            "conversation_id": conversation.id,
            "category": category,
            "priority": priority,
            "source": source,
        },
    )

    if commit:
        db.commit()
        db.refresh(handoff)
    return handoff




def _ensure_handoff_context(
    *,
    handoff: HandoffRequest,
    conversation: Conversation,
) -> None:
    if (
        handoff.workspace_id != conversation.workspace_id
        or handoff.conversation_id != conversation.id
    ):
        raise HandoffStateError("Handoff does not belong to this conversation.")


def claim_handoff(
    db: Session,
    *,
    handoff: HandoffRequest,
    conversation: Conversation,
    user: User,
    commit: bool = True,
) -> HandoffRequest:
    _ensure_handoff_context(handoff=handoff, conversation=conversation)
    if handoff.status == "resolved":
        raise HandoffStateError("This handoff is already resolved.")
    if handoff.assigned_user_id and handoff.assigned_user_id != user.id:
        raise HandoffStateError("This handoff is already claimed by another team member.")

    _quiesce_ai_before_staff(db, conversation=conversation)

    now = datetime.now(UTC)
    first_claim = handoff.assigned_user_id is None
    handoff.assigned_user_id = user.id
    handoff.status = "claimed"
    handoff.claimed_at = handoff.claimed_at or now
    transfer_to_human(
        conversation,
        assigned_user_id=user.id,
        now=now,
    )
    mark_conversation_read(conversation)

    if first_claim:
        add_handoff_event(
            db,
            handoff=handoff,
            event_type="claimed",
            actor_type="staff",
            actor_user_id=user.id,
        )
        record_activity_event(
            db,
            workspace_id=handoff.workspace_id,
            actor_type="staff",
            actor_user_id=user.id,
            action="handoff.claimed",
            entity_type="handoff",
            entity_id=handoff.id,
            summary="Human handoff claimed",
            metadata={"conversation_id": conversation.id},
        )

    if commit:
        db.commit()
        db.refresh(handoff)
    return handoff


def assign_handoff(
    db: Session,
    *,
    handoff: HandoffRequest,
    conversation: Conversation,
    target_user: User,
    actor_user: User,
    commit: bool = True,
) -> HandoffRequest:
    _ensure_handoff_context(handoff=handoff, conversation=conversation)
    if handoff.status == "resolved":
        raise HandoffStateError("This handoff is already resolved.")

    _quiesce_ai_before_staff(db, conversation=conversation)

    previous_user_id = handoff.assigned_user_id
    now = datetime.now(UTC)
    handoff.assigned_user_id = target_user.id
    handoff.status = "claimed"
    handoff.claimed_at = handoff.claimed_at or now
    transfer_to_human(
        conversation,
        assigned_user_id=target_user.id,
        now=now,
    )

    add_handoff_event(
        db,
        handoff=handoff,
        event_type="assigned",
        actor_type="staff",
        actor_user_id=actor_user.id,
        metadata={
            "previous_user_id": str(previous_user_id) if previous_user_id else None,
            "assigned_user_id": str(target_user.id),
        },
    )
    record_activity_event(
        db,
        workspace_id=handoff.workspace_id,
        actor_type="staff",
        actor_user_id=actor_user.id,
        action="handoff.assigned",
        entity_type="handoff",
        entity_id=handoff.id,
        summary="Human handoff assigned",
        metadata={
            "conversation_id": conversation.id,
            "previous_user_id": previous_user_id,
            "assigned_user_id": target_user.id,
        },
    )
    if commit:
        db.commit()
        db.refresh(handoff)
    return handoff


def ensure_active_workspace_user(
    db: Session,
    *,
    workspace_id: UUID,
    user_id: UUID,
) -> User:
    user = db.scalar(
        select(User)
        .join(WorkspaceMember, WorkspaceMember.user_id == User.id)
        .where(
            WorkspaceMember.workspace_id == workspace_id,
            WorkspaceMember.user_id == user_id,
            WorkspaceMember.is_active.is_(True),
            User.is_active.is_(True),
        )
    )
    if user is None:
        raise HandoffStateError("Assigned user is not an active member of this workspace.")
    return user


def add_staff_reply(
    db: Session,
    *,
    handoff: HandoffRequest,
    conversation: Conversation,
    user: User,
    content: str,
    commit: bool = True,
) -> Message:
    _ensure_handoff_context(handoff=handoff, conversation=conversation)
    if handoff.status == "resolved":
        raise HandoffStateError("Resolve state cannot receive a staff reply.")
    if handoff.assigned_user_id != user.id:
        raise HandoffStateError("Claim this handoff before replying to the customer.")
    if conversation.owner_type != "human":
        raise HandoffStateError("This conversation is not currently owned by a team member.")
    content = content.strip()
    if not content:
        raise HandoffStateError("Message cannot be empty.")

    _quiesce_ai_before_staff(db, conversation=conversation)
    mark_conversation_read(conversation)
    message = Message(
        workspace_id=handoff.workspace_id,
        conversation_id=conversation.id,
        channel_connection_id=conversation.channel_connection_id,
        sender_type="staff",
        direction="outbound",
        message_type="text",
        content=content,
        delivery_status="queued",
        sent_by_user_id=user.id,
        metadata_json={
            "source": "team_inbox",
            "dispatch_required": True,
            "handoff_request_id": str(handoff.id),
        },
    )
    conversation.last_message_at = datetime.now(UTC)
    db.add(message)
    db.flush()
    add_handoff_event(
        db,
        handoff=handoff,
        event_type="staff_replied",
        actor_type="staff",
        actor_user_id=user.id,
        metadata={
            "message_id": str(message.id),
            "delivery_status": "queued",
        },
    )
    record_activity_event(
        db,
        workspace_id=handoff.workspace_id,
        actor_type="staff",
        actor_user_id=user.id,
        action="handoff.staff_replied",
        entity_type="handoff",
        entity_id=handoff.id,
        summary="Staff replied in Team Inbox",
        metadata={
            "conversation_id": conversation.id,
            "delivery_status": "queued",
        },
    )
    if commit:
        db.commit()
        db.refresh(message)
    return message


def resolve_handoff(
    db: Session,
    *,
    handoff: HandoffRequest,
    conversation: Conversation,
    actor_user: User,
    resolution_note: str | None,
    conversation_status_after: str = "open",
) -> HandoffRequest:
    _ensure_handoff_context(handoff=handoff, conversation=conversation)
    if handoff.status == "resolved":
        return handoff
    if conversation_status_after not in {"open", "closed"}:
        raise HandoffStateError("conversation_status_after must be open or closed.")

    if conversation_status_after == "open":
        try:
            ensure_staff_outbox_drained_before_ai(db, conversation=conversation)
        except OwnershipTransitionBlockedError as exc:
            raise HandoffStateError(str(exc)) from exc

    now = datetime.now(UTC)
    handoff.status = "resolved"
    handoff.resolved_at = now
    handoff.resolved_by_user_id = actor_user.id
    handoff.resolution_note = resolution_note.strip() if resolution_note else None

    return_to_ai(
        conversation,
        close=conversation_status_after == "closed",
        now=now,
    )

    add_handoff_event(
        db,
        handoff=handoff,
        event_type="resolved",
        actor_type="staff",
        actor_user_id=actor_user.id,
        metadata={
            "resolution_note": handoff.resolution_note,
            "conversation_status_after": conversation_status_after,
        },
    )
    record_activity_event(
        db,
        workspace_id=handoff.workspace_id,
        actor_type="staff",
        actor_user_id=actor_user.id,
        action="handoff.resolved",
        entity_type="handoff",
        entity_id=handoff.id,
        summary="Human handoff resolved",
        metadata={
            "conversation_id": conversation.id,
            "conversation_status_after": conversation_status_after,
        },
    )
    db.commit()
    db.refresh(handoff)
    return handoff
