from __future__ import annotations

from datetime import datetime, timezone
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.conversation import Conversation
from app.models.handoff_event import HandoffEvent
from app.models.handoff_request import (
    HANDOFF_CATEGORIES,
    HANDOFF_PRIORITIES,
    HandoffRequest,
)
from app.models.message import Message
from app.models.patient import Patient
from app.models.user import User
from app.models.workspace_member import WorkspaceMember


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
        stmt = stmt.with_for_update()
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
    commit: bool = True,
) -> HandoffRequest:
    reason = reason.strip() or "human_handoff_requested"
    category = _normalize_choice(category, HANDOFF_CATEGORIES, "other")
    priority = _normalize_choice(priority, HANDOFF_PRIORITIES, "normal")

    existing = get_active_handoff(
        db,
        workspace_id=workspace_id,
        conversation_id=conversation.id,
        for_update=True,
    )

    if existing is not None:
        if existing.category == "other" and category != "other":
            existing.category = category
        if _PRIORITY_RANK[priority] > _PRIORITY_RANK[existing.priority]:
            existing.priority = priority
        if reason and reason not in existing.reason:
            existing.reason = f"{existing.reason}\n{reason}"[:4000]
        conversation.status = "pending"
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
        created_by_user_id=created_by_user_id,
    )
    conversation.status = "pending"
    conversation.closed_at = None
    db.add(handoff)
    db.flush()
    add_handoff_event(
        db,
        handoff=handoff,
        event_type="created",
        actor_type="staff" if created_by_user_id else ("ai" if source == "ai" else "system"),
        actor_user_id=created_by_user_id,
        metadata={
            "category": category,
            "priority": priority,
            "source": source,
            "reason": reason,
        },
    )

    if commit:
        db.commit()
        db.refresh(handoff)
    return handoff


def claim_handoff(
    db: Session,
    *,
    handoff: HandoffRequest,
    conversation: Conversation,
    user: User,
) -> HandoffRequest:
    if handoff.status == "resolved":
        raise HandoffStateError("This handoff is already resolved.")
    if handoff.assigned_user_id and handoff.assigned_user_id != user.id:
        raise HandoffStateError("This handoff is already claimed by another team member.")

    now = datetime.now(timezone.utc)
    first_claim = handoff.assigned_user_id is None
    handoff.assigned_user_id = user.id
    handoff.status = "claimed"
    handoff.claimed_at = handoff.claimed_at or now
    conversation.assigned_user_id = user.id
    conversation.status = "pending"
    conversation.closed_at = None

    if first_claim:
        add_handoff_event(
            db,
            handoff=handoff,
            event_type="claimed",
            actor_type="staff",
            actor_user_id=user.id,
        )

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
) -> HandoffRequest:
    if handoff.status == "resolved":
        raise HandoffStateError("This handoff is already resolved.")

    previous_user_id = handoff.assigned_user_id
    now = datetime.now(timezone.utc)
    handoff.assigned_user_id = target_user.id
    handoff.status = "claimed"
    handoff.claimed_at = handoff.claimed_at or now
    conversation.assigned_user_id = target_user.id
    conversation.status = "pending"
    conversation.closed_at = None

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
) -> Message:
    if handoff.status == "resolved":
        raise HandoffStateError("Resolve state cannot receive a staff reply.")
    if handoff.assigned_user_id != user.id:
        raise HandoffStateError("Claim this handoff before replying to the customer.")

    message = Message(
        workspace_id=handoff.workspace_id,
        conversation_id=conversation.id,
        channel_connection_id=conversation.channel_connection_id,
        sender_type="staff",
        direction="outbound",
        message_type="text",
        content=content.strip(),
        delivery_status="queued",
        sent_by_user_id=user.id,
        metadata_json={
            "source": "team_inbox",
            "dispatch_required": True,
            "handoff_request_id": str(handoff.id),
        },
    )
    conversation.last_message_at = datetime.now(timezone.utc)
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
    if handoff.status == "resolved":
        return handoff
    if conversation_status_after not in {"open", "closed"}:
        raise HandoffStateError("conversation_status_after must be open or closed.")

    now = datetime.now(timezone.utc)
    handoff.status = "resolved"
    handoff.resolved_at = now
    handoff.resolved_by_user_id = actor_user.id
    handoff.resolution_note = resolution_note.strip() if resolution_note else None

    conversation.assigned_user_id = None
    conversation.status = conversation_status_after
    conversation.closed_at = now if conversation_status_after == "closed" else None

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
    db.commit()
    db.refresh(handoff)
    return handoff
