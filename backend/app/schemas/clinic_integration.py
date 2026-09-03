from __future__ import annotations

from datetime import datetime
from typing import Any, Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from app.integrations.clinic.registry import registered_clinic_adapter_keys

ClinicIntegrationMode = Literal["tia_native", "external_api", "hybrid", "imported"]
ClinicIntegrationStatus = Literal["active", "setup_required", "paused", "error"]
ClinicEntityType = Literal["service", "branch", "doctor", "patient", "appointment", "payment", "patient_package", "package_usage"]

_SENSITIVE_CONFIG_MARKERS = (
    "token",
    "secret",
    "password",
    "passwd",
    "api_key",
    "apikey",
    "access_key",
    "private_key",
    "credential",
)


def _clean_optional(value: str | None) -> str | None:
    if value is None:
        return None
    value = value.strip()
    return value or None


def _validate_non_secret_config(config: dict[str, Any]) -> dict[str, Any]:
    def walk(value: Any) -> None:
        if isinstance(value, dict):
            for key, nested in value.items():
                normalized = str(key).strip().lower()
                if any(marker in normalized for marker in _SENSITIVE_CONFIG_MARKERS):
                    raise ValueError(
                        "Clinic integration config cannot contain credentials or secrets. "
                        "Store them in a secret manager and save only secret_ref here."
                    )
                walk(nested)
        elif isinstance(value, list):
            for item in value:
                walk(item)

    walk(config)
    return config


class ClinicIntegrationUpsert(BaseModel):
    mode: ClinicIntegrationMode
    adapter_key: str = Field(min_length=1, max_length=80)
    status: ClinicIntegrationStatus = "setup_required"
    external_clinic_id: str | None = Field(default=None, max_length=255)
    secret_ref: str | None = Field(default=None, max_length=512)
    config: dict[str, Any] = Field(default_factory=dict)

    @field_validator("adapter_key")
    @classmethod
    def normalize_adapter_key(cls, value: str) -> str:
        value = value.strip().lower()
        if not value:
            raise ValueError("adapter_key cannot be empty.")
        return value

    @field_validator("external_clinic_id", "secret_ref")
    @classmethod
    def normalize_optional_text(cls, value: str | None) -> str | None:
        return _clean_optional(value)

    @field_validator("config")
    @classmethod
    def reject_secrets_in_config(cls, value: dict[str, Any]) -> dict[str, Any]:
        return _validate_non_secret_config(value)

    @model_validator(mode="after")
    def validate_mode_and_adapter(self) -> ClinicIntegrationUpsert:
        if self.mode in {"tia_native", "imported"} and self.adapter_key != "tia_database":
            raise ValueError(
                f"mode={self.mode!r} currently requires adapter_key='tia_database'."
            )
        if self.status == "active" and self.adapter_key not in registered_clinic_adapter_keys():
            raise ValueError(
                "An integration cannot be active until its adapter is installed. "
                "Use status='setup_required' while configuring a future external adapter."
            )
        if self.adapter_key == "prototype_external":
            if self.mode != "external_api":
                raise ValueError(
                    "adapter_key='prototype_external' is a Phase 2.6 external_api prototype."
                )
            if self.status == "active" and not isinstance(
                self.config.get("prototype_dataset"), dict
            ):
                raise ValueError(
                    "An active prototype_external integration requires "
                    "config.prototype_dataset."
                )
        return self


class ClinicIntegrationRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    workspace_id: UUID
    mode: ClinicIntegrationMode
    adapter_key: str
    status: ClinicIntegrationStatus
    external_clinic_id: str | None
    secret_ref: str | None
    config_json: dict[str, Any]
    created_at: datetime
    updated_at: datetime


class ClinicEntityLinkUpsert(BaseModel):
    entity_type: ClinicEntityType
    canonical_id: str = Field(min_length=1, max_length=255)
    external_id: str = Field(min_length=1, max_length=512)
    metadata: dict[str, Any] = Field(default_factory=dict)

    @field_validator("canonical_id", "external_id")
    @classmethod
    def normalize_required_text(cls, value: str) -> str:
        value = value.strip()
        if not value:
            raise ValueError("Entity ids cannot be empty.")
        return value


class ClinicEntityLinkRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    workspace_id: UUID
    entity_type: ClinicEntityType
    canonical_id: str
    external_id: str
    metadata_json: dict[str, Any]
    created_at: datetime
    updated_at: datetime




AuthorityOwner = Literal["tia", "external"]


class ClinicAuthorityDomainPolicy(BaseModel):
    owner: AuthorityOwner
    fields: dict[str, AuthorityOwner] = Field(default_factory=dict)


class ClinicIntegrationAuthorityUpsert(BaseModel):
    patients: ClinicAuthorityDomainPolicy
    payments: ClinicAuthorityDomainPolicy
    appointments: ClinicAuthorityDomainPolicy

    @model_validator(mode="after")
    def validate_supported_field_authority(self) -> ClinicIntegrationAuthorityUpsert:
        from app.integrations.clinic.authority import PATIENT_EXTERNAL_SYNC_FIELDS

        unsupported_patient = set(self.patients.fields) - set(PATIENT_EXTERNAL_SYNC_FIELDS)
        if unsupported_patient:
            raise ValueError("Patient authority policy contains unsupported fields.")
        if self.payments.fields:
            raise ValueError("Field-level payment authority is not supported yet.")
        if self.appointments.fields:
            raise ValueError("Field-level appointment authority is not supported yet.")
        return self


