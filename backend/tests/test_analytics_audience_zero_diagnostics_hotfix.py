from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path
from uuid import uuid4

from sqlalchemy import create_engine, text
from sqlalchemy.orm import Session

from app.schemas.analytics_composable import AnalyticsAudiencePlan
from app.services.analytics_audience import execute_audience_plan

NOW = datetime(2026, 8, 28, 12, 0, tzinfo=UTC)


def _plan(service_id: str) -> AnalyticsAudiencePlan:
    return AnalyticsAudiencePlan.model_validate(
        {
            "kind": "patient_audience",
            "lookback_days": 180,
            "inactivity_days": None,
            "limit": 25,
            "service_ids": [service_id],
            "branch_ids": [],
            "doctor_ids": [],
            "appointment_statuses": ["completed"],
            "min_matching_visits": 1,
            "max_matching_visits": None,
            "has_future_appointment": None,
            "marketing_consent": None,
            "patient_statuses": ["active", "inactive"],
            "min_net_paid_minor": None,
            "max_net_paid_minor": None,
            "currency": None,
            "sort_by": "last_activity_desc",
            "reason": "laser patients in the last six months",
        }
    )


def test_zero_audience_explains_status_mismatch_instead_of_silent_zero() -> None:
    engine = create_engine("sqlite+pysqlite:///:memory:")
    workspace_id = uuid4()
    service_id = uuid4()
    patient_id = uuid4()
    appointment_id = uuid4()
    with engine.begin() as conn:
        conn.exec_driver_sql(
            "CREATE TABLE services (id CHAR(32) PRIMARY KEY, workspace_id CHAR(32), name VARCHAR(200))"
        )
        conn.exec_driver_sql(
            "CREATE TABLE patients (id CHAR(32) PRIMARY KEY, workspace_id CHAR(32), first_name VARCHAR(120), "
            "last_name VARCHAR(120), phone VARCHAR(40), status VARCHAR(20), marketing_consent BOOLEAN, "
            "source_created_at DATETIME, created_at DATETIME)"
        )
        conn.exec_driver_sql(
            "CREATE TABLE appointments (id CHAR(32) PRIMARY KEY, workspace_id CHAR(32), patient_id CHAR(32), "
            "branch_id CHAR(32), doctor_id CHAR(32), service_id CHAR(32), status VARCHAR(20), start_at DATETIME)"
        )
        conn.exec_driver_sql(
            "CREATE TABLE payment_transactions (id CHAR(32) PRIMARY KEY, workspace_id CHAR(32), patient_id CHAR(32), "
            "transaction_type VARCHAR(16), amount_minor INTEGER, currency VARCHAR(3), created_at DATETIME)"
        )
        conn.exec_driver_sql(
            "CREATE TABLE payment_allocations (id CHAR(32) PRIMARY KEY, workspace_id CHAR(32), transaction_id CHAR(32), "
            "appointment_id CHAR(32), amount_minor INTEGER, created_at DATETIME)"
        )
        conn.execute(
            text("INSERT INTO services (id,workspace_id,name) VALUES (:id,:w,'Laser Full Body')"),
            {"id": service_id.hex, "w": workspace_id.hex},
        )
        conn.execute(
            text(
                "INSERT INTO patients (id,workspace_id,first_name,last_name,phone,status,marketing_consent,created_at) "
                "VALUES (:id,:w,'Mona','Ali','01000000000','active',1,'2025-01-01')"
            ),
            {"id": patient_id.hex, "w": workspace_id.hex},
        )
        conn.execute(
            text(
                "INSERT INTO appointments (id,workspace_id,patient_id,branch_id,doctor_id,service_id,status,start_at) "
                "VALUES (:id,:w,:p,:b,:d,:s,'confirmed','2026-08-01')"
            ),
            {
                "id": appointment_id.hex,
                "w": workspace_id.hex,
                "p": patient_id.hex,
                "b": uuid4().hex,
                "d": uuid4().hex,
                "s": service_id.hex,
            },
        )

    with Session(engine) as db:
        result = execute_audience_plan(
            db,
            workspace_id=workspace_id,
            plan=_plan(str(service_id)),
            now=NOW,
        )

    assert result.rows == []
    assert "confirmed" in result.answer
    assert "completed" in " ".join(result.definitions)
    assert "Laser Full Body" in " ".join(result.definitions)
    assert "لا تحسب حجزًا لم يتم كجلسة فعلية" in result.answer


def test_planner_requests_all_clearly_matching_services_for_broad_service_wording() -> None:
    root = Path(__file__).resolve().parents[1]
    source = (root / "app/agents/analytics_orchestrator.py").read_text(encoding="utf-8")
    assert "include every clearly matching service ID" in source
    assert "choosing one arbitrary service" in source
