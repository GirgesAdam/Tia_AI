from __future__ import annotations

from datetime import datetime, timezone
from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, Response, status
from sqlalchemy import or_, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.api.dependencies.security import WorkspaceAccess, get_workspace_reader
from app.database.session import get_db
from app.models.branch import Branch
from app.models.conversation import Conversation
from app.models.lead import Lead
from app.models.message import Message
from app.models.patient import Patient
from app.models.patient_note import PatientNote
from app.models.patient_tag import PatientTag, PatientTagAssignment
from app.models.service import Service
from app.models.workspace_member import WorkspaceMember
from app.schemas.crm import (
    ConversationChannel,
    ConversationCreate,
    ConversationRead,
    ConversationStatus,
    ConversationUpdate,
    LeadCreate,
    LeadRead,
    LeadStatus,
    LeadUpdate,
    MessageCreate,
    MessageRead,
    PatientCreate,
    PatientNoteCreate,
    PatientNoteRead,
    PatientRead,
    PatientSource,
    PatientStatus,
    PatientTagCreate,
    PatientTagRead,
    PatientUpdate,
    normalize_phone,
)

router = APIRouter()


def not_found(entity: str) -> HTTPException:
    return HTTPException(
        status_code=status.HTTP_404_NOT_FOUND,
        detail=f"{entity} not found.",
    )


def commit_or_conflict(db: Session, detail: str) -> None:
    try:
        db.commit()
    except IntegrityError as exc:
        db.rollback()
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=detail,
        ) from exc


def get_patient_or_404(db: Session, workspace_id: UUID, patient_id: UUID) -> Patient:
    patient = db.scalar(
        select(Patient).where(
            Patient.id == patient_id,
            Patient.workspace_id == workspace_id,
        )
    )
    if patient is None:
        raise not_found("Patient")
    return patient


def ensure_branch(db: Session, workspace_id: UUID, branch_id: UUID | None) -> None:
    if branch_id is None:
        return
    branch = db.scalar(
        select(Branch.id).where(
            Branch.id == branch_id,
            Branch.workspace_id == workspace_id,
            Branch.is_active.is_(True),
        )
    )
    if branch is None:
        raise not_found("Preferred branch")


def ensure_service(db: Session, workspace_id: UUID, service_id: UUID | None) -> None:
    if service_id is None:
        return
    service = db.scalar(
        select(Service.id).where(
            Service.id == service_id,
            Service.workspace_id == workspace_id,
            Service.is_active.is_(True),
        )
    )
    if service is None:
        raise not_found("Service")


def ensure_assignable_user(db: Session, workspace_id: UUID, user_id: UUID | None) -> None:
    if user_id is None:
        return
    membership = db.scalar(
        select(WorkspaceMember.id).where(
            WorkspaceMember.workspace_id == workspace_id,
            WorkspaceMember.user_id == user_id,
            WorkspaceMember.is_active.is_(True),
        )
    )
    if membership is None:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="Assigned user is not an active member of this workspace.",
        )


def apply_patient_contact_fields(patient: Patient, phone: str | None, email: str | None) -> None:
    display_phone, normalized_phone = normalize_phone(phone)
    patient.phone = display_phone
    patient.phone_normalized = normalized_phone
    patient.email = email


@router.post("/patients", response_model=PatientRead, status_code=status.HTTP_201_CREATED)
def create_patient(
    payload: PatientCreate,
    access: Annotated[WorkspaceAccess, Depends(get_workspace_reader)],
    db: Annotated[Session, Depends(get_db)],
) -> Patient:
    ensure_branch(db, access.workspace.id, payload.preferred_branch_id)
    data = payload.model_dump(exclude={"phone", "email", "marketing_consent"})
    patient = Patient(
        workspace_id=access.workspace.id,
        marketing_consent=payload.marketing_consent,
        **data,
    )
    apply_patient_contact_fields(patient, payload.phone, payload.email)
    if payload.marketing_consent:
        patient.marketing_consent_at = datetime.now(timezone.utc)
    db.add(patient)
    commit_or_conflict(db, "A patient with this phone already exists in this workspace.")
    db.refresh(patient)
    return patient


