from __future__ import annotations

from datetime import datetime
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, field_validator

ExpenseCategory = Literal[
    "rent",
    "payroll",
    "marketing",
    "supplies",
    "utilities",
    "software",
    "other",
]


class ExpenseCreate(BaseModel):
    incurred_at: datetime
    category: ExpenseCategory
    description: str | None = Field(default=None, max_length=240)
    amount_minor: int = Field(gt=0)
    currency: str = Field(default="EGP", min_length=3, max_length=3)

    @field_validator("description")
    @classmethod
    def clean_description(cls, value: str | None) -> str | None:
        if value is None:
            return None
        value = value.strip()
        return value or None

    @field_validator("currency")
    @classmethod
    def normalize_currency(cls, value: str) -> str:
        return value.strip().upper()


class ExpenseUpdate(BaseModel):
    incurred_at: datetime | None = None
    category: ExpenseCategory | None = None
    description: str | None = Field(default=None, max_length=240)
    amount_minor: int | None = Field(default=None, gt=0)
    currency: str | None = Field(default=None, min_length=3, max_length=3)

    @field_validator("description")
    @classmethod
    def clean_description(cls, value: str | None) -> str | None:
        if value is None:
            return None
        value = value.strip()
        return value or None

    @field_validator("currency")
    @classmethod
    def normalize_currency(cls, value: str | None) -> str | None:
        return value.strip().upper() if value is not None else None


class ExpenseRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    workspace_id: UUID
    incurred_at: datetime
    category: ExpenseCategory
    description: str | None
    amount_minor: int
    currency: str
    created_at: datetime
    updated_at: datetime


class ExpenseSummary(BaseModel):
    days: int
    currency: str
    revenue_minor: int
    expenses_minor: int
    operating_profit_minor: int
