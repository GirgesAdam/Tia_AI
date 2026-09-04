from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path
from uuid import uuid4

import pytest
from sqlalchemy import create_engine, text
from sqlalchemy.orm import Session

from app.schemas.analytics_catalog import AnalyticsCatalogRunRequest
from app.services.analytics_bi import AnalyticsBIError
from app.services.analytics_catalog import (
    _BY_KEY,
    _DEFINITIONS,
    analytics_catalog,
    run_catalog_analysis,
)

NOW = datetime(2026, 8, 28, 12, 0, tzinfo=UTC)


def _engine():
    engine = create_engine("sqlite+pysqlite:///:memory:")
    ddl = [
        "CREATE TABLE services (id CHAR(32) PRIMARY KEY, workspace_id CHAR(32), name VARCHAR(160), currency VARCHAR(3), is_active BOOLEAN)",
        "CREATE TABLE branches (id CHAR(32) PRIMARY KEY, workspace_id CHAR(32), name VARCHAR(160), is_active BOOLEAN)",
        "CREATE TABLE staff (id CHAR(32) PRIMARY KEY, workspace_id CHAR(32), first_name VARCHAR(120), last_name VARCHAR(120), is_active BOOLEAN)",
        "CREATE TABLE doctors (id CHAR(32) PRIMARY KEY, workspace_id CHAR(32), staff_id CHAR(32), is_active BOOLEAN)",
        """
        CREATE TABLE patients (
            id CHAR(32) PRIMARY KEY, workspace_id CHAR(32), first_name VARCHAR(120), last_name VARCHAR(120),
            phone VARCHAR(40), status VARCHAR(20), marketing_consent BOOLEAN,
            source_created_at DATETIME, created_at DATETIME, updated_at DATETIME
        )
        """,
        """
        CREATE TABLE appointments (
            id CHAR(32) PRIMARY KEY, workspace_id CHAR(32), patient_id CHAR(32), branch_id CHAR(32),
            doctor_id CHAR(32), service_id CHAR(32), status VARCHAR(20), source VARCHAR(20), start_at DATETIME, end_at DATETIME,
            created_at DATETIME, updated_at DATETIME
        )
        """,
        """
        CREATE TABLE payment_transactions (
            id CHAR(32) PRIMARY KEY, workspace_id CHAR(32), patient_id CHAR(32), transaction_type VARCHAR(16),
            amount_minor INTEGER, currency VARCHAR(3), reference_transaction_id CHAR(32), created_at DATETIME,
            patient_package_id CHAR(32)
        )
        """,
        """
        CREATE TABLE payment_allocations (
            id CHAR(32) PRIMARY KEY, workspace_id CHAR(32), transaction_id CHAR(32), appointment_id CHAR(32),
            amount_minor INTEGER, created_at DATETIME
        )
        """,
        """
        CREATE TABLE patient_packages (
            id CHAR(32) PRIMARY KEY, workspace_id CHAR(32), patient_id CHAR(32), service_id CHAR(32),
            purchase_transaction_id CHAR(32), name VARCHAR(200), sessions_purchased INTEGER, sale_price_minor INTEGER,
            currency VARCHAR(3), purchased_at DATETIME, status VARCHAR(16), source VARCHAR(16)
        )
        """,
    ]
    with engine.begin() as conn:
        for statement in ddl:
            conn.exec_driver_sql(statement)
    return engine


