from __future__ import annotations

from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import case, select
from sqlalchemy.orm import Session

from app.api.dependencies.security import (
    WorkspaceAccess,
    get_workspace_admin,
    get_workspace_reader,
)
from app.database.session import get_db
from app.models.conversation import Conversation
from app.models.handoff_event import HandoffEvent
from app.models.handoff_request import HandoffRequest
from app.models.message import Message
from app.models.patient import Patient
from app.models.user import User
from app.models.workspace_member import WORKSPACE_ROLE_ADMIN
from app.schemas.inbox import (
    HandoffAssignRequest,
    HandoffCategory,
    HandoffPriority,
    HandoffQueueItem,
    HandoffRead,
    HandoffStatus,
    InboxConversationRead,
    InboxMessageRead,
    InboxPatientRead,
    ResolveHandoffRequest,
    StaffReplyRequest,
    StaffReplyResponse,
)
from app.services.channels import queue_message_dispatch
from app.services.handoffs import (
    HandoffStateError,
    add_staff_reply,
    assign_handoff,
    claim_handoff,
    ensure_active_workspace_user,
    get_active_handoff,
    resolve_handoff,
)

router = APIRouter()


def _not_found(resource: str) -> HTTPException:
    return HTTPException(
        status_code=status.HTTP_404_NOT_FOUND,
        detail=f"{resource} not found in this workspace.",
    )


def _conflict(exc: HandoffStateError) -> HTTPException:
    return HTTPException(
        status_code=status.HTTP_409_CONFLICT,
        detail=str(exc),
    )


def _get_handoff(
    db: Session,
    *,
    workspace_id: UUID,
    handoff_id: UUID,
    for_update: bool = False,
) -> HandoffRequest:
    stmt = select(HandoffRequest).where(
        HandoffRequest.workspace_id == workspace_id,
        HandoffRequest.id == handoff_id,
    )
    if for_update:
        stmt = stmt.with_for_update()
    handoff = db.scalar(stmt)
    if handoff is None:
        raise _not_found("Handoff")
    return handoff


def _get_conversation(
    db: Session,
    *,
    workspace_id: UUID,
    conversation_id: UUID,
    for_update: bool = False,
) -> Conversation:
    stmt = select(Conversation).where(
        Conversation.workspace_id == workspace_id,
        Conversation.id == conversation_id,
    )
    if for_update:
        stmt = stmt.with_for_update()
    conversation = db.scalar(stmt)
    if conversation is None:
        raise _not_found("Conversation")
    return conversation


def _queue_item(
    db: Session,
    handoff: HandoffRequest,
) -> HandoffQueueItem:
    patient = db.scalar(
        select(Patient).where(
            Patient.workspace_id == handoff.workspace_id,
            Patient.id == handoff.patient_id,
        )
    )
    conversation = db.scalar(
        select(Conversation).where(
            Conversation.workspace_id == handoff.workspace_id,
            Conversation.id == handoff.conversation_id,
        )
    )
    assigned_user = None
    if handoff.assigned_user_id:
        assigned_user = db.scalar(select(User).where(User.id == handoff.assigned_user_id))

    if patient is None or conversation is None:
        raise RuntimeError("Handoff references missing workspace data.")

    patient_name = f"{patient.first_name} {patient.last_name or ''}".strip()
    data = HandoffRead.model_validate(handoff).model_dump()
    return HandoffQueueItem(
        **data,
        patient_name=patient_name,
        patient_phone=patient.phone,
        channel=conversation.channel,
        conversation_last_message_at=conversation.last_message_at,
        assigned_user_name=assigned_user.full_name if assigned_user else None,
        assigned_user_email=assigned_user.email if assigned_user else None,
    )


