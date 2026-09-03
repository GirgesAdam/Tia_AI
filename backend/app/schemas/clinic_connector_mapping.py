from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, Field, model_validator

from app.schemas.clinic_import import StructuralTransformMapping

ConnectorColumnKind = Literal[
    "text",
    "integer",
    "decimal",
    "boolean",
    "date",
    "datetime",
    "time",
    "json",
    "unknown",
]


class ClinicConnectorColumnSchema(BaseModel):
    name: str = Field(min_length=1, max_length=255)
    kind: ConnectorColumnKind = "unknown"
    nullable: bool = True
    primary_key: bool = False
    references_table: str | None = Field(default=None, max_length=255)
    references_column: str | None = Field(default=None, max_length=255)
    distinct_count: int | None = Field(default=None, ge=0)
    unique_ratio: float | None = Field(default=None, ge=0, le=1)
    phone_like_ratio: float | None = Field(default=None, ge=0, le=1)
    identifier_like_ratio: float | None = Field(default=None, ge=0, le=1)

    @model_validator(mode="after")
    def validate_reference(self):
        if bool(self.references_table) != bool(self.references_column):
            raise ValueError("Connector column foreign-key references require table and column together.")
        return self


class ClinicConnectorTableSchema(BaseModel):
    name: str = Field(min_length=1, max_length=255)
    columns: list[ClinicConnectorColumnSchema] = Field(min_length=1, max_length=300)
    estimated_row_count: int | None = Field(default=None, ge=0)

    @model_validator(mode="after")
    def validate_unique_columns(self):
        names = [column.name for column in self.columns]
        if len(names) != len(set(names)):
            raise ValueError(f"Connector schema table {self.name!r} has duplicate column names.")
        return self


class ClinicConnectorSchemaSnapshot(BaseModel):
    revision: str | None = Field(default=None, max_length=255)
    tables: list[ClinicConnectorTableSchema] = Field(min_length=1, max_length=200)

    @model_validator(mode="after")
    def validate_unique_tables(self):
        names = [table.name for table in self.tables]
        if len(names) != len(set(names)):
            raise ValueError("Connector schema has duplicate table names.")
        return self


class PatientSyncMapping(BaseModel):
    sheet: str = Field(min_length=1, max_length=255)
    external_id: str = Field(min_length=1, max_length=255)
    first_name: str = Field(min_length=1, max_length=255)
    last_name: str | None = Field(default=None, max_length=255)
    phone: str | None = Field(default=None, max_length=255)
    gender: str | None = Field(default=None, max_length=255)
    birth_date: str | None = Field(default=None, max_length=255)
    status: str | None = Field(default=None, max_length=255)
    preferred_language: str | None = Field(default=None, max_length=255)
    source: str | None = Field(default=None, max_length=255)
    source_created_at: str | None = Field(default=None, max_length=255)
    source_updated_at: str | None = Field(default=None, max_length=255)
    default_status: str = Field(default="active", min_length=1, max_length=32)
    default_preferred_language: str = Field(default="ar", min_length=1, max_length=16)
    default_source: str = Field(default="other", min_length=1, max_length=32)


class AppointmentSyncMapping(BaseModel):
    sheet: str = Field(min_length=1, max_length=255)
    external_id: str = Field(min_length=1, max_length=255)
    patient_external_id: str = Field(min_length=1, max_length=255)
    branch_external_id: str = Field(min_length=1, max_length=255)
    service_external_id: str = Field(min_length=1, max_length=255)
    doctor_external_id: str = Field(min_length=1, max_length=255)
    status: str = Field(min_length=1, max_length=255)
    start_at: str = Field(min_length=1, max_length=255)
    end_at: str = Field(min_length=1, max_length=255)
    status_at: str | None = Field(default=None, max_length=255)
    price_minor: str | None = Field(default=None, max_length=255)
    currency: str | None = Field(default=None, max_length=255)
    source_updated_at: str | None = Field(default=None, max_length=255)
    price_scale: int = Field(default=1, ge=1, le=10000)
    default_currency: str = Field(default="EGP", min_length=3, max_length=3)


class PaymentSyncMapping(BaseModel):
    sheet: str = Field(min_length=1, max_length=255)
    external_id: str = Field(min_length=1, max_length=255)
    patient_external_id: str = Field(min_length=1, max_length=255)
    transaction_type: str | None = Field(default=None, max_length=255)
    amount_minor: str = Field(min_length=1, max_length=255)
    currency: str | None = Field(default=None, max_length=255)
    payment_method: str | None = Field(default=None, max_length=255)
    created_at: str = Field(min_length=1, max_length=255)
    external_reference: str | None = Field(default=None, max_length=255)
    reference_payment_external_id: str | None = Field(default=None, max_length=255)
    amount_scale: int = Field(default=1, ge=1, le=10000)
    default_transaction_type: Literal["payment", "refund"] = "payment"
    default_currency: str = Field(default="EGP", min_length=3, max_length=3)
    default_payment_method: str = Field(default="unknown", min_length=1, max_length=32)


class PaymentAllocationSyncMapping(BaseModel):
    sheet: str = Field(min_length=1, max_length=255)
    payment_external_id: str = Field(min_length=1, max_length=255)
    appointment_external_id: str = Field(min_length=1, max_length=255)
    amount_minor: str = Field(min_length=1, max_length=255)
    amount_scale: int = Field(default=1, ge=1, le=10000)




class ClinicReferenceIdentityMapping(BaseModel):
    sheet: str = Field(min_length=1, max_length=255)
    external_id: str = Field(min_length=1, max_length=255)
    label: str | None = Field(default=None, max_length=255)


class ClinicReferenceIdentityMappings(BaseModel):
    branches: ClinicReferenceIdentityMapping | None = None
    services: ClinicReferenceIdentityMapping | None = None
    doctors: ClinicReferenceIdentityMapping | None = None

class ClinicSyncMapping(BaseModel):
    transformations: list[StructuralTransformMapping] = Field(default_factory=list, max_length=40)
    references: ClinicReferenceIdentityMappings = Field(default_factory=ClinicReferenceIdentityMappings)
    patients: PatientSyncMapping | None = None
    appointments: AppointmentSyncMapping | None = None
    payments: PaymentSyncMapping | None = None
    payment_allocations: PaymentAllocationSyncMapping | None = None

    @model_validator(mode="after")
    def validate_mapping(self):
        names = [item.name for item in self.transformations]
        if len(names) != len(set(names)):
            raise ValueError("Connector structural transform names must be unique.")
        if self.payment_allocations is not None and self.payments is None:
            raise ValueError("Payment allocation mapping requires a payments mapping.")
        if self.patients is None and self.appointments is None and self.payments is None:
            raise ValueError("Connector mapping must configure at least one sync domain.")
        return self


class ClinicConnectorMappingProposalRead(BaseModel):
    proposed_mapping: dict[str, Any]
    notes: list[str] = Field(default_factory=list, max_length=20)
    unresolved: list[str] = Field(default_factory=list, max_length=40)
    can_confirm: bool
    schema_snapshot: ClinicConnectorSchemaSnapshot
    schema_fingerprint: str
    model: str | None = None


class ClinicConnectorMappingProviderTransport(BaseModel):
    """Shallow provider transport; mapping_json is strictly validated locally."""

    mapping_json: str = Field(min_length=2, max_length=60_000)
    notes: list[str] = Field(default_factory=list, max_length=20)
    unresolved: list[str] = Field(default_factory=list, max_length=40)
