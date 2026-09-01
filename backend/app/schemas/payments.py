from __future__ import annotations

from datetime import datetime
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, field_validator

PaymentMethod = Literal["cash", "card", "bank_transfer", "wallet", "online", "other"]
PaymentTransactionType = Literal["payment", "refund"]


class PaymentCreate(BaseModel):
    amount_minor: int = Field(gt=0)
    payment_method: PaymentMethod
    external_reference: str | None = Field(default=None, max_length=128)

    @field_validator("external_reference", mode="before")
    @classmethod
    def normalize_external_reference(cls, value: object) -> object:
        if isinstance(value, str):
            value = value.strip()
            return value or None
        return value


class RefundCreate(BaseModel):
    payment_transaction_id: UUID
    amount_minor: int = Field(gt=0)
    reason: str = Field(min_length=1, max_length=500)

    @field_validator("reason")
    @classmethod
    def normalize_reason(cls, value: str) -> str:
        value = value.strip()
        if not value:
            raise ValueError("Refund reason cannot be empty.")
        return value


class PaymentTransactionRead(BaseModel):
    id: UUID
    workspace_id: UUID
    appointment_id: UUID | None
    origin_appointment_id: UUID | None
    patient_id: UUID
    created_by_user_id: UUID | None
    reference_transaction_id: UUID | None
    patient_package_id: UUID | None = None
    transaction_type: PaymentTransactionType
    amount_minor: int
    allocated_amount_minor: int | None = None
    currency: str
    payment_method: str
    source: str
    external_reference: str | None
    reason: str | None
    created_at: datetime
    refunded_minor: int = 0
    refundable_minor: int = 0

    model_config = ConfigDict(from_attributes=True)


class AppointmentPaymentSummaryRead(BaseModel):
    appointment_id: UUID
    patient_id: UUID
    currency: str
    price_minor: int
    gross_paid_minor: int
    refunded_minor: int
    net_paid_minor: int
    balance_minor: int
    payment_status: str
    billing_context: str = "standard"
    package_external_id: str | None = None
    transactions: list[PaymentTransactionRead]
    can_refund: bool = False
