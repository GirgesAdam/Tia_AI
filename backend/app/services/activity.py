from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import Any, Literal
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.activity_event import ActivityEvent
from app.models.user import User

ActivityActorType = Literal["staff", "ai", "system"]
ACTIVITY_ALLOWED_DAYS = (7, 30, 90)
_SENSITIVE_KEY_PARTS = (
    "email",
    "phone",
    "message",
    "content",
    "text",
    "token",
    "secret",
    "password",
    "api_key",
)


def _safe_activity_metadata(value: Any, *, key: str | None = None, depth: int = 0) -> Any:
    """Bound activity metadata and drop obvious PII/secrets.

    Audit rows should explain a mutation, not become a second copy of patient
    messages, contact data, tokens, or free-form clinical text.
    """
    if key and any(part in key.lower() for part in _SENSITIVE_KEY_PARTS):
        return None
    if depth > 3:
        return None
    if value is None or isinstance(value, (bool, int, float)):
        return value
    if isinstance(value, UUID):
        return str(value)
    if isinstance(value, datetime):
        return value.astimezone(UTC).isoformat() if value.tzinfo else value.isoformat()
    if isinstance(value, str):
        return value[:200]
    if isinstance(value, (list, tuple, set)):
        return [
            item
            for item in (
                _safe_activity_metadata(child, depth=depth + 1) for child in list(value)[:30]
            )
            if item is not None
        ]
    if isinstance(value, dict):
        clean: dict[str, Any] = {}
        for raw_key, child in list(value.items())[:40]:
            child_key = str(raw_key)[:80]
            sanitized = _safe_activity_metadata(child, key=child_key, depth=depth + 1)
            if sanitized is not None:
                clean[child_key] = sanitized
        return clean
    return str(value)[:200]


def record_activity_event(
    db: Session,
    *,
    workspace_id: UUID,
    actor_type: ActivityActorType,
    action: str,
    entity_type: str,
    summary: str,
    actor_user_id: UUID | None = None,
    entity_id: UUID | None = None,
    metadata: dict | None = None,
    flush: bool = True,
) -> ActivityEvent:
    if actor_type not in {"staff", "ai", "system"}:
        raise ValueError("Unsupported activity actor type.")
    action = action.strip()
    entity_type = entity_type.strip()
    summary = summary.strip()
    if not action or len(action) > 80:
        raise ValueError("Activity action must be between 1 and 80 characters.")
    if not entity_type or len(entity_type) > 40:
        raise ValueError("Activity entity_type must be between 1 and 40 characters.")
    if not summary:
        raise ValueError("Activity summary cannot be empty.")

    clean_metadata = _safe_activity_metadata(metadata or {})
    event = ActivityEvent(
        workspace_id=workspace_id,
        actor_type=actor_type,
        actor_user_id=actor_user_id,
        action=action,
        entity_type=entity_type,
        entity_id=entity_id,
        summary=summary[:500],
        metadata_json=clean_metadata if isinstance(clean_metadata, dict) else {},
    )
    db.add(event)
    if flush:
        db.flush()
    return event


def list_activity_events(
    db: Session,
    *,
    workspace_id: UUID,
    days: int = 7,
    actor_type: ActivityActorType | None = None,
    entity_type: str | None = None,
    limit: int = 100,
    now: datetime | None = None,
) -> list[tuple[ActivityEvent, User | None]]:
    if days not in ACTIVITY_ALLOWED_DAYS:
        raise ValueError(f"days must be one of {ACTIVITY_ALLOWED_DAYS}")
    if actor_type is not None and actor_type not in {"staff", "ai", "system"}:
        raise ValueError("Unsupported activity actor type.")
    if not 1 <= limit <= 200:
        raise ValueError("limit must be between 1 and 200.")

    now = (now or datetime.now(UTC)).astimezone(UTC)
    since = now - timedelta(days=days)
    stmt = (
        select(ActivityEvent, User)
        .outerjoin(User, User.id == ActivityEvent.actor_user_id)
        .where(
            ActivityEvent.workspace_id == workspace_id,
            ActivityEvent.created_at >= since,
        )
    )
    if actor_type is not None:
        stmt = stmt.where(ActivityEvent.actor_type == actor_type)
    if entity_type:
        stmt = stmt.where(ActivityEvent.entity_type == entity_type)
    return list(
        db.execute(stmt.order_by(ActivityEvent.created_at.desc(), ActivityEvent.id.desc()).limit(limit)).all()
    )