class ClinicIntegrationAuthorityRead(ClinicIntegrationAuthorityUpsert):
    pass


ClinicSyncDomainName = Literal["patients", "payments", "appointments"]


class ClinicSyncScheduleUpsert(BaseModel):
    enabled: bool = False
    interval_minutes: int = Field(default=15, ge=5, le=1440)


class ClinicSyncScheduleRead(BaseModel):
    enabled: bool
    interval_minutes: int
    next_run_at: datetime | None = None
    locked: bool = False
    locked_at: datetime | None = None
    attempts: int = 0
    last_error: str | None = None
    last_completed_at: datetime | None = None


class ClinicSyncRuntimeDomainRead(BaseModel):
    domain: Literal["patients", "payments", "appointments"]
    authority_owner: AuthorityOwner
    authority_fields: dict[str, AuthorityOwner] = Field(default_factory=dict)
    checkpoint_present: bool = False
    cursor_digest: str | None = None
    source_revision: str | None = None
    last_success_at: datetime | None = None
    last_run_id: UUID | None = None
    last_run_status: Literal["running", "succeeded", "partial", "failed"] | None = None
    last_run_started_at: datetime | None = None
    last_run_completed_at: datetime | None = None
    processed_count: int = 0
    created_count: int = 0
    updated_count: int = 0
    skipped_count: int = 0
    failed_count: int = 0
    latest_error_code: str | None = None
    latest_error_message: str | None = None
    latest_error_retryable: bool | None = None
    latest_error_at: datetime | None = None


class ClinicIntegrationDataQualityRead(BaseModel):
    open_count: int = 0
    affected_rows: int = 0
    critical: int = 0
    normal: int = 0
    simple: int = 0
    categories: dict[str, int] = Field(default_factory=dict)
    status: str = "clean"


class ClinicDataIssueRead(BaseModel):
    id: UUID
    severity: Literal["critical", "normal", "simple"]
    status: Literal["open", "resolved", "ignored", "auto_resolved"]
    category: str
    code: str
    title: str
    description: str
    entity_type: str | None = None
    entity_external_id: str | None = None
    related_external_id: str | None = None
    occurrence_count: int = 1
    repair_options: list[dict[str, Any]] = Field(default_factory=list)
    created_at: datetime
    resolved_at: datetime | None = None


class ClinicDataIssueListRead(BaseModel):
    summary: ClinicIntegrationDataQualityRead
    issues: list[ClinicDataIssueRead] = Field(default_factory=list)


class ClinicDataIssueResolveRequest(BaseModel):
    option_index: int = Field(ge=0, le=29)


class ClinicIntegrationRuntimeRead(BaseModel):
    mode: ClinicIntegrationMode
    adapter_key: str
    status: ClinicIntegrationStatus
    adapter_installed: bool
    adapter_active: bool
    cache_namespace: str | None = None
    capabilities: dict[str, bool] = Field(default_factory=dict)
    entity_link_counts: dict[str, int] = Field(default_factory=dict)
    authority_policy: ClinicIntegrationAuthorityRead
    sync_domains: list[ClinicSyncRuntimeDomainRead] = Field(default_factory=list)
    sync_source_domains: list[ClinicSyncDomainName] = Field(default_factory=list)
    approved_mapping_active: bool = False
    approved_mapping_domains: list[ClinicSyncDomainName] = Field(default_factory=list)
    approved_schema_fingerprint_digest: str | None = None
    sync_schedule: ClinicSyncScheduleRead | None = None
    data_quality: ClinicIntegrationDataQualityRead = Field(default_factory=ClinicIntegrationDataQualityRead)

class ClinicSyncRunRequest(BaseModel):
    domains: list[ClinicSyncDomainName] | None = None
    page_size: int = Field(default=100, ge=1, le=500)
    max_pages_per_domain: int = Field(default=10, ge=1, le=100)

    @field_validator("domains")
    @classmethod
    def normalize_domains(cls, value: list[ClinicSyncDomainName] | None):
        if value is None:
            return None
        ordered: list[ClinicSyncDomainName] = []
        for domain in value:
            if domain not in ordered:
                ordered.append(domain)
        return ordered


class ClinicSyncDomainCycleRead(BaseModel):
    domain: ClinicSyncDomainName
    status: Literal["succeeded", "partial", "failed", "skipped"]
    pages: int = 0
    processed_count: int = 0
    created_count: int = 0
    updated_count: int = 0
    skipped_count: int = 0
    failed_count: int = 0
    complete: bool = True
    error: str | None = None


class ClinicSyncCycleRead(BaseModel):
    status: Literal["succeeded", "partial", "failed", "skipped"]
    domains: list[ClinicSyncDomainCycleRead] = Field(default_factory=list)
    complete: bool = True
    started_at: datetime
    completed_at: datetime


class ClinicSyncWorkerTickRequest(BaseModel):
    page_size: int = Field(default=100, ge=1, le=500)
    max_pages_per_domain: int = Field(default=10, ge=1, le=100)


class ClinicSyncWorkerTickResponse(BaseModel):
    claimed: bool
    reason: str | None = None
    cycle: ClinicSyncCycleRead | None = None