@router.get("/patients", response_model=list[PatientRead])
def list_patients(
    access: Annotated[WorkspaceAccess, Depends(get_workspace_reader)],
    db: Annotated[Session, Depends(get_db)],
    q: Annotated[str | None, Query(max_length=200)] = None,
    patient_status: Annotated[PatientStatus | None, Query(alias="status")] = None,
    source: PatientSource | None = None,
    limit: Annotated[int, Query(ge=1, le=100)] = 50,
    offset: Annotated[int, Query(ge=0)] = 0,
) -> list[Patient]:
    stmt = select(Patient).where(Patient.workspace_id == access.workspace.id)
    if patient_status:
        stmt = stmt.where(Patient.status == patient_status)
    if source:
        stmt = stmt.where(Patient.source == source)
    if q:
        term = f"%{q.strip()}%"
        stmt = stmt.where(
            or_(
                Patient.first_name.ilike(term),
                Patient.last_name.ilike(term),
                Patient.phone.ilike(term),
                Patient.email.ilike(term),
            )
        )
    stmt = stmt.order_by(Patient.created_at.desc()).limit(limit).offset(offset)
    return list(db.scalars(stmt))


@router.get("/patients/{patient_id}", response_model=PatientRead)
def get_patient(
    patient_id: UUID,
    access: Annotated[WorkspaceAccess, Depends(get_workspace_reader)],
    db: Annotated[Session, Depends(get_db)],
) -> Patient:
    return get_patient_or_404(db, access.workspace.id, patient_id)


@router.patch("/patients/{patient_id}", response_model=PatientRead)
def update_patient(
    patient_id: UUID,
    payload: PatientUpdate,
    access: Annotated[WorkspaceAccess, Depends(get_workspace_reader)],
    db: Annotated[Session, Depends(get_db)],
) -> Patient:
    patient = get_patient_or_404(db, access.workspace.id, patient_id)
    updates = payload.model_dump(exclude_unset=True)
    required_fields = {"first_name", "preferred_language", "source", "status", "marketing_consent"}
    if any(field in updates and updates[field] is None for field in required_fields):
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="Required patient fields cannot be null.",
        )

    if "preferred_branch_id" in updates:
        ensure_branch(db, access.workspace.id, updates["preferred_branch_id"])
    if "phone" in updates:
        display_phone, normalized_phone = normalize_phone(updates.pop("phone"))
        patient.phone = display_phone
        patient.phone_normalized = normalized_phone
    if "email" in updates:
        patient.email = updates.pop("email")
    if "marketing_consent" in updates:
        new_consent = updates["marketing_consent"]
        if new_consent and not patient.marketing_consent:
            patient.marketing_consent_at = datetime.now(timezone.utc)
        elif not new_consent:
            patient.marketing_consent_at = None

    for key, value in updates.items():
        setattr(patient, key, value)

    commit_or_conflict(db, "A patient with this phone already exists in this workspace.")
    db.refresh(patient)
    return patient


@router.post(
    "/patients/{patient_id}/notes",
    response_model=PatientNoteRead,
    status_code=status.HTTP_201_CREATED,
)
def create_patient_note(
    patient_id: UUID,
    payload: PatientNoteCreate,
    access: Annotated[WorkspaceAccess, Depends(get_workspace_reader)],
    db: Annotated[Session, Depends(get_db)],
) -> PatientNote:
    get_patient_or_404(db, access.workspace.id, patient_id)
    note = PatientNote(
        workspace_id=access.workspace.id,
        patient_id=patient_id,
        author_user_id=access.user.id,
        **payload.model_dump(),
    )
    db.add(note)
    db.commit()
    db.refresh(note)
    return note


@router.get("/patients/{patient_id}/notes", response_model=list[PatientNoteRead])
def list_patient_notes(
    patient_id: UUID,
    access: Annotated[WorkspaceAccess, Depends(get_workspace_reader)],
    db: Annotated[Session, Depends(get_db)],
) -> list[PatientNote]:
    get_patient_or_404(db, access.workspace.id, patient_id)
    return list(
        db.scalars(
            select(PatientNote)
            .where(
                PatientNote.workspace_id == access.workspace.id,
                PatientNote.patient_id == patient_id,
            )
            .order_by(PatientNote.is_pinned.desc(), PatientNote.created_at.desc())
        )
    )


