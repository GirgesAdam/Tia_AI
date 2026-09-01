from __future__ import annotations

from datetime import datetime
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, Field

ActivityActorType = Literal["staff", "ai", "system"]


class ActivityEventRead(BaseModel):
    id: UUID
    action: str
    actor_type: ActivityActorType
    actor_user_id: UUID | None
    actor_label: str
    entity_type: str
    entity_id: UUID | None
    summary: str
    metadata: dict = Field(default_factory=dict)
    created_at: datetime
