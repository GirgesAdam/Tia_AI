from __future__ import annotations

from datetime import datetime
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, field_validator

from app.schemas.analytics_catalog import AnalyticsCatalogChart, AnalyticsCatalogRunRequest

AnalyticsSavedViewDisplayMode = Literal["visual", "table", "both"]


class AnalyticsSavedViewCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str = Field(min_length=1, max_length=160)
    request: AnalyticsCatalogRunRequest
    chart: AnalyticsCatalogChart | None = None
    display_mode: AnalyticsSavedViewDisplayMode = "visual"

    @field_validator("name")
    @classmethod
    def clean_name(cls, value: str) -> str:
        cleaned = " ".join(value.split())
        if not cleaned:
            raise ValueError("Saved view name cannot be empty.")
        return cleaned


class AnalyticsSavedViewRead(BaseModel):
    id: UUID
    workspace_id: UUID
    created_by_user_id: UUID
    name: str
    analysis_key: str
    request: AnalyticsCatalogRunRequest
    chart: AnalyticsCatalogChart | None
    display_mode: AnalyticsSavedViewDisplayMode
    created_at: datetime
    updated_at: datetime