@router.get("/handoffs", response_model=list[HandoffQueueItem])
def list_handoffs(
    access: Annotated[WorkspaceAccess, Depends(get_workspace_reader)],
    db: Annotated[Session, Depends(get_db)],
    handoff_status: Annotated[HandoffStatus | None, Query(alias="status")] = None,
    category: HandoffCategory | None = None,
    priority: HandoffPriority | None = None,
    assigned_to_me: bool = False,
    limit: Annotated[int, Query(ge=1, le=100)] = 50,
    offset: Annotated[int, Query(ge=0)] = 0,
) -> list[HandoffQueueItem]:
    priority_order = case(
        (HandoffRequest.priority == "urgent", 0),
        (HandoffRequest.priority == "high", 1),
        (HandoffRequest.priority == "normal", 2),
        else_=3,
    )
    stmt = select(HandoffRequest).where(
        HandoffRequest.workspace_id == access.workspace.id
    )
    if handoff_status:
        stmt = stmt.where(HandoffRequest.status == handoff_status)
    else:
        stmt = stmt.where(HandoffRequest.status.in_(("pending", "claimed")))
    if category:
        stmt = stmt.where(HandoffRequest.category == category)
    if priority:
        stmt = stmt.where(HandoffRequest.priority == priority)
    if assigned_to_me:
        stmt = stmt.where(HandoffRequest.assigned_user_id == access.user.id)

    stmt = (
        stmt.order_by(priority_order, HandoffRequest.created_at)
        .limit(limit)
        .offset(offset)
    )
    return [_queue_item(db, item) for item in db.scalars(stmt)]


@router.get(
    "/conversations/{conversation_id}",
    response_model=InboxConversationRead,
)
def get_inbox_conversation(
    conversation_id: UUID,
    access: Annotated[WorkspaceAccess, Depends(get_workspace_reader)],
    db: Annotated[Session, Depends(get_db)],
) -> InboxConversationRead:
    conversation = _get_conversation(
        db,
        workspace_id=access.workspace.id,
        conversation_id=conversation_id,
    )
    patient = db.scalar(
        select(Patient).where(
            Patient.workspace_id == access.workspace.id,
            Patient.id == conversation.patient_id,
        )
    )
    if patient is None:
        raise _not_found("Patient")

    handoff = get_active_handoff(
        db,
        workspace_id=access.workspace.id,
        conversation_id=conversation.id,
    )
    handoff_history = list(
        db.scalars(
            select(HandoffRequest)
            .where(
                HandoffRequest.workspace_id == access.workspace.id,
                HandoffRequest.conversation_id == conversation.id,
            )
            .order_by(HandoffRequest.created_at.desc())
            .limit(100)
        )
    )
    messages = list(
        db.scalars(
            select(Message)
            .where(
                Message.workspace_id == access.workspace.id,
                Message.conversation_id == conversation.id,
            )
            .order_by(Message.created_at)
            .limit(500)
        )
    )
    events = list(
        db.scalars(
            select(HandoffEvent)
            .where(
                HandoffEvent.workspace_id == access.workspace.id,
                HandoffEvent.conversation_id == conversation.id,
            )
            .order_by(HandoffEvent.created_at)
            .limit(500)
        )
    )

    return InboxConversationRead(
        id=conversation.id,
        workspace_id=conversation.workspace_id,
        patient_id=conversation.patient_id,
        channel=conversation.channel,
        channel_connection_id=conversation.channel_connection_id,
        status=conversation.status,
        assigned_user_id=conversation.assigned_user_id,
        subject=conversation.subject,
        started_at=conversation.started_at,
        last_message_at=conversation.last_message_at,
        closed_at=conversation.closed_at,
        patient=InboxPatientRead(
            id=patient.id,
            first_name=patient.first_name,
            last_name=patient.last_name,
            phone=patient.phone,
            email=patient.email,
        ),
        active_handoff=HandoffRead.model_validate(handoff) if handoff else None,
        handoff_history=[HandoffRead.model_validate(item) for item in handoff_history],
        messages=[InboxMessageRead.model_validate(message) for message in messages],
        handoff_events=events,
    )


@router.post(
    "/handoffs/{handoff_id}/claim",
    response_model=HandoffRead,
)
def claim_inbox_handoff(
    handoff_id: UUID,
    access: Annotated[WorkspaceAccess, Depends(get_workspace_reader)],
    db: Annotated[Session, Depends(get_db)],
) -> HandoffRequest:
    handoff = _get_handoff(
        db,
        workspace_id=access.workspace.id,
        handoff_id=handoff_id,
        for_update=True,
    )
    conversation = _get_conversation(
        db,
        workspace_id=access.workspace.id,
        conversation_id=handoff.conversation_id,
        for_update=True,
    )
    try:
        return claim_handoff(
            db,
            handoff=handoff,
            conversation=conversation,
            user=access.user,
        )
    except HandoffStateError as exc:
        db.rollback()
        raise _conflict(exc) from exc


