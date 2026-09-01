from __future__ import annotations

from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, Field


class CampaignAnalyticsMetrics(BaseModel):
    recipient_count: int = 0
    eligible_count: int = 0
    dispatch_count: int = 0
    sent_count: int = 0
    delivered_count: int = 0
    read_count: int = 0
    failed_count: int = 0
    cancelled_count: int = 0
    delivery_rate: float = 0.0
    read_rate: float = 0.0
    tracked_booking_count: int = 0
    completed_booking_count: int = 0
    booking_conversion_rate: float = 0.0
    attributed_revenue_minor: int = 0
    currency: str = "EGP"


class CampaignAnalyticsCampaignRead(CampaignAnalyticsMetrics):
    campaign_id: UUID
    cohort_id: UUID
    name: str
    status: str
    template_name: str
    confirmed_at: datetime | None = None


class CampaignAnalyticsOverviewRead(BaseModel):
    period_label: str
    attribution_window_days: int
    historical_booking_backfill: bool = False
    totals: CampaignAnalyticsMetrics
    campaigns: list[CampaignAnalyticsCampaignRead] = Field(default_factory=list)
    definitions: list[str] = Field(default_factory=list)
