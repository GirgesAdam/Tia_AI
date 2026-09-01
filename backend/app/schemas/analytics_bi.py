from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator

AnalyticsBIOperation = Literal[
    "clinic_summary",
    "revenue_trend",
    "appointment_outcomes",
    "service_performance",
    "service_retention",
    "doctor_performance",
    "branch_performance",
    "top_repeat_patients",
    "top_value_patients",
    "lapsed_patients",
    "new_patients_trend",
    "patient_history_lookup",
]


class AnalyticsBIQuestionRequest(BaseModel):
    question: str = Field(min_length=1, max_length=1200)

    @field_validator("question")
    @classmethod
    def normalize_question(cls, value: str) -> str:
        normalized = " ".join(value.split())
        if not normalized:
            raise ValueError("question must not be empty")
        return normalized


class AnalyticsBIPlan(BaseModel):
    """Typed plan produced by the LLM and executed by deterministic analytics code.

    Every field is required in the provider schema. Null/empty collections mean
    "not specified"; they never broaden access outside the current workspace.
    """

    model_config = ConfigDict(extra="forbid")

    operation: AnalyticsBIOperation
    lookback_days: int | None = Field(ge=1, le=3650)
    inactivity_days: int | None = Field(ge=30, le=3650)
    limit: int = Field(ge=1, le=25)
    service_ids: list[str]
    branch_ids: list[str]
    doctor_ids: list[str]
    currency: str | None
    patient_name: str | None
    patient_phone: str | None
    reason: str = Field(min_length=1, max_length=500)

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


class AnalyticsBIMetricRead(BaseModel):
    key: str
    label: str
    value: int | float | str
    currency: str | None = None


class AnalyticsBIResultRow(BaseModel):
    key: str | None = None
    label: str
    secondary_label: str | None = None
    metrics: list[AnalyticsBIMetricRead] = Field(default_factory=list)


class AnalyticsBIAnswerRead(BaseModel):
    question: str
    plan: AnalyticsBIPlan
    period_label: str
    answer: str
    definitions: list[str] = Field(default_factory=list)
    rows: list[AnalyticsBIResultRow] = Field(default_factory=list)
    model: str | None = None