@router.post("/tags", response_model=PatientTagRead, status_code=status.HTTP_201_CREATED)
def create_tag(
    payload: PatientTagCreate,
    access: Annotated[WorkspaceAccess, Depends(get_workspace_reader)],
    db: Annotated[Session, Depends(get_db)],
) -> PatientTag:
    tag = PatientTag(
        workspace_id=access.workspace.id,
        name=payload.name,
        normalized_name=payload.name.casefold(),
        color=payload.color,
    )
    db.add(tag)
    commit_or_conflict(db, "A tag with this name already exists in this workspace.")
    db.refresh(tag)
    return tag


@router.get("/tags", response_model=list[PatientTagRead])
def list_tags(
    access: Annotated[WorkspaceAccess, Depends(get_workspace_reader)],
    db: Annotated[Session, Depends(get_db)],
) -> list[PatientTag]:
    return list(
        db.scalars(
            select(PatientTag)
            .where(
                PatientTag.workspace_id == access.workspace.id,
                PatientTag.is_active.is_(True),
            )
            .order_by(PatientTag.name)
        )
    )


@router.put(
    "/patients/{patient_id}/tags/{tag_id}",
    response_model=PatientTagRead,
)
def assign_tag_to_patient(
    patient_id: UUID,
    tag_id: UUID,
    access: Annotated[WorkspaceAccess, Depends(get_workspace_reader)],
    db: Annotated[Session, Depends(get_db)],
) -> PatientTag:
    get_patient_or_404(db, access.workspace.id, patient_id)
    tag = db.scalar(
        select(PatientTag).where(
            PatientTag.id == tag_id,
            PatientTag.workspace_id == access.workspace.id,
            PatientTag.is_active.is_(True),
        )
    )
    if tag is None:
        raise not_found("Tag")

    assignment = db.scalar(
        select(PatientTagAssignment).where(
            PatientTagAssignment.workspace_id == access.workspace.id,
            PatientTagAssignment.patient_id == patient_id,
            PatientTagAssignment.tag_id == tag_id,
        )
    )
    if assignment is None:
        db.add(
            PatientTagAssignment(
                workspace_id=access.workspace.id,
                patient_id=patient_id,
                tag_id=tag_id,
                created_by_user_id=access.user.id,
            )
        )
        db.commit()
    return tag


@router.get("/patients/{patient_id}/tags", response_model=list[PatientTagRead])
def list_patient_tags(
    patient_id: UUID,
    access: Annotated[WorkspaceAccess, Depends(get_workspace_reader)],
    db: Annotated[Session, Depends(get_db)],
) -> list[PatientTag]:
    get_patient_or_404(db, access.workspace.id, patient_id)
    stmt = (
        select(PatientTag)
        .join(
            PatientTagAssignment,
            PatientTagAssignment.tag_id == PatientTag.id,
        )
        .where(
            PatientTagAssignment.workspace_id == access.workspace.id,
            PatientTagAssignment.patient_id == patient_id,
            PatientTag.workspace_id == access.workspace.id,
        )
        .order_by(PatientTag.name)
    )
    return list(db.scalars(stmt))


@router.delete(
    "/patients/{patient_id}/tags/{tag_id}",
    status_code=status.HTTP_204_NO_CONTENT,
)
def remove_tag_from_patient(
    patient_id: UUID,
    tag_id: UUID,
    access: Annotated[WorkspaceAccess, Depends(get_workspace_reader)],
    db: Annotated[Session, Depends(get_db)],
) -> Response:
    assignment = db.scalar(
        select(PatientTagAssignment).where(
            PatientTagAssignment.workspace_id == access.workspace.id,
            PatientTagAssignment.patient_id == patient_id,
            PatientTagAssignment.tag_id == tag_id,
        )
    )
    if assignment is not None:
        db.delete(assignment)
        db.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.post("/leads", response_model=LeadRead, status_code=status.HTTP_201_CREATED)