def _seed(db: Session):
    ids = {key: uuid4() for key in (
        "workspace", "laser", "prp", "branch", "staff", "doctor", "recent", "old", "other",
        "laser_recent", "laser_old", "prp_recent",
    )}
    w = ids["workspace"].hex
    db.execute(text("INSERT INTO services (id,workspace_id,name,currency,is_active) VALUES (:id,:w,'Laser','EGP',1)"), {"id": ids["laser"].hex, "w": w})
    db.execute(text("INSERT INTO services (id,workspace_id,name,currency,is_active) VALUES (:id,:w,'PRP','EGP',1)"), {"id": ids["prp"].hex, "w": w})
    db.execute(text("INSERT INTO branches (id,workspace_id,name,is_active) VALUES (:id,:w,'Main',1)"), {"id": ids["branch"].hex, "w": w})
    db.execute(text("INSERT INTO staff (id,workspace_id,first_name,last_name,is_active) VALUES (:id,:w,'Sara','Hassan',1)"), {"id": ids["staff"].hex, "w": w})
    db.execute(text("INSERT INTO doctors (id,workspace_id,staff_id,is_active) VALUES (:id,:w,:s,1)"), {"id": ids["doctor"].hex, "w": w, "s": ids["staff"].hex})

    for key, first, source_created in (
        ("recent", "Mona", "2025-01-01"),
        ("old", "Nour", "2024-01-01"),
        ("other", "Laila", "2026-08-10"),
    ):
        db.execute(text("""
            INSERT INTO patients (id,workspace_id,first_name,last_name,phone,status,marketing_consent,source_created_at,created_at,updated_at)
            VALUES (:id,:w,:first,'Ali',:phone,'active',1,:source,'2026-01-01','2026-08-20')
        """), {"id": ids[key].hex, "w": w, "first": first, "phone": f"0100000000{len(first)}", "source": source_created})

    appointments = (
        ("laser_recent", "recent", "laser", "completed", "2026-08-10T10:00:00+00:00", "whatsapp"),
        ("laser_old", "old", "laser", "completed", "2025-10-01T10:00:00+00:00", "phone"),
        ("prp_recent", "other", "prp", "completed", "2026-08-12T10:00:00+00:00", "phone"),
    )
    for aid, patient, service, status, at, source in appointments:
        db.execute(text("""
            INSERT INTO appointments (id,workspace_id,patient_id,branch_id,doctor_id,service_id,status,source,start_at,end_at,created_at,updated_at)
            VALUES (:id,:w,:p,:b,:d,:s,:status,:source,:at,:at,:at,:at)
        """), {
            "id": ids[aid].hex, "w": w, "p": ids[patient].hex, "b": ids["branch"].hex,
            "d": ids["doctor"].hex, "s": ids[service].hex, "status": status, "source": source, "at": at,
        })

    # Explicit allocations: Laser = 1,000 EGP; PRP = 1,500 EGP.
    for patient, appointment, amount, at in (
        ("recent", "laser_recent", 100000, "2026-08-11"),
        ("other", "prp_recent", 150000, "2026-08-13"),
    ):
        tx = uuid4()
        db.execute(text("INSERT INTO payment_transactions (id,workspace_id,patient_id,transaction_type,amount_minor,currency,created_at) VALUES (:id,:w,:p,'payment',:amount,'EGP',:at)"), {"id": tx.hex, "w": w, "p": ids[patient].hex, "amount": amount, "at": at})
        db.execute(text("INSERT INTO payment_allocations (id,workspace_id,transaction_id,appointment_id,amount_minor,created_at) VALUES (:id,:w,:tx,:a,:amount,:at)"), {"id": uuid4().hex, "w": w, "tx": tx.hex, "a": ids[appointment].hex, "amount": amount, "at": at})

    # Huge unallocated payment must not be attributed to Laser.
    db.execute(text("INSERT INTO payment_transactions (id,workspace_id,patient_id,transaction_type,amount_minor,currency,created_at) VALUES (:id,:w,:p,'payment',9000000,'EGP','2026-08-14')"), {"id": uuid4().hex, "w": w, "p": ids["recent"].hex})
    db.commit()
    return ids


def _metrics(row):
    return {metric.key: metric.value for metric in row.metrics}


def test_catalog_has_broad_deterministic_library_and_no_question_field() -> None:
    assert len(_DEFINITIONS) == 35
    assert len({item.key for item in _DEFINITIONS}) == len(_DEFINITIONS)
    assert {item.category for item in _DEFINITIONS} == {
        "revenue", "patients", "appointments", "services", "doctors", "branches", "retention", "funnels"
    }
    assert "question" not in AnalyticsCatalogRunRequest.model_fields
    assert "message" not in AnalyticsCatalogRunRequest.model_fields