@router.post(
    "/handoffs/{handoff_id}/assign",
    response_model=HandoffRead,
)
def assign_inbox_handoff(
    handoff_id: UUID,
    payload: HandoffAssignRequest,
    access: Annotated[WorkspaceAccess, Depends(get_workspace_admin)],
    db: Annotated[Session, Depends(get_db)],
) -> HandoffRequest:
    handoff = _get_handoff(
        db,
        workspace_id=access.workspace.id,
        handoff_id=handoff_id,
        for_update=True,
    )
    conversation = _get_conversation(
        db,
        workspace_id=access.workspace.id,
        conversation_id=handoff.conversation_id,
        for_update=True,
    )
    try:
        target_user = ensure_active_workspace_user(
            db,
            workspace_id=access.workspace.id,
            user_id=payload.user_id,
        )
        return assign_handoff(
            db,
            handoff=handoff,
            conversation=conversation,
            target_user=target_user,
            actor_user=access.user,
        )
    except HandoffStateError as exc:
        db.rollback()
        raise _conflict(exc) from exc


@router.post(
    "/conversations/{conversation_id}/messages",
    response_model=StaffReplyResponse,
    status_code=status.HTTP_201_CREATED,
)
def send_staff_reply(
    conversation_id: UUID,
    payload: StaffReplyRequest,
    access: Annotated[WorkspaceAccess, Depends(get_workspace_reader)],
    db: Annotated[Session, Depends(get_db)],
) -> StaffReplyResponse:
    conversation = _get_conversation(
        db,
        workspace_id=access.workspace.id,
        conversation_id=conversation_id,
        for_update=True,
    )
    handoff = get_active_handoff(
        db,
        workspace_id=access.workspace.id,
        conversation_id=conversation.id,
        for_update=True,
    )
    if handoff is None:
        db.rollback()
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="This conversation does not have an active handoff.",
        )

    if handoff.assigned_user_id != access.user.id:
        db.rollback()
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Claim this handoff before replying to the customer.",
        )

    try:
        message = add_staff_reply(
            db,
            handoff=handoff,
            conversation=conversation,
            user=access.user,
            content=payload.content,
        )
    except HandoffStateError as exc:
        db.rollback()
        raise _conflict(exc) from exc

    dispatch = queue_message_dispatch(
        db,
        message=message,
        conversation=conversation,
    )

    return StaffReplyResponse(
        message=InboxMessageRead.model_validate(message),
        dispatch_required=dispatch is not None,
        dispatch_id=dispatch.id if dispatch else None,
    )


@router.post(
    "/handoffs/{handoff_id}/resolve",
    response_model=HandoffRead,
)
def resolve_inbox_handoff(
    handoff_id: UUID,
    payload: ResolveHandoffRequest,
    access: Annotated[WorkspaceAccess, Depends(get_workspace_reader)],
    db: Annotated[Session, Depends(get_db)],
) -> HandoffRequest:
    handoff = _get_handoff(
        db,
        workspace_id=access.workspace.id,
        handoff_id=handoff_id,
        for_update=True,
    )
    conversation = _get_conversation(
        db,
        workspace_id=access.workspace.id,
        conversation_id=handoff.conversation_id,
        for_update=True,
    )

    is_admin = access.membership.role == WORKSPACE_ROLE_ADMIN
    if not is_admin and handoff.assigned_user_id != access.user.id:
        db.rollback()
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Claim this handoff before resolving it.",
        )

    try:
        return resolve_handoff(
            db,
            handoff=handoff,
            conversation=conversation,
            actor_user=access.user,
            resolution_note=payload.resolution_note,
            conversation_status_after=payload.conversation_status_after,
        )
    except HandoffStateError as exc:
        db.rollback()
        raise _conflict(exc) from exc