def create_lead(
    payload: LeadCreate,
    access: Annotated[WorkspaceAccess, Depends(get_workspace_reader)],
    db: Annotated[Session, Depends(get_db)],
) -> Lead:
    patient = get_patient_or_404(db, access.workspace.id, payload.patient_id)
    ensure_service(db, access.workspace.id, payload.service_id)
    ensure_assignable_user(db, access.workspace.id, payload.assigned_user_id)
    data = payload.model_dump(exclude={"source"})
    lead = Lead(
        workspace_id=access.workspace.id,
        source=payload.source or patient.source,
        **data,
    )
    db.add(lead)
    db.commit()
    db.refresh(lead)
    return lead


@router.get("/leads", response_model=list[LeadRead])
def list_leads(
    access: Annotated[WorkspaceAccess, Depends(get_workspace_reader)],
    db: Annotated[Session, Depends(get_db)],
    lead_status: Annotated[LeadStatus | None, Query(alias="status")] = None,
    patient_id: UUID | None = None,
    assigned_user_id: UUID | None = None,
    limit: Annotated[int, Query(ge=1, le=100)] = 50,
    offset: Annotated[int, Query(ge=0)] = 0,
) -> list[Lead]:
    stmt = select(Lead).where(Lead.workspace_id == access.workspace.id)
    if lead_status:
        stmt = stmt.where(Lead.status == lead_status)
    if patient_id:
        stmt = stmt.where(Lead.patient_id == patient_id)
    if assigned_user_id:
        stmt = stmt.where(Lead.assigned_user_id == assigned_user_id)
    stmt = stmt.order_by(Lead.created_at.desc()).limit(limit).offset(offset)
    return list(db.scalars(stmt))


@router.patch("/leads/{lead_id}", response_model=LeadRead)
def update_lead(
    lead_id: UUID,
    payload: LeadUpdate,
    access: Annotated[WorkspaceAccess, Depends(get_workspace_reader)],
    db: Annotated[Session, Depends(get_db)],
) -> Lead:
    lead = db.scalar(
        select(Lead).where(
            Lead.id == lead_id,
            Lead.workspace_id == access.workspace.id,
        )
    )
    if lead is None:
        raise not_found("Lead")
    updates = payload.model_dump(exclude_unset=True)
    required_fields = {"source", "status", "currency"}
    if any(field in updates and updates[field] is None for field in required_fields):
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="Required lead fields cannot be null.",
        )
    if "service_id" in updates:
        ensure_service(db, access.workspace.id, updates["service_id"])
    if "assigned_user_id" in updates:
        ensure_assignable_user(db, access.workspace.id, updates["assigned_user_id"])
    for key, value in updates.items():
        setattr(lead, key, value)
    if lead.status != "lost":
        lead.lost_reason = None
    db.commit()
    db.refresh(lead)
    return lead


@router.post(
    "/conversations",
    response_model=ConversationRead,
    status_code=status.HTTP_201_CREATED,
)
def create_conversation(
    payload: ConversationCreate,
    access: Annotated[WorkspaceAccess, Depends(get_workspace_reader)],
    db: Annotated[Session, Depends(get_db)],
) -> Conversation:
    get_patient_or_404(db, access.workspace.id, payload.patient_id)
    ensure_assignable_user(db, access.workspace.id, payload.assigned_user_id)
    now = datetime.now(timezone.utc)
    conversation = Conversation(
        workspace_id=access.workspace.id,
        started_at=now,
        **payload.model_dump(),
    )
    if payload.status == "closed":
        conversation.closed_at = now
    db.add(conversation)
    commit_or_conflict(db, "This external conversation already exists in the workspace.")
    db.refresh(conversation)
    return conversation


@router.get("/conversations", response_model=list[ConversationRead])
def list_conversations(
    access: Annotated[WorkspaceAccess, Depends(get_workspace_reader)],
    db: Annotated[Session, Depends(get_db)],
    conversation_status: Annotated[ConversationStatus | None, Query(alias="status")] = None,
    patient_id: UUID | None = None,
    channel: ConversationChannel | None = None,
    limit: Annotated[int, Query(ge=1, le=100)] = 50,
    offset: Annotated[int, Query(ge=0)] = 0,
) -> list[Conversation]:
    stmt = select(Conversation).where(Conversation.workspace_id == access.workspace.id)
    if conversation_status:
        stmt = stmt.where(Conversation.status == conversation_status)
    if patient_id:
        stmt = stmt.where(Conversation.patient_id == patient_id)
    if channel:
        stmt = stmt.where(Conversation.channel == channel)
    stmt = stmt.order_by(
        Conversation.last_message_at.desc().nullslast(),
        Conversation.created_at.desc(),
    ).limit(limit).offset(offset)
    return list(db.scalars(stmt))


