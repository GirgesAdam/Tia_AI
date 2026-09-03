from __future__ import annotations

from contextlib import contextmanager
from datetime import UTC, datetime

import pytest

from app.integrations.clinic.mapped_sync import schema_fingerprint
from app.integrations.clinic.postgres_readonly import (
    PostgresReadonlyClinicAdapter,
    PostgresReadonlyConnectorError,
    _ColumnMeta,
    _TableMeta,
)
from app.integrations.clinic.registry import registered_clinic_adapter_keys
from app.integrations.clinic.sync_contract import ClinicRawSyncFetchRequest, ClinicSyncDomain
from app.integrations.secrets import SecretResolutionError, resolve_secret_ref
from app.schemas.clinic_connector_mapping import (
    ClinicConnectorColumnSchema,
    ClinicConnectorSchemaSnapshot,
    ClinicConnectorTableSchema,
    ClinicSyncMapping,
    PatientSyncMapping,
    PaymentAllocationSyncMapping,
    PaymentSyncMapping,
)


class _Cursor:
    def __init__(self, responses: dict[str, list[dict]]):
        self.responses = responses
        self.current: list[dict] = []
        self.executed: list[tuple[str, tuple | None]] = []

    def execute(self, query: str, params=None):
        text = str(query)
        self.executed.append((text, params))
        self.current = []
        for marker, rows in self.responses.items():
            if marker in text:
                self.current = list(rows)
                break

    def fetchall(self):
        return list(self.current)

    def close(self):
        return None


class _Connection:
    def __init__(self, cursor: _Cursor):
        self._cursor = cursor
        self.read_only = False
        self.rolled_back = False
        self.closed = False

    def cursor(self):
        return self._cursor

    def rollback(self):
        self.rolled_back = True

    def close(self):
        self.closed = True


def _adapter(monkeypatch, *, config: dict | None = None) -> PostgresReadonlyClinicAdapter:
    monkeypatch.setenv("TIA_TEST_CLINIC_DB", "postgresql://readonly:secret@db.example/clinic")
    return PostgresReadonlyClinicAdapter(
        secret_ref="env:TIA_TEST_CLINIC_DB",
        config=config or {},
    )


def _simple_snapshot(*, patient_pk: bool = True) -> ClinicConnectorSchemaSnapshot:
    return ClinicConnectorSchemaSnapshot(
        tables=[
            ClinicConnectorTableSchema(
                name="clients",
                estimated_row_count=3,
                columns=[
                    ClinicConnectorColumnSchema(
                        name="id", kind="integer", nullable=False, primary_key=patient_pk
                    ),
                    ClinicConnectorColumnSchema(name="first_name", kind="text", nullable=False),
                    ClinicConnectorColumnSchema(name="phone", kind="text"),
                ],
            )
        ]
    )


def _simple_mapping() -> ClinicSyncMapping:
    return ClinicSyncMapping(
        patients=PatientSyncMapping(
            sheet="clients",
            external_id="id",
            first_name="first_name",
            phone="phone",
        )
    )


def _patient_table() -> _TableMeta:
    return _TableMeta(
        display_name="clients",
        schema_name="public",
        table_name="clients",
        columns=(
            _ColumnMeta(
                name="id",
                raw_type="int8",
                kind="integer",
                nullable=False,
                primary_key=True,
                pk_position=1,
            ),
            _ColumnMeta(name="first_name", raw_type="varchar", kind="text", nullable=False),
            _ColumnMeta(name="phone", raw_type="varchar", kind="text", nullable=True),
            _ColumnMeta(name="medical_notes", raw_type="text", kind="text", nullable=True),
        ),
        estimated_row_count=3,
    )


def test_env_secret_resolver_is_server_side_and_fail_closed(monkeypatch) -> None:
    monkeypatch.setenv("CLINIC_SECRET_DSN", "postgresql://readonly:pw@localhost/clinic")
    assert resolve_secret_ref("env:CLINIC_SECRET_DSN").endswith("/clinic")
    assert resolve_secret_ref("env://CLINIC_SECRET_DSN").endswith("/clinic")
    with pytest.raises(SecretResolutionError, match="not installed"):
        resolve_secret_ref("vault://clinic/prod")
    with pytest.raises(SecretResolutionError, match="not configured"):
        resolve_secret_ref("env:NOT_CONFIGURED_TIA_SECRET")


def test_registry_exposes_first_real_postgres_connector() -> None:
    assert "postgres_readonly" in registered_clinic_adapter_keys()


