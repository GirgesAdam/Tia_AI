from __future__ import annotations

from datetime import datetime
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, Field, field_validator

from app.schemas.analytics_bi import AnalyticsBIPlan
from app.schemas.analytics_composable import AnalyticsAudiencePlan
from app.schemas.crm import CRMTaskPriority, normalize_required_text

CohortableAnalyticsOperation = Literal[
    "top_repeat_patients",
    "top_value_patients",
    "lapsed_patients",
]


AnalyticsSavedAudiencePlan = AnalyticsBIPlan | AnalyticsAudiencePlan


class AnalyticsCohortCreateRequest(BaseModel):
    request_id: UUID
    name: str = Field(min_length=1, max_length=160)
    question: str = Field(min_length=1, max_length=1200)
    plan: AnalyticsSavedAudiencePlan

    @field_validator("name", "question")
    @classmethod
    def normalize_text(cls, value: str) -> str:
        return normalize_required_text(value)


class CRMCohortMemberRead(BaseModel):
    patient_id: UUID
    rank: int
    patient_name: str
    patient_phone: str | None = None
    snapshot_metrics: list[dict] = Field(default_factory=list)


class CRMCohortRead(BaseModel):
    id: UUID
    workspace_id: UUID
    created_by_user_id: UUID | None
    name: str
    request_id: UUID
    source: Literal["analytics_bi"]
    status: Literal["active", "archived"]
    analytics_operation: str
    question: str
    plan: AnalyticsSavedAudiencePlan
    period_label: str
    member_count: int
    created_at: datetime
    updated_at: datetime
    members: list[CRMCohortMemberRead] = Field(default_factory=list)


class CohortFollowUpCreateRequest(BaseModel):
    request_id: UUID
    assigned_user_id: UUID | None = None
    priority: CRMTaskPriority = "normal"
    title: str = Field(min_length=1, max_length=200)
    description: str | None = Field(default=None, max_length=5000)
    due_at: datetime

    @field_validator("title")
    @classmethod
    def normalize_title(cls, value: str) -> str:
        return normalize_required_text(value)

    @field_validator("description", mode="before")
    @classmethod
    def normalize_description(cls, value: object) -> object:
        if isinstance(value, str):
            normalized = value.strip()
            return normalized or None
        return value


class CohortFollowUpResult(BaseModel):
    cohort_id: UUID
    request_id: UUID
    member_count: int
    created_tasks: int
    reused_tasks: int
    task_ids: list[UUID] = Field(default_factory=list)

CampaignParameterKey = Literal["patient_first_name", "clinic_name", "cohort_name"]
CampaignRecipientStatus = Literal[
    "eligible",
    "skipped_no_consent",
    "skipped_inactive",
    "skipped_no_route",
    "cancelled_no_consent",
    "cancelled_inactive",
    "cancelled_no_route",
    "queued",
    "processing",
    "sent",
    "delivered",
    "read",
    "failed",
    "cancelled",
]


class CohortCampaignPrepareRequest(BaseModel):
    request_id: UUID
    name: str = Field(min_length=1, max_length=160)
    channel_connection_id: UUID
    template_name: str = Field(min_length=1, max_length=160)
    template_language: str = Field(default="ar", min_length=1, max_length=32)
    body_parameter_keys: list[CampaignParameterKey] = Field(default_factory=list, max_length=3)
    rate_limit_per_minute: int = Field(default=10, ge=1, le=60)

    @field_validator("name", "template_name", "template_language")
    @classmethod
    def normalize_campaign_text(cls, value: str) -> str:
        return normalize_required_text(value)

    @field_validator("body_parameter_keys")
    @classmethod
    def unique_parameter_keys(cls, value: list[CampaignParameterKey]) -> list[CampaignParameterKey]:
        if len(value) != len(set(value)):
            raise ValueError("Campaign body parameter keys cannot contain duplicates.")
        return value


class CohortCampaignConfirmRequest(BaseModel):
    confirmation_id: UUID


class CRMCampaignRecipientRead(BaseModel):
    id: UUID
    patient_id: UUID
    rank: int
    patient_name: str
    patient_phone: str | None = None
    status: CampaignRecipientStatus
    reason: str | None = None
    message_id: UUID | None = None
    dispatch_id: UUID | None = None
    scheduled_at: datetime | None = None


class CRMCampaignRead(BaseModel):
    id: UUID
    workspace_id: UUID
    cohort_id: UUID
    channel_connection_id: UUID
    created_by_user_id: UUID | None
    confirmed_by_user_id: UUID | None
    request_id: UUID
    confirmation_id: UUID | None
    name: str
    status: Literal["draft", "confirmed", "cancelled"]
    template_name: str
    template_language: str
    body_parameter_keys: list[CampaignParameterKey] = Field(default_factory=list)
    rate_limit_per_minute: int
    recipient_count: int
    eligible_count: int
    confirmed_at: datetime | None
    created_at: datetime
    updated_at: datetime
    recipients: list[CRMCampaignRecipientRead] = Field(default_factory=list)


class CohortCampaignConfirmResult(BaseModel):
    campaign_id: UUID
    confirmation_id: UUID
    recipient_count: int
    preview_eligible_count: int
    queued_count: int
    cancelled_before_queue: int
    status: Literal["confirmed"] = "confirmed"


class AnalyticsAudienceActionConfirmRequest(BaseModel):
    request_id: UUID
    audience_request_id: UUID
    name: str = Field(min_length=1, max_length=160)
    question: str = Field(min_length=1, max_length=1200)
    plan: AnalyticsAudiencePlan
    action_kind: Literal["save_audience", "follow_up_tasks", "whatsapp_campaign"]
    assigned_user_id: UUID | None = None
    priority: CRMTaskPriority = "normal"
    title: str | None = Field(default=None, max_length=200)
    description: str | None = Field(default=None, max_length=5000)
    due_at: datetime | None = None

    @field_validator("name", "question")
    @classmethod
    def normalize_action_text(cls, value: str) -> str:
        return normalize_required_text(value)

    @field_validator("title", "description", mode="before")
    @classmethod
    def normalize_optional_action_text(cls, value: object) -> object:
        if isinstance(value, str):
            normalized = value.strip()
            return normalized or None
        return value


class AnalyticsAudienceActionResult(BaseModel):
    audience: CRMCohortRead
    action_kind: Literal["save_audience", "follow_up_tasks", "whatsapp_campaign"]
    follow_up: CohortFollowUpResult | None = None
    next_step: Literal["saved", "tasks_created", "campaign_setup"]
