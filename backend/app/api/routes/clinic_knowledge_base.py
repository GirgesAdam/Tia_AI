from __future__ import annotations

from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Response, status
from sqlalchemy.orm import Session

from app.api.dependencies.security import WorkspaceAccess, get_workspace_admin, get_workspace_reader
from app.database.session import get_db
from app.schemas.clinic_knowledge_base import (
    ClinicKnowledgeBaseSnapshot,
    ClinicKnowledgeEntryRead,
    ClinicKnowledgeEntryUpdate,
    ClinicKnowledgeEntryWrite,
)
from app.services.activity import record_activity_event
from app.services.clinic_knowledge_base import (
    ClinicKnowledgeError,
    create_knowledge_entry,
    delete_knowledge_entry,
    list_knowledge_entries,
    update_knowledge_entry,
)

router = APIRouter()


def _error(exc: ClinicKnowledgeError) -> HTTPException:
    return HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(exc))


@router.get("/knowledge-base", response_model=ClinicKnowledgeBaseSnapshot)
def read_knowledge_base(
    access: Annotated[WorkspaceAccess, Depends(get_workspace_reader)],
    db: Annotated[Session, Depends(get_db)],
) -> ClinicKnowledgeBaseSnapshot:
    return ClinicKnowledgeBaseSnapshot(entries=list_knowledge_entries(db, workspace_id=access.workspace.id))


@router.post("/knowledge-base", response_model=ClinicKnowledgeEntryRead, status_code=status.HTTP_201_CREATED)
def add_knowledge_entry(
    payload: ClinicKnowledgeEntryWrite,
    access: Annotated[WorkspaceAccess, Depends(get_workspace_admin)],
    db: Annotated[Session, Depends(get_db)],
) -> ClinicKnowledgeEntryRead:
    try:
        entry = create_knowledge_entry(db, workspace_id=access.workspace.id, payload=payload)
        record_activity_event(
            db,
            workspace_id=access.workspace.id,
            actor_type="staff",
            actor_user_id=access.user.id,
            action="clinic.knowledge_created",
            entity_type="clinic_knowledge_entry",
            entity_id=entry.id,
            summary="Clinic knowledge entry created.",
            metadata={"scope_type": entry.scope_type},
            flush=False,
        )
        db.commit()
        return next(item for item in list_knowledge_entries(db, workspace_id=access.workspace.id) if item.id == entry.id)
    except ClinicKnowledgeError as exc:
        db.rollback()
        raise _error(exc) from exc


@router.put("/knowledge-base/{entry_id}", response_model=ClinicKnowledgeEntryRead)
def edit_knowledge_entry(
    entry_id: UUID,
    payload: ClinicKnowledgeEntryUpdate,
    access: Annotated[WorkspaceAccess, Depends(get_workspace_admin)],
    db: Annotated[Session, Depends(get_db)],
) -> ClinicKnowledgeEntryRead:
    try:
        entry = update_knowledge_entry(db, workspace_id=access.workspace.id, entry_id=entry_id, payload=payload)
        record_activity_event(
            db,
            workspace_id=access.workspace.id,
            actor_type="staff",
            actor_user_id=access.user.id,
            action="clinic.knowledge_updated",
            entity_type="clinic_knowledge_entry",
            entity_id=entry.id,
            summary="Clinic knowledge entry updated.",
            metadata={"scope_type": entry.scope_type},
            flush=False,
        )
        db.commit()
        return next(item for item in list_knowledge_entries(db, workspace_id=access.workspace.id) if item.id == entry.id)
    except ClinicKnowledgeError as exc:
        db.rollback()
        raise _error(exc) from exc


@router.delete("/knowledge-base/{entry_id}", status_code=status.HTTP_204_NO_CONTENT)
def remove_knowledge_entry(
    entry_id: UUID,
    access: Annotated[WorkspaceAccess, Depends(get_workspace_admin)],
    db: Annotated[Session, Depends(get_db)],
) -> Response:
    try:
        entry = delete_knowledge_entry(db, workspace_id=access.workspace.id, entry_id=entry_id)
        record_activity_event(
            db,
            workspace_id=access.workspace.id,
            actor_type="staff",
            actor_user_id=access.user.id,
            action="clinic.knowledge_deleted",
            entity_type="clinic_knowledge_entry",
            entity_id=entry_id,
            summary="Clinic knowledge entry deleted.",
            metadata={"scope_type": entry.scope_type},
            flush=False,
        )
        db.commit()
        return Response(status_code=status.HTTP_204_NO_CONTENT)
    except ClinicKnowledgeError as exc:
        db.rollback()
        raise _error(exc) from exc