def test_postgres_schema_discovery_reads_catalog_only_and_marks_fk(monkeypatch) -> None:
    adapter = _adapter(monkeypatch)
    cursor = _Cursor(
        {
            "tia:postgres-schema-columns": [
                {
                    "table_schema": "public",
                    "table_name": "clients",
                    "column_name": "id",
                    "data_type": "bigint",
                    "udt_name": "int8",
                    "is_nullable": "NO",
                    "ordinal_position": 1,
                },
                {
                    "table_schema": "public",
                    "table_name": "visits",
                    "column_name": "client_id",
                    "data_type": "bigint",
                    "udt_name": "int8",
                    "is_nullable": "NO",
                    "ordinal_position": 1,
                },
            ],
            "tia:postgres-schema-primary-keys": [
                {
                    "table_schema": "public",
                    "table_name": "clients",
                    "column_name": "id",
                    "ordinal_position": 1,
                }
            ],
            "tia:postgres-schema-foreign-keys": [
                {
                    "table_schema": "public",
                    "table_name": "visits",
                    "column_name": "client_id",
                    "foreign_table_schema": "public",
                    "foreign_table_name": "clients",
                    "foreign_column_name": "id",
                }
            ],
            "tia:postgres-schema-estimates": [
                {"table_schema": "public", "table_name": "clients", "estimated_row_count": 120},
                {"table_schema": "public", "table_name": "visits", "estimated_row_count": 350},
            ],
        }
    )
    connection = _Connection(cursor)
    monkeypatch.setattr(adapter, "_connect", lambda: connection)

    snapshot = adapter.discover_sync_schema()

    assert [table.name for table in snapshot.tables] == ["clients", "visits"]
    clients = next(table for table in snapshot.tables if table.name == "clients")
    visits = next(table for table in snapshot.tables if table.name == "visits")
    assert clients.columns[0].primary_key is True
    assert visits.columns[0].references_table == "clients"
    assert visits.columns[0].references_column == "id"
    assert clients.estimated_row_count == 120
    assert snapshot.revision and snapshot.revision.startswith("postgres:")
    assert connection.read_only is True
    executed_sql = "\n".join(query for query, _params in cursor.executed)
    assert "SET TRANSACTION READ ONLY" in executed_sql
    assert "information_schema.columns" in executed_sql
    assert "SELECT *" not in executed_sql


def test_runtime_validation_requires_deterministic_primary_key(monkeypatch) -> None:
    adapter = _adapter(monkeypatch)
    with pytest.raises(PostgresReadonlyConnectorError, match="needs a primary key"):
        adapter.validate_sync_mapping_runtime(_simple_mapping(), _simple_snapshot(patient_pk=False))


def test_raw_patient_pages_use_keyset_cursor_and_never_offset(monkeypatch) -> None:
    mapping = _simple_mapping()
    adapter = _adapter(monkeypatch, config={"approved_sync_mapping": mapping.model_dump(mode="json")})
    table = _patient_table()
    snapshot = _simple_snapshot()
    snapshot.revision = "postgres:test"
    monkeypatch.setattr(adapter, "_load_table_metadata", lambda: {"clients": table})
    monkeypatch.setattr(adapter, "discover_sync_schema", lambda: snapshot)

    first_cursor = _Cursor(
        {
            "tia:postgres-root-page": [
                {"id": 1, "first_name": "Mona", "phone": "+201000000001"},
                {"id": 2, "first_name": "Nour", "phone": "+201000000002"},
                {"id": 3, "first_name": "Sara", "phone": "+201000000003"},
            ]
        }
    )

    @contextmanager
    def first_read_cursor():
        yield first_cursor

    monkeypatch.setattr(adapter, "_read_cursor", first_read_cursor)
    first = adapter.fetch_raw_sync_page(
        ClinicRawSyncFetchRequest(domain=ClinicSyncDomain.PATIENTS, limit=2)
    )
    assert [row["id"] for row in first.tables["clients"]] == [1, 2]
    assert first.has_more is True
    assert first.next_cursor
    assert "OFFSET" not in first_cursor.executed[-1][0].upper()
    assert '"medical_notes"' not in first_cursor.executed[-1][0]

    second_cursor = _Cursor(
        {"tia:postgres-root-page": [{"id": 3, "first_name": "Sara", "phone": "+201000000003"}]}
    )

    @contextmanager
    def second_read_cursor():
        yield second_cursor

    monkeypatch.setattr(adapter, "_read_cursor", second_read_cursor)
    second = adapter.fetch_raw_sync_page(
        ClinicRawSyncFetchRequest(
            domain=ClinicSyncDomain.PATIENTS,
            cursor=first.next_cursor,
            limit=2,
        )
    )
    assert [row["id"] for row in second.tables["clients"]] == [3]
    assert second.has_more is False
    query, params = second_cursor.executed[-1]
    assert "WHERE (\"id\") > (%s)" in query
    assert params[0] == 2


