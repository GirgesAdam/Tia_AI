from __future__ import annotations

from datetime import UTC, datetime
from types import SimpleNamespace
from uuid import uuid4

import pytest

from app.integrations.clinic.mapped_sync import (
    ClinicMappedSyncError,
    MappedClinicSyncSource,
    canonicalize_raw_sync_page,
    schema_fingerprint,
    validate_sync_mapping_schema,
)
from app.integrations.clinic.sync_contract import (
    ClinicRawSyncFetchRequest,
    ClinicRawSyncPage,
    ClinicSyncDomain,
    ClinicSyncFetchRequest,
)
from app.models.clinic_integration import ClinicIntegration
from app.schemas.clinic_connector_mapping import (
    AppointmentSyncMapping,
    ClinicConnectorColumnSchema,
    ClinicConnectorSchemaSnapshot,
    ClinicConnectorTableSchema,
    ClinicSyncMapping,
    PatientSyncMapping,
    PaymentAllocationSyncMapping,
    PaymentSyncMapping,
)


def _snapshot(*, revision: str = "r1") -> ClinicConnectorSchemaSnapshot:
    return ClinicConnectorSchemaSnapshot(
        revision=revision,
        tables=[
            ClinicConnectorTableSchema(
                name="clients",
                columns=[
                    ClinicConnectorColumnSchema(name="id", kind="text", primary_key=True, nullable=False),
                    ClinicConnectorColumnSchema(name="first_name", kind="text", nullable=False),
                    ClinicConnectorColumnSchema(name="phone", kind="text"),
                    ClinicConnectorColumnSchema(name="updated_at", kind="datetime"),
                ],
            ),
            ClinicConnectorTableSchema(
                name="visits",
                columns=[
                    ClinicConnectorColumnSchema(name="id", kind="text", primary_key=True, nullable=False),
                    ClinicConnectorColumnSchema(name="client_id", kind="text"),
                    ClinicConnectorColumnSchema(name="branch_id", kind="text"),
                    ClinicConnectorColumnSchema(name="service_id", kind="text"),
                    ClinicConnectorColumnSchema(name="doctor_id", kind="text"),
                    ClinicConnectorColumnSchema(name="status", kind="text"),
                    ClinicConnectorColumnSchema(name="start_at", kind="datetime"),
                    ClinicConnectorColumnSchema(name="end_at", kind="datetime"),
                ],
            ),
            ClinicConnectorTableSchema(
                name="receipts",
                columns=[
                    ClinicConnectorColumnSchema(name="id", kind="text", primary_key=True, nullable=False),
                    ClinicConnectorColumnSchema(name="client_id", kind="text"),
                    ClinicConnectorColumnSchema(name="amount", kind="decimal"),
                    ClinicConnectorColumnSchema(name="created_at", kind="datetime"),
                ],
            ),
            ClinicConnectorTableSchema(
                name="receipt_allocations",
                columns=[
                    ClinicConnectorColumnSchema(name="receipt_id", kind="text"),
                    ClinicConnectorColumnSchema(name="visit_id", kind="text"),
                    ClinicConnectorColumnSchema(name="amount", kind="decimal"),
                ],
            ),
        ],
    )


def _mapping() -> ClinicSyncMapping:
    return ClinicSyncMapping(
        patients=PatientSyncMapping(
            sheet="clients",
            external_id="id",
            first_name="first_name",
            phone="phone",
            source_updated_at="updated_at",
        ),
        appointments=AppointmentSyncMapping(
            sheet="visits",
            external_id="id",
            patient_external_id="client_id",
            branch_external_id="branch_id",
            service_external_id="service_id",
            doctor_external_id="doctor_id",
            status="status",
            start_at="start_at",
            end_at="end_at",
        ),
        payments=PaymentSyncMapping(
            sheet="receipts",
            external_id="id",
            patient_external_id="client_id",
            amount_minor="amount",
            amount_scale=100,
            created_at="created_at",
        ),
        payment_allocations=PaymentAllocationSyncMapping(
            sheet="receipt_allocations",
            payment_external_id="receipt_id",
            appointment_external_id="visit_id",
            amount_minor="amount",
            amount_scale=100,
        ),
    )


def test_schema_fingerprint_ignores_revision_but_not_structure() -> None:
    first = _snapshot(revision="rev-1")
    second = _snapshot(revision="rev-2")
    assert schema_fingerprint(first) == schema_fingerprint(second)
    second.tables[0].estimated_row_count = 999999
    second.tables[0].columns[0].distinct_count = 12345
    second.tables[0].columns[0].unique_ratio = 0.42
    assert schema_fingerprint(first) == schema_fingerprint(second)
    second.tables.reverse()
    for table in second.tables:
        table.columns.reverse()
    assert schema_fingerprint(first) == schema_fingerprint(second)
    client_table = next(table for table in second.tables if table.name == "clients")
    client_table.columns.append(ClinicConnectorColumnSchema(name="new_col"))
    assert schema_fingerprint(first) != schema_fingerprint(second)