@router.patch("/conversations/{conversation_id}", response_model=ConversationRead)
def update_conversation(
    conversation_id: UUID,
    payload: ConversationUpdate,
    access: Annotated[WorkspaceAccess, Depends(get_workspace_reader)],
    db: Annotated[Session, Depends(get_db)],
) -> Conversation:
    conversation = db.scalar(
        select(Conversation).where(
            Conversation.id == conversation_id,
            Conversation.workspace_id == access.workspace.id,
        )
    )
    if conversation is None:
        raise not_found("Conversation")
    updates = payload.model_dump(exclude_unset=True)
    if "status" in updates and updates["status"] is None:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="Conversation status cannot be null.",
        )
    if "assigned_user_id" in updates:
        ensure_assignable_user(db, access.workspace.id, updates["assigned_user_id"])
    if "status" in updates:
        if updates["status"] == "closed" and conversation.status != "closed":
            conversation.closed_at = datetime.now(timezone.utc)
        elif updates["status"] != "closed":
            conversation.closed_at = None
    for key, value in updates.items():
        setattr(conversation, key, value)
    db.commit()
    db.refresh(conversation)
    return conversation


@router.post(
    "/conversations/{conversation_id}/messages",
    response_model=MessageRead,
    status_code=status.HTTP_201_CREATED,
)
def create_message(
    conversation_id: UUID,
    payload: MessageCreate,
    access: Annotated[WorkspaceAccess, Depends(get_workspace_reader)],
    db: Annotated[Session, Depends(get_db)],
) -> Message:
    conversation = db.scalar(
        select(Conversation).where(
            Conversation.id == conversation_id,
            Conversation.workspace_id == access.workspace.id,
        )
    )
    if conversation is None:
        raise not_found("Conversation")

    if payload.delivery_status is not None:
        delivery_status = payload.delivery_status
    elif payload.direction == "inbound":
        delivery_status = "received"
    elif payload.direction == "internal":
        delivery_status = "sent"
    else:
        delivery_status = "queued"

    sent_by_user_id = access.user.id if payload.sender_type == "staff" else None
    message = Message(
        workspace_id=access.workspace.id,
        conversation_id=conversation.id,
        sender_type=payload.sender_type,
        direction=payload.direction,
        message_type=payload.message_type,
        content=payload.content.strip() if payload.content else None,
        external_message_id=payload.external_message_id,
        delivery_status=delivery_status,
        sent_by_user_id=sent_by_user_id,
        metadata_json=payload.metadata,
    )
    db.add(message)

    now = datetime.now(timezone.utc)
    conversation.last_message_at = now
    if conversation.status == "closed":
        conversation.status = "open"
        conversation.closed_at = None
    if payload.direction != "internal":
        patient = get_patient_or_404(db, access.workspace.id, conversation.patient_id)
        patient.last_contact_at = now
    db.commit()
    db.refresh(message)
    return message


@router.get(
    "/conversations/{conversation_id}/messages",
    response_model=list[MessageRead],
)
def list_messages(
    conversation_id: UUID,
    access: Annotated[WorkspaceAccess, Depends(get_workspace_reader)],
    db: Annotated[Session, Depends(get_db)],
    limit: Annotated[int, Query(ge=1, le=200)] = 100,
    before: datetime | None = None,
) -> list[Message]:
    conversation = db.scalar(
        select(Conversation.id).where(
            Conversation.id == conversation_id,
            Conversation.workspace_id == access.workspace.id,
        )
    )
    if conversation is None:
        raise not_found("Conversation")

    stmt = select(Message).where(
        Message.workspace_id == access.workspace.id,
        Message.conversation_id == conversation_id,
    )
    if before:
        stmt = stmt.where(Message.created_at < before)
    stmt = stmt.order_by(Message.created_at.desc()).limit(limit)
    messages = list(db.scalars(stmt))
    messages.reverse()
    return messages