def test_payment_allocations_are_filtered_to_current_payment_page(monkeypatch) -> None:
    mapping = ClinicSyncMapping(
        payments=PaymentSyncMapping(
            sheet="receipts",
            external_id="id",
            patient_external_id="client_id",
            amount_minor="amount_minor",
            created_at="created_at",
        ),
        payment_allocations=PaymentAllocationSyncMapping(
            sheet="receipt_allocations",
            payment_external_id="receipt_id",
            appointment_external_id="visit_id",
            amount_minor="amount_minor",
        ),
    )
    adapter = _adapter(monkeypatch, config={"approved_sync_mapping": mapping.model_dump(mode="json")})
    receipts = _TableMeta(
        display_name="receipts",
        schema_name="public",
        table_name="receipts",
        columns=(
            _ColumnMeta("id", "int8", "integer", False, True, 1),
            _ColumnMeta("client_id", "int8", "integer", False),
            _ColumnMeta("amount_minor", "int8", "integer", False),
            _ColumnMeta("created_at", "timestamptz", "datetime", False),
        ),
        estimated_row_count=100000,
    )
    allocations = _TableMeta(
        display_name="receipt_allocations",
        schema_name="public",
        table_name="receipt_allocations",
        columns=(
            _ColumnMeta("receipt_id", "int8", "integer", False),
            _ColumnMeta("visit_id", "int8", "integer", False),
            _ColumnMeta("amount_minor", "int8", "integer", False),
        ),
        estimated_row_count=900000,
    )
    snapshot = ClinicConnectorSchemaSnapshot(
        tables=[
            ClinicConnectorTableSchema(
                name="receipts",
                estimated_row_count=100000,
                columns=[
                    ClinicConnectorColumnSchema(name="id", kind="integer", nullable=False, primary_key=True),
                    ClinicConnectorColumnSchema(name="client_id", kind="integer", nullable=False),
                    ClinicConnectorColumnSchema(name="amount_minor", kind="integer", nullable=False),
                    ClinicConnectorColumnSchema(name="created_at", kind="datetime", nullable=False),
                ],
            ),
            ClinicConnectorTableSchema(
                name="receipt_allocations",
                estimated_row_count=900000,
                columns=[
                    ClinicConnectorColumnSchema(name="receipt_id", kind="integer", nullable=False),
                    ClinicConnectorColumnSchema(name="visit_id", kind="integer", nullable=False),
                    ClinicConnectorColumnSchema(name="amount_minor", kind="integer", nullable=False),
                ],
            ),
        ]
    )
    snapshot.revision = "postgres:alloc"
    monkeypatch.setattr(
        adapter,
        "_load_table_metadata",
        lambda: {"receipts": receipts, "receipt_allocations": allocations},
    )
    monkeypatch.setattr(adapter, "discover_sync_schema", lambda: snapshot)
    cursor = _Cursor(
        {
            "tia:postgres-root-page": [
                {
                    "id": 10,
                    "client_id": 7,
                    "amount_minor": 1500,
                    "created_at": datetime(2026, 8, 26, 12, 0, tzinfo=UTC),
                }
            ],
            "tia:postgres-payment-allocations": [
                {"receipt_id": 10, "visit_id": 99, "amount_minor": 1000},
                {"receipt_id": 10, "visit_id": 100, "amount_minor": 500},
            ],
        }
    )

    @contextmanager
    def read_cursor():
        yield cursor

    monkeypatch.setattr(adapter, "_read_cursor", read_cursor)
    page = adapter.fetch_raw_sync_page(
        ClinicRawSyncFetchRequest(domain=ClinicSyncDomain.PAYMENTS, limit=50)
    )
    assert len(page.tables["receipt_allocations"]) == 2
    allocation_query = next(query for query, _params in cursor.executed if "payment-allocations" in query)
    assert "= ANY(%s)" in allocation_query
    assert "OFFSET" not in allocation_query.upper()


def test_cursor_is_bound_to_schema_fingerprint(monkeypatch) -> None:
    mapping = _simple_mapping()
    adapter = _adapter(monkeypatch, config={"approved_sync_mapping": mapping.model_dump(mode="json")})
    table = _patient_table()
    first_snapshot = _simple_snapshot()
    first_fingerprint = schema_fingerprint(first_snapshot)
    cursor = adapter._encode_cursor(
        domain=ClinicSyncDomain.PATIENTS,
        root=table,
        fingerprint=first_fingerprint,
        row={"id": 9},
    )
    changed = _simple_snapshot()
    changed.tables[0].columns.append(ClinicConnectorColumnSchema(name="new_column"))
    with pytest.raises(PostgresReadonlyConnectorError, match="does not match"):
        adapter._decode_cursor(
            cursor=cursor,
            domain=ClinicSyncDomain.PATIENTS,
            root=table,
            fingerprint=schema_fingerprint(changed),
        )


