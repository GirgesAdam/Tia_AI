from __future__ import annotations

from datetime import datetime
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

PackageSessionCount = Literal[3, 6, 9]
LaserDeviceKey = Literal["prime_lase", "candela_gentle"]


class ServicePackageOfferUpsert(BaseModel):
    service_id: UUID
    device_key: LaserDeviceKey
    sessions_count: PackageSessionCount
    price_minor: int = Field(ge=0)
    currency: str = Field(default="EGP", min_length=3, max_length=3)
    is_active: bool = True


class ServicePackageOfferRead(BaseModel):
    id: UUID
    workspace_id: UUID
    service_id: UUID
    service_name: str
    device_key: LaserDeviceKey
    device_name: str
    sessions_count: PackageSessionCount
    price_minor: int
    currency: str
    is_active: bool
    standalone_session_price_minor: int
    savings_minor: int
    created_at: datetime
    updated_at: datetime

    model_config = ConfigDict(from_attributes=True)


class PatientPackageOfferPurchase(BaseModel):
    patient_id: UUID
    offer_id: UUID
    amount_paid_minor: int = Field(default=0, ge=0)
    payment_method: str = "unknown"
    external_reference: str | None = Field(default=None, max_length=128)
