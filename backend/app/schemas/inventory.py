from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, field_validator


class ClinicProductCreate(BaseModel):
    name: str = Field(min_length=1, max_length=180)
    description: str | None = Field(default=None, max_length=1000)

    @field_validator("name")
    @classmethod
    def normalize_name(cls, value: str) -> str:
        value = " ".join(value.split())
        if not value:
            raise ValueError("Product name is required.")
        return value


class ClinicProductRead(BaseModel):
    id: UUID
    workspace_id: UUID
    name: str
    description: str | None
    is_active: bool
    created_at: datetime
    updated_at: datetime
    model_config = ConfigDict(from_attributes=True)


class AppointmentProductCreate(BaseModel):
    product_id: UUID
    unit_price_minor: int = Field(ge=0)
    quantity: int = Field(default=1, ge=1, le=100)


class AppointmentProductLineRead(BaseModel):
    id: UUID
    appointment_id: UUID
    product_id: UUID
    product_name: str
    quantity: int
    unit_price_minor: int
    currency: str
    total_minor: int


class InventoryItemCreate(BaseModel):
    name: str = Field(min_length=1, max_length=180)
    quantity_ml: Decimal = Field(ge=0)
    concentration_mg_per_ml: Decimal = Field(gt=0)
    low_stock_threshold_ml: Decimal | None = Field(default=None, ge=0)
    notes: str | None = Field(default=None, max_length=2000)


class InventoryItemAdjust(BaseModel):
    quantity_ml: Decimal = Field(gt=0)


class InventoryUsageCreate(BaseModel):
    used_mg: Decimal = Field(gt=0)
    appointment_id: UUID | None = None
    note: str | None = Field(default=None, max_length=2000)


class InventoryItemRead(BaseModel):
    id: UUID
    workspace_id: UUID
    name: str
    category: str
    quantity_ml: Decimal
    concentration_mg_per_ml: Decimal
    remaining_mg: Decimal
    low_stock_threshold_ml: Decimal | None
    notes: str | None
    is_active: bool
    created_at: datetime
    updated_at: datetime


class InventoryUsageRead(BaseModel):
    id: UUID
    inventory_item_id: UUID
    appointment_id: UUID | None
    used_mg: Decimal
    used_ml: Decimal
    note: str | None
    created_at: datetime


class LaserDevicePriceUpsert(BaseModel):
    service_id: UUID
    device_key: str
    price_minor: int = Field(ge=0)
    currency: str = Field(default="EGP", min_length=3, max_length=3)

    @field_validator("device_key")
    @classmethod
    def validate_device_key(cls, value: str) -> str:
        if value not in {"prime_lase", "candela_gentle"}:
            raise ValueError("Unsupported laser device.")
        return value


class LaserDevicePriceRead(BaseModel):
    service_id: UUID
    service_name: str
    device_key: str
    device_name: str
    price_minor: int | None
    currency: str
    configured: bool
