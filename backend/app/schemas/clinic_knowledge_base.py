from __future__ import annotations

from datetime import datetime
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, Field, model_validator

KnowledgeScope = Literal["clinic", "service", "laser_device"]


class ClinicKnowledgeEntryWrite(BaseModel):
    scope_type: KnowledgeScope
    service_id: UUID | None = None
    device_key: str | None = Field(default=None, max_length=40)
    title: str = Field(min_length=1, max_length=200)
    content: str = Field(min_length=1, max_length=6000)
    sort_order: int = Field(default=0, ge=-1000, le=1000)
    is_active: bool = True

    @model_validator(mode="after")
    def validate_scope(self):
        if self.scope_type == "clinic" and (self.service_id is not None or self.device_key):
            raise ValueError("Clinic knowledge cannot target a service or device.")
        if self.scope_type == "service" and (self.service_id is None or self.device_key):
            raise ValueError("Service knowledge requires service_id only.")
        if self.scope_type == "laser_device" and (self.service_id is not None or not self.device_key):
            raise ValueError("Laser-device knowledge requires device_key only.")
        return self


class ClinicKnowledgeEntryUpdate(ClinicKnowledgeEntryWrite):
    pass


class ClinicKnowledgeEntryRead(BaseModel):
    id: UUID
    scope_type: KnowledgeScope
    service_id: UUID | None
    service_name: str | None = None
    device_key: str | None
    device_name: str | None = None
    title: str
    content: str
    sort_order: int
    is_active: bool
    created_at: datetime
    updated_at: datetime


class ClinicKnowledgeBaseSnapshot(BaseModel):
    entries: list[ClinicKnowledgeEntryRead]


class ClinicKnowledgeText(BaseModel):
    content: str = Field(default="", max_length=6000)
