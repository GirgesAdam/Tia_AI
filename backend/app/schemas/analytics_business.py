from __future__ import annotations

from datetime import date
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from app.schemas.analytics_bi import AnalyticsBIResultRow

BusinessMetric = Literal[
    "appointments",
    "completed_appointments",
    "no_show_appointments",
    "cancelled_appointments",
    "unique_patients",
    "attendance_rate",
    "no_show_rate",
    "cancellation_rate",
    "gross_paid_minor",
    "refunded_minor",
    "net_paid_minor",
    "avg_net_paid_per_paying_patient_minor",
    "paying_patients",
    "paid_completed_appointments",
    "completion_rate",
    "paid_completion_rate",
    "booking_to_paid_rate",
    "repeat_patients",
    "repeat_rate",
    "new_patients",
    "same_service_repeat_rate",
]

BusinessDimension = Literal["service", "branch", "doctor", "source", "day", "week", "month"]
BusinessSortDirection = Literal["asc", "desc"]
BusinessComparison = Literal["none", "previous_period"]

MONEY_METRICS: frozenset[str] = frozenset({"gross_paid_minor", "refunded_minor", "net_paid_minor", "avg_net_paid_per_paying_patient_minor"})
RATE_METRICS: frozenset[str] = frozenset(
    {
        "attendance_rate",
        "no_show_rate",
        "cancellation_rate",
        "completion_rate",
        "paid_completion_rate",
        "booking_to_paid_rate",
        "repeat_rate",
        "same_service_repeat_rate",
    }
)


class AnalyticsBusinessPlan(BaseModel):
    """Composable business-analytics plan executed only by deterministic backend code."""

    model_config = ConfigDict(extra="forbid")

    kind: Literal["business_analytics"]
    metrics: list[BusinessMetric] = Field(min_length=1, max_length=6)
    group_by: list[BusinessDimension] = Field(max_length=2)
    lookback_days: int | None = Field(ge=1, le=3650)
    start_date: date | None
    end_date: date | None
    comparison: BusinessComparison
    service_ids: list[str]
    branch_ids: list[str]
    doctor_ids: list[str]
    currency: str | None
    limit: int = Field(ge=1, le=25)
    sort_metric: BusinessMetric | None
    sort_direction: BusinessSortDirection
    reason: str = Field(min_length=1, max_length=500)

    @field_validator("metrics", "group_by")
    @classmethod
    def dedupe_literals(cls, values: list[str]) -> list[str]:
        return list(dict.fromkeys(values))

    @field_validator("service_ids", "branch_ids", "doctor_ids")
    @classmethod
    def dedupe_ids(cls, values: list[str]) -> list[str]:
        result: list[str] = []
        seen: set[str] = set()
        for value in values:
            candidate = str(value).strip()
            if candidate and candidate not in seen:
                result.append(candidate)
                seen.add(candidate)
        return result

    @field_validator("currency")
    @classmethod
    def normalize_currency(cls, value: str | None) -> str | None:
        if value is None:
            return None
        normalized = value.strip().upper()
        if len(normalized) != 3 or not normalized.isalpha():
            raise ValueError("currency must be a 3-letter ISO-style code")
        return normalized

    @model_validator(mode="after")
    def validate_shape(self) -> AnalyticsBusinessPlan:
        explicit_dates = self.start_date is not None or self.end_date is not None
        if explicit_dates:
            if self.start_date is None or self.end_date is None:
                raise ValueError("start_date and end_date must be supplied together")
            if self.lookback_days is not None:
                raise ValueError("use either lookback_days or explicit dates, not both")
            if self.end_date < self.start_date:
                raise ValueError("end_date must be >= start_date")
        if self.comparison == "previous_period" and self.lookback_days is None and not explicit_dates:
            raise ValueError("previous_period comparison requires a bounded period")
        if self.sort_metric is not None and self.sort_metric not in self.metrics:
            raise ValueError("sort_metric must be one of the requested metrics")
        if any(metric in MONEY_METRICS for metric in self.metrics) and not self.currency:
            raise ValueError("currency is required for money metrics")

        time_dims = [dim for dim in self.group_by if dim in {"day", "week", "month"}]
        if len(time_dims) > 1:
            raise ValueError("group_by may contain at most one time dimension")
        if self.comparison == "previous_period" and time_dims:
            raise ValueError("previous_period comparison cannot be combined with a time dimension")

        if "new_patients" in self.metrics:
            if any(dim not in {"day", "week", "month"} for dim in self.group_by):
                raise ValueError("new_patients may only be grouped by time")
            if self.service_ids or self.branch_ids or self.doctor_ids:
                raise ValueError("new_patients does not accept appointment entity filters")

        repeat_metrics = {"repeat_patients", "repeat_rate", "same_service_repeat_rate"}
        if repeat_metrics.intersection(self.metrics) and time_dims:
            raise ValueError("repeat/retention metrics cannot be grouped by time")
        if "same_service_repeat_rate" in self.metrics:
            if "service" not in self.group_by and len(self.service_ids) != 1:
                raise ValueError(
                    "same_service_repeat_rate requires group_by service or exactly one service filter"
                )

        return self


class AnalyticsBusinessAnswerRead(BaseModel):
    question: str
    plan: AnalyticsBusinessPlan
    period_label: str
    answer: str
    definitions: list[str] = Field(default_factory=list)
    rows: list[AnalyticsBIResultRow] = Field(default_factory=list)
    model: str | None = None