def test_revenue_by_service_is_registry_driven_and_allocation_only() -> None:
    engine = _engine()
    with Session(engine) as db:
        ids = _seed(db)
        result = run_catalog_analysis(
            db,
            workspace_id=ids["workspace"],
            request=AnalyticsCatalogRunRequest(
                analysis_key="revenue_by_service", lookback_days=30
            ),
            now=NOW,
        )
        assert result.business_plan is not None
        assert result.business_plan.group_by == ["service"]
        assert result.business_plan.currency == "EGP"
        assert "currency" not in _BY_KEY["revenue_by_service"].filters
        assert result.business_plan.reason.startswith("Admin selected catalog analysis")
        assert [row.label for row in result.rows] == ["PRP", "Laser"]
        values = {row.label: _metrics(row) for row in result.rows}
        assert values["Laser"]["net_paid_minor"] == 100000
        assert values["PRP"]["net_paid_minor"] == 150000
        assert result.chart_data.labels == ["PRP", "Laser"]
        assert result.chart_data.series[0].key == "net_paid_minor"
        assert result.chart_data.series[0].format == "money"
        assert result.chart_data.series[0].currency == "EGP"
        assert result.chart_data.series[0].values == [150000, 100000]
        # A grouped revenue view must not calculate its headline from clinic-wide
        # transactions because that would re-introduce unallocated money.
        assert result.highlights == []
        assert all("الـAI" not in item and "تخمين نصي" not in item for item in result.definitions)


def test_lapsed_patient_function_uses_explicit_admin_filters() -> None:
    engine = _engine()
    with Session(engine) as db:
        ids = _seed(db)
        result = run_catalog_analysis(
            db,
            workspace_id=ids["workspace"],
            request=AnalyticsCatalogRunRequest(
                analysis_key="lapsed_patients",
                service_ids=[str(ids["laser"])],
                inactivity_days=180,
                limit=25,
            ),
            now=NOW,
        )
        assert result.result_kind == "patient_list"
        assert result.audience_plan is not None
        assert result.audience_plan.service_ids == [str(ids["laser"])]
        assert result.audience_plan.inactivity_days == 180
        assert [row.key for row in result.rows] == [str(ids["old"])]
        assert "follow_up_tasks" in result.allowed_actions


def test_booking_paid_funnel_has_fixed_stages() -> None:
    engine = _engine()
    with Session(engine) as db:
        ids = _seed(db)
        result = run_catalog_analysis(
            db,
            workspace_id=ids["workspace"],
            request=AnalyticsCatalogRunRequest(analysis_key="booking_paid_funnel", lookback_days=30),
            now=NOW,
        )
        metrics = _metrics(result.rows[0])
        assert metrics["appointments"] == 2
        assert metrics["completed_appointments"] == 2
        assert metrics["paid_completed_appointments"] == 2
        assert result.chart_metric_keys == ["appointments", "completed_appointments", "paid_completed_appointments"]


def test_catalog_rejects_filters_not_supported_by_selected_analysis() -> None:
    engine = _engine()
    with Session(engine) as db:
        ids = _seed(db)
        with pytest.raises(AnalyticsBIError, match="does not accept the service filter"):
            run_catalog_analysis(
                db,
                workspace_id=ids["workspace"],
                request=AnalyticsCatalogRunRequest(
                    analysis_key="revenue_overview",
                    lookback_days=30,
                    service_ids=[str(ids["laser"])],
                ),
                now=NOW,
            )


def test_catalog_rejects_unknown_canonical_entity_id() -> None:
    engine = _engine()
    with Session(engine) as db:
        ids = _seed(db)
        with pytest.raises(AnalyticsBIError, match="unknown canonical service"):
            run_catalog_analysis(
                db,
                workspace_id=ids["workspace"],
                request=AnalyticsCatalogRunRequest(
                    analysis_key="appointment_overview",
                    lookback_days=30,
                    service_ids=[str(uuid4())],
                ),
                now=NOW,
            )


def test_catalog_response_exposes_entities_without_currency_choice() -> None:
    engine = _engine()
    with Session(engine) as db:
        ids = _seed(db)
        result = analytics_catalog(db, workspace_id=ids["workspace"])
        assert "currencies" not in type(result).model_fields
        assert {item.name for item in result.services} == {"Laser", "PRP"}
        assert result.analyses[0].key == "revenue_overview"


def test_catalog_request_forbids_user_selected_currency() -> None:
    with pytest.raises(Exception, match="currency"):
        AnalyticsCatalogRunRequest(analysis_key="revenue_overview", lookback_days=30, currency="USD")


def test_duplicate_overall_retention_was_replaced_by_doctor_retention() -> None:
    keys = {item.key for item in _DEFINITIONS}
    assert "overall_retention" not in keys
    assert "doctor_retention" in keys
    assert _BY_KEY["doctor_retention"].group_by == ("doctor",)