def test_reference_candidates_are_explicit_distinct_reads(monkeypatch) -> None:
    from app.schemas.clinic_connector_mapping import (
        ClinicReferenceIdentityMapping,
        ClinicReferenceIdentityMappings,
    )

    mapping = ClinicSyncMapping(
        patients=PatientSyncMapping(sheet="clients", external_id="id", first_name="first_name"),
        references=ClinicReferenceIdentityMappings(
            branches=ClinicReferenceIdentityMapping(
                sheet="branches", external_id="branch_code", label="branch_name"
            )
        ),
    )
    adapter = _adapter(monkeypatch)
    branches = _TableMeta(
        display_name="branches",
        schema_name="public",
        table_name="branches",
        columns=(
            _ColumnMeta("branch_code", "varchar", "text", False, True, 1),
            _ColumnMeta("branch_name", "varchar", "text", False),
        ),
        estimated_row_count=3,
    )
    monkeypatch.setattr(adapter, "_load_table_metadata", lambda: {"branches": branches})
    cursor = _Cursor(
        {
            "tia:postgres-reference-candidates": [
                {"external_id": "B1", "label": "New Cairo"},
                {"external_id": "B2", "label": "Zamalek"},
            ]
        }
    )

    @contextmanager
    def read_cursor():
        yield cursor

    monkeypatch.setattr(adapter, "_read_cursor", read_cursor)
    candidates = adapter.list_reference_candidates(
        mapping=mapping, entity_type="branch", limit=500
    )
    assert [(item.external_id, item.label) for item in candidates] == [
        ("B1", "New Cairo"),
        ("B2", "Zamalek"),
    ]
    query, params = cursor.executed[-1]
    assert "SELECT DISTINCT" in query
    assert '"branch_code"' in query
    assert '"branch_name"' in query
    assert params == (501,)


def test_mapping_schema_validates_reference_identity_columns() -> None:
    from app.integrations.clinic.mapped_sync import (
        ClinicMappedSyncError,
        validate_sync_mapping_schema,
    )
    from app.schemas.clinic_connector_mapping import (
        ClinicReferenceIdentityMapping,
        ClinicReferenceIdentityMappings,
    )

    mapping = _simple_mapping()
    mapping.references = ClinicReferenceIdentityMappings(
        branches=ClinicReferenceIdentityMapping(
            sheet="clients", external_id="id", label="missing_label"
        )
    )
    with pytest.raises(ClinicMappedSyncError, match="missing_label"):
        validate_sync_mapping_schema(mapping, _simple_snapshot())


def test_hybrid_postgres_connector_can_delegate_tia_owned_agent_reads(monkeypatch) -> None:
    from app.integrations.clinic.base import ClinicCapabilities, ClinicCapability

    class _NativeDelegate:
        capabilities = ClinicCapabilities(frozenset({ClinicCapability.CATALOG_READ}))

        def build_catalog(self):
            return {"services": [{"id": "tia-service"}]}

    monkeypatch.setenv("TIA_TEST_CLINIC_DB", "postgresql://readonly:secret@db.example/clinic")
    adapter = PostgresReadonlyClinicAdapter(
        secret_ref="env:TIA_TEST_CLINIC_DB",
        config={},
        native_delegate=_NativeDelegate(),
    )
    assert adapter.capabilities.supports(ClinicCapability.CATALOG_READ)
    assert adapter.build_catalog()["services"][0]["id"] == "tia-service"


def test_postgres_onboarding_samples_are_bounded_read_only_and_not_select_star(monkeypatch) -> None:
    adapter = _adapter(monkeypatch)
    table = _patient_table()
    monkeypatch.setattr(adapter, "_load_table_metadata", lambda: {"clients": table})
    cursor = _Cursor({
        "tia:postgres-onboarding-sample": [
            {"id": 1, "first_name": "Mona", "phone": "+201000000000", "medical_notes": "x" * 500},
            {"id": 2, "first_name": "Sara", "phone": "+201000000001", "medical_notes": "ok"},
        ]
    })
    connection = _Connection(cursor)
    monkeypatch.setattr(adapter, "_connect", lambda: connection)

    samples = adapter.sample_sync_schema_rows(rows_per_table=2, max_tables=1)

    assert len(samples["clients"]) == 2
    assert samples["clients"][0]["first_name"] == "Mona"
    assert len(samples["clients"][0]["medical_notes"]) <= 301
    sql = "\n".join(query for query, _params in cursor.executed)
    assert "tia:postgres-onboarding-sample" in sql
    assert "SELECT *" not in sql
    assert "SET TRANSACTION READ ONLY" in sql