def test_mapping_validation_rejects_unknown_connector_column() -> None:
    mapping = _mapping()
    mapping.payments.amount_minor = "missing_amount"
    with pytest.raises(ClinicMappedSyncError, match="missing_amount"):
        validate_sync_mapping_schema(mapping, _snapshot())


def test_raw_payment_page_becomes_minor_units_with_explicit_allocations() -> None:
    mapping = _mapping()
    fingerprint = schema_fingerprint(_snapshot())
    page = ClinicRawSyncPage(
        domain=ClinicSyncDomain.PAYMENTS,
        schema_fingerprint=fingerprint,
        tables={
            "receipts": (
                {"id": "R1", "client_id": "C1", "amount": "15.00", "created_at": "2026-08-26T10:00:00+03:00"},
            ),
            "receipt_allocations": (
                {"receipt_id": "R1", "visit_id": "V1", "amount": "10.00"},
                {"receipt_id": "R1", "visit_id": "V1", "amount": "2.00"},
                {"receipt_id": "R1", "visit_id": "V2", "amount": "3.00"},
            ),
            "clients": (),
            "visits": (),
        },
    )
    canonical = canonicalize_raw_sync_page(
        raw_page=page,
        mapping=mapping,
        expected_schema_fingerprint=fingerprint,
    )
    payment = canonical.records[0]
    assert payment.amount_minor == 1500
    assert [(item.appointment_external_id, item.amount_minor) for item in payment.allocations] == [
        ("V1", 1200),
        ("V2", 300),
    ]


def test_schema_drift_blocks_runtime_before_any_canonical_write() -> None:
    with pytest.raises(ClinicMappedSyncError, match="schema changed"):
        canonicalize_raw_sync_page(
            raw_page=ClinicRawSyncPage(
                domain=ClinicSyncDomain.PATIENTS,
                tables={"clients": ()},
                schema_fingerprint="new",
            ),
            mapping=_mapping(),
            expected_schema_fingerprint="approved",
        )


class _RawSource:
    raw_sync_domains = frozenset({ClinicSyncDomain.PATIENTS})

    def __init__(self, fingerprint: str):
        self.fingerprint = fingerprint

    def fetch_raw_sync_page(self, request: ClinicRawSyncFetchRequest) -> ClinicRawSyncPage:
        return ClinicRawSyncPage(
            domain=request.domain,
            cursor=request.cursor,
            tables={
                "clients": (
                    {"id": "C1", "first_name": "Mona", "phone": "+201000000000", "updated_at": "2026-08-26T10:00:00+03:00"},
                ),
                "visits": (),
                "receipts": (),
                "receipt_allocations": (),
            },
            schema_fingerprint=self.fingerprint,
        )


def test_mapped_source_exposes_only_intersection_of_mapping_and_connector_domains() -> None:
    fingerprint = schema_fingerprint(_snapshot())
    source = MappedClinicSyncSource(
        source=_RawSource(fingerprint),
        mapping=_mapping(),
        schema_fingerprint_value=fingerprint,
    )
    assert source.sync_domains == frozenset({ClinicSyncDomain.PATIENTS})
    page = source.fetch_sync_page(ClinicSyncFetchRequest(domain=ClinicSyncDomain.PATIENTS))
    assert page.records[0].external_id == "C1"
    assert not hasattr(page.records[0], "email")


def test_scheduled_runtime_wraps_raw_connector_with_approved_mapping(monkeypatch) -> None:
    from app.services import clinic_integration_sync_runtime as runtime

    workspace_id = uuid4()
    snapshot = _snapshot()
    fingerprint = schema_fingerprint(snapshot)
    raw_source = _RawSource(fingerprint)
    integration = SimpleNamespace(
        workspace_id=workspace_id,
        config_json={
            "approved_sync_mapping": _mapping().model_dump(mode="json"),
            "approved_sync_schema_fingerprint": fingerprint,
        },
    )

    class Db:
        @staticmethod
        def get(model, key):
            assert key == workspace_id
            if model is ClinicIntegration:
                return integration
            return None

    monkeypatch.setattr(runtime, "get_clinic_adapter", lambda **_: raw_source)
    source = runtime._source_for_workspace(Db(), SimpleNamespace(id=workspace_id))
    assert isinstance(source, MappedClinicSyncSource)
    page = source.fetch_sync_page(ClinicSyncFetchRequest(domain=ClinicSyncDomain.PATIENTS))
    assert page.records[0].external_id == "C1"
