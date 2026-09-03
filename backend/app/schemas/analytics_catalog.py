from __future__ import annotations

from datetime import date
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from app.schemas.analytics_bi import AnalyticsBIMetricRead, AnalyticsBIResultRow
from app.schemas.analytics_business import AnalyticsBusinessPlan
from app.schemas.analytics_composable import AnalyticsAudiencePlan

AnalyticsCatalogCategory = Literal[
    "revenue",
    "patients",
    "appointments",
    "services",
    "doctors",
    "branches",
    "retention",
    "funnels",
]
AnalyticsCatalogResultKind = Literal["summary", "trend", "breakdown", "patient_list", "funnel"]
AnalyticsCatalogChart = Literal["kpi", "line", "bar", "heatmap", "funnel", "table"]
AnalyticsCatalogFilter = Literal[
    "period",
    "service",
    "branch",
    "doctor",
    "comparison",
    "granularity",
    "limit",
    "inactivity_days",
    "min_visits",
    "max_visits",
    "future_booking",
    "marketing_consent",
]
AnalyticsCatalogAction = Literal[
    "export",
    "save_patient_group",
    "follow_up_tasks",
    "whatsapp_campaign",
]
AnalyticsCatalogGranularity = Literal["day", "week", "month"]


class AnalyticsCatalogEntityOption(BaseModel):
    id: str
    name: str


class AnalyticsCatalogDefinitionRead(BaseModel):
    key: str
    category: AnalyticsCatalogCategory
    title: str
    description: str
    result_kind: AnalyticsCatalogResultKind
    default_chart: AnalyticsCatalogChart
    supported_charts: list[AnalyticsCatalogChart]
    filters: list[AnalyticsCatalogFilter]
    allowed_actions: list[AnalyticsCatalogAction]
    default_lookback_days: int | None = None
    default_granularity: AnalyticsCatalogGranularity | None = None
    default_inactivity_days: int | None = None
    default_limit: int = 10
    default_min_visits: int | None = None
    default_max_visits: int | None = None
    chart_metric_keys: list[str] = Field(default_factory=list)


class AnalyticsCatalogRead(BaseModel):
    analyses: list[AnalyticsCatalogDefinitionRead]
    services: list[AnalyticsCatalogEntityOption]
    branches: list[AnalyticsCatalogEntityOption]
    doctors: list[AnalyticsCatalogEntityOption]


class AnalyticsCatalogRunRequest(BaseModel):
    """Explicit admin-selected analytics request.

    There is intentionally no free-text question or model-facing field here.
    The analysis key chooses a deterministic backend function, and this object
    only carries bounded filters exposed by that analysis definition.
    """

    model_config = ConfigDict(extra="forbid")

    analysis_key: str = Field(min_length=1, max_length=120)
    lookback_days: int | None = Field(default=None, ge=1, le=3650)
    all_history: bool = False
    start_date: date | None = None
    end_date: date | None = None
    service_ids: list[str] = Field(default_factory=list)
    branch_ids: list[str] = Field(default_factory=list)
    doctor_ids: list[str] = Field(default_factory=list)
    comparison: bool = False
    granularity: AnalyticsCatalogGranularity | None = None
    limit: int | None = Field(default=None, ge=1, le=25)
    inactivity_days: int | None = Field(default=None, ge=30, le=3650)
    min_visits: int | None = Field(default=None, ge=1, le=100)
    max_visits: int | None = Field(default=None, ge=1, le=100)
    has_future_appointment: bool | None = None
    marketing_consent: bool | None = None

    @field_validator("analysis_key")
    @classmethod
    def normalize_key(cls, value: str) -> str:
        return value.strip()

    @field_validator("service_ids", "branch_ids", "doctor_ids")
    @classmethod
    def dedupe_ids(cls, values: list[str]) -> list[str]:
        result: list[str] = []
        seen: set[str] = set()
        for raw in values:
            value = str(raw).strip()
            if value and value not in seen:
                result.append(value)
                seen.add(value)
        return result

    @model_validator(mode="after")
    def validate_ranges(self) -> AnalyticsCatalogRunRequest:
        explicit_dates = self.start_date is not None or self.end_date is not None
        if self.all_history and (self.lookback_days is not None or explicit_dates):
            raise ValueError("all_history cannot be combined with a bounded period")
        if explicit_dates:
            if self.start_date is None or self.end_date is None:
                raise ValueError("start_date and end_date must be supplied together")
            if self.lookback_days is not None:
                raise ValueError("use either lookback_days or explicit dates, not both")
            if self.end_date < self.start_date:
                raise ValueError("end_date must be >= start_date")
        if self.max_visits is not None and self.min_visits is not None and self.max_visits < self.min_visits:
            raise ValueError("max_visits must be >= min_visits")
        return self


AnalyticsCatalogSeriesFormat = Literal["number", "percent", "money"]


class AnalyticsCatalogChartSeriesRead(BaseModel):
    key: str
    label: str
    format: AnalyticsCatalogSeriesFormat
    currency: str | None = None
    values: list[int | float | None] = Field(default_factory=list)


class AnalyticsCatalogChartDataRead(BaseModel):
    labels: list[str] = Field(default_factory=list)
    series: list[AnalyticsCatalogChartSeriesRead] = Field(default_factory=list)


class AnalyticsCatalogRunRead(BaseModel):
    request: AnalyticsCatalogRunRequest
    analysis_key: str
    title: str
    category: AnalyticsCatalogCategory
    result_kind: AnalyticsCatalogResultKind
    chart: AnalyticsCatalogChart
    supported_charts: list[AnalyticsCatalogChart]
    chart_metric_keys: list[str] = Field(default_factory=list)
    chart_data: AnalyticsCatalogChartDataRead
    highlights: list[AnalyticsBIMetricRead] = Field(default_factory=list)
    allowed_actions: list[AnalyticsCatalogAction]
    period_label: str
    answer: str
    definitions: list[str] = Field(default_factory=list)
    rows: list[AnalyticsBIResultRow] = Field(default_factory=list)
    business_plan: AnalyticsBusinessPlan | None = None
    audience_plan: AnalyticsAudiencePlan | None = None
