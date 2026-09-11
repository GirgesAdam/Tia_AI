from __future__ import annotations

from uuid import UUID

from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from app.models.clinic_inventory import LASER_DEVICE_NAMES, ServiceDevicePrice
from app.models.clinic_knowledge_entry import ClinicKnowledgeEntry
from app.models.service import Service
from app.schemas.clinic_knowledge_base import ClinicKnowledgeEntryRead, ClinicKnowledgeEntryWrite


class ClinicKnowledgeError(ValueError):
    pass


SINGLE_KNOWLEDGE_TITLE = "معلومات العيادة"


def _validate_target(db: Session, *, workspace_id: UUID, payload: ClinicKnowledgeEntryWrite) -> None:
    if payload.scope_type == "service":
        service = db.scalar(select(Service).where(Service.workspace_id == workspace_id, Service.id == payload.service_id))
        if service is None:
            raise ClinicKnowledgeError("Service not found in this clinic.")
    if payload.scope_type == "laser_device":
        exists = db.scalar(
            select(ServiceDevicePrice.id).where(
                ServiceDevicePrice.workspace_id == workspace_id,
                ServiceDevicePrice.device_key == payload.device_key,
                ServiceDevicePrice.is_active.is_(True),
            ).limit(1)
        )
        if exists is None:
            raise ClinicKnowledgeError("Laser device is not configured for this clinic.")


def _read(entry: ClinicKnowledgeEntry, service_name: str | None = None) -> ClinicKnowledgeEntryRead:
    return ClinicKnowledgeEntryRead(
        id=entry.id,
        scope_type=entry.scope_type,
        service_id=entry.service_id,
        service_name=service_name,
        device_key=entry.device_key,
        device_name=LASER_DEVICE_NAMES.get(entry.device_key or ""),
        title=entry.title,
        content=entry.content,
        sort_order=entry.sort_order,
        is_active=entry.is_active,
        created_at=entry.created_at,
        updated_at=entry.updated_at,
    )


def list_knowledge_entries(db: Session, *, workspace_id: UUID, active_only: bool = False) -> list[ClinicKnowledgeEntryRead]:
    stmt = select(ClinicKnowledgeEntry, Service.name).outerjoin(
        Service,
        (Service.workspace_id == ClinicKnowledgeEntry.workspace_id)
        & (Service.id == ClinicKnowledgeEntry.service_id),
    ).where(ClinicKnowledgeEntry.workspace_id == workspace_id)
    if active_only:
        stmt = stmt.where(ClinicKnowledgeEntry.is_active.is_(True))
    rows = db.execute(stmt.order_by(ClinicKnowledgeEntry.scope_type, ClinicKnowledgeEntry.sort_order, ClinicKnowledgeEntry.created_at)).all()
    return [_read(entry, service_name) for entry, service_name in rows]


def read_knowledge_text(db: Session, *, workspace_id: UUID) -> str:
    """Expose the legacy structured entries as one editable text field during migration."""
    entries = list_knowledge_entries(db, workspace_id=workspace_id)
    if not entries:
        return ""
    if len(entries) == 1 and entries[0].title == SINGLE_KNOWLEDGE_TITLE:
        return entries[0].content

    blocks: list[str] = []
    for entry in entries:
        content = entry.content.strip()
        if not content:
            continue
        title = entry.title.strip()
        blocks.append(f"{title}\n{content}" if title else content)
    return "\n\n".join(blocks)[:6000]


def replace_knowledge_text(db: Session, *, workspace_id: UUID, content: str) -> str:
    """Atomically replace all user-managed knowledge with one clinic-wide text entry."""
    normalized = content.strip()
    db.execute(delete(ClinicKnowledgeEntry).where(ClinicKnowledgeEntry.workspace_id == workspace_id))
    db.flush()
    if normalized:
        db.add(
            ClinicKnowledgeEntry(
                workspace_id=workspace_id,
                scope_type="clinic",
                service_id=None,
                device_key=None,
                title=SINGLE_KNOWLEDGE_TITLE,
                content=normalized,
                sort_order=0,
                is_active=True,
            )
        )
        db.flush()
    return normalized


def create_knowledge_entry(db: Session, *, workspace_id: UUID, payload: ClinicKnowledgeEntryWrite) -> ClinicKnowledgeEntry:
    _validate_target(db, workspace_id=workspace_id, payload=payload)
    entry = ClinicKnowledgeEntry(workspace_id=workspace_id, **payload.model_dump())
    db.add(entry)
    db.flush()
    return entry


def update_knowledge_entry(db: Session, *, workspace_id: UUID, entry_id: UUID, payload: ClinicKnowledgeEntryWrite) -> ClinicKnowledgeEntry:
    entry = db.scalar(select(ClinicKnowledgeEntry).where(ClinicKnowledgeEntry.workspace_id == workspace_id, ClinicKnowledgeEntry.id == entry_id))
    if entry is None:
        raise ClinicKnowledgeError("Knowledge entry not found.")
    _validate_target(db, workspace_id=workspace_id, payload=payload)
    for key, value in payload.model_dump().items():
        setattr(entry, key, value)
    db.flush()
    return entry


def delete_knowledge_entry(db: Session, *, workspace_id: UUID, entry_id: UUID) -> ClinicKnowledgeEntry:
    entry = db.scalar(select(ClinicKnowledgeEntry).where(ClinicKnowledgeEntry.workspace_id == workspace_id, ClinicKnowledgeEntry.id == entry_id))
    if entry is None:
        raise ClinicKnowledgeError("Knowledge entry not found.")
    db.delete(entry)
    db.flush()
    return entry


def relevant_knowledge_context(
    db: Session,
    *,
    workspace_id: UUID,
    service_id: UUID | None = None,
    device_key: str | None = None,
    include_clinic: bool = False,
    limit: int = 8,
) -> dict[str, object] | None:
    """Return only grounded explanatory entries relevant to the current turn."""
    clauses = []
    if include_clinic or service_id is not None or device_key:
        clauses.append(ClinicKnowledgeEntry.scope_type == "clinic")
    if service_id is not None:
        clauses.append(
            (ClinicKnowledgeEntry.scope_type == "service")
            & (ClinicKnowledgeEntry.service_id == service_id)
        )
    if device_key:
        clauses.append(
            (ClinicKnowledgeEntry.scope_type == "laser_device")
            & (ClinicKnowledgeEntry.device_key == device_key)
        )
    if not clauses:
        return None
    from sqlalchemy import or_

    entries = list(
        db.scalars(
            select(ClinicKnowledgeEntry)
            .where(
                ClinicKnowledgeEntry.workspace_id == workspace_id,
                ClinicKnowledgeEntry.is_active.is_(True),
                or_(*clauses),
            )
            .order_by(ClinicKnowledgeEntry.sort_order, ClinicKnowledgeEntry.created_at)
            .limit(max(1, min(limit, 8)))
        )
    )
    if not entries:
        return None
    return {
        "ok": True,
        "source": "curated_clinic_knowledge",
        "authority": "explanatory_only",
        "entries": [
            {
                "scope_type": item.scope_type,
                "service_id": str(item.service_id) if item.service_id else None,
                "device_key": item.device_key,
                "title": item.title,
                "content": item.content[:6000] if item.title == SINGLE_KNOWLEDGE_TITLE else item.content[:1200],
            }
            for item in entries
        ],
        "rule": "Never override canonical price, duration, availability, payment, package, or booking-policy data with this knowledge.",
    }