def test_trend_highlights_are_backend_aggregate_metrics_not_frontend_sums() -> None:
    engine = _engine()
    with Session(engine) as db:
        ids = _seed(db)
        result = run_catalog_analysis(
            db,
            workspace_id=ids["workspace"],
            request=AnalyticsCatalogRunRequest(analysis_key="appointment_trend", lookback_days=30),
            now=NOW,
        )
        highlights = {metric.key: metric.value for metric in result.highlights}
        assert highlights == {
            "appointments": 2,
            "completed_appointments": 2,
            "no_show_appointments": 0,
        }


def test_public_catalog_removes_duplicate_service_booking_analysis_and_uses_business_copy() -> None:
    keys = {item.key for item in _DEFINITIONS}
    assert "appointments_by_service" not in keys
    assert "service_popularity" in keys
    forbidden_copy = ("refund", "no-show", "Funnel", "completion")
    for definition in _DEFINITIONS:
        public_copy = f"{definition.title} {definition.description}"
        assert not any(word in public_copy for word in forbidden_copy)


def test_frontend_primary_analytics_page_uses_catalog_not_ai_assistant() -> None:
    root = Path(__file__).resolve().parents[2]
    page = (root / "frontend/src/app/(dashboard)/analytics/page.tsx").read_text(encoding="utf-8")
    catalog = (root / "frontend/src/app/(dashboard)/analytics/catalog.tsx").read_text(encoding="utf-8")

    assert "AnalyticsCatalogPanel" in page
    assert "<AnalyticsAssistant" not in page
    assert "/analytics/catalog" in page
    assert "runAnalyticsCatalogAction" in catalog
    assert 'name="currency"' not in catalog
    assert "chart_data" in catalog
    assert "highlights" in catalog
    assert 'const [query, setQuery] = useState("")' in catalog
    assert "normalizedQuery" in catalog
    assert "includes(normalizedQuery)" in catalog
    assert "quickAccess.map" in catalog
    assert "hasEntityFilters" in catalog
    assert "value / first * 100" in catalog
    assert "fromPrevious" in catalog
    assert "result.definitions.map" in catalog
    assert "canManageDoctorIdentities" not in page
    assert "/analytics/overview" not in page
    assert "/analytics/history" not in page

    assistant = (root / "frontend/src/app/(dashboard)/analytics/assistant.tsx").read_text(encoding="utf-8")
    assert "analyticsAssistantAction" not in assistant
    assert "return null" in assistant



def test_analytics_query_index_migration_is_current_head() -> None:
    root = Path(__file__).resolve().parents[1]
    migration = (root / "alembic/versions/0041_analytics_query_indexes.py").read_text(encoding="utf-8")
    readiness = (root / "app/services/operational_readiness.py").read_text(encoding="utf-8")
    assert 'revision: str = "0041_analytics_query_indexes"' in migration
    assert 'down_revision: str | None = "0040_doctor_name_hygiene"' in migration
    assert 'ix_appointments_workspace_status_start_patient' in migration
    assert 'EXPECTED_MIGRATION_HEAD = "0054_cancel_recovery"' in readiness


def test_catalog_filter_options_hide_inactive_legacy_entities() -> None:
    engine = _engine()
    with Session(engine) as db:
        ids = _seed(db)
        w = ids["workspace"].hex
        inactive_service = uuid4()
        inactive_branch = uuid4()
        inactive_staff = uuid4()
        inactive_doctor = uuid4()
        db.execute(
            text("INSERT INTO services (id,workspace_id,name,currency,is_active) VALUES (:id,:w,'Legacy Service','EGP',0)"),
            {"id": inactive_service.hex, "w": w},
        )
        db.execute(
            text("INSERT INTO branches (id,workspace_id,name,is_active) VALUES (:id,:w,'Legacy Branch',0)"),
            {"id": inactive_branch.hex, "w": w},
        )
        db.execute(
            text("INSERT INTO staff (id,workspace_id,first_name,last_name,is_active) VALUES (:id,:w,'Legacy','Doctor',0)"),
            {"id": inactive_staff.hex, "w": w},
        )
        db.execute(
            text("INSERT INTO doctors (id,workspace_id,staff_id,is_active) VALUES (:id,:w,:s,0)"),
            {"id": inactive_doctor.hex, "w": w, "s": inactive_staff.hex},
        )
        db.commit()

        result = analytics_catalog(db, workspace_id=ids["workspace"])
        assert "Legacy Service" not in {item.name for item in result.services}
        assert "Legacy Branch" not in {item.name for item in result.branches}
        assert "Legacy Doctor" not in {item.name for item in result.doctors}
        assert "Sara Hassan" in {item.name for item in result.doctors}
