from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path
from uuid import uuid4

import pytest
from pydantic import ValidationError
from sqlalchemy import create_engine, text
from sqlalchemy.orm import Session

from app.schemas.analytics_business import AnalyticsBusinessPlan
from app.schemas.analytics_composable import AnalyticsComposePlan
from app.services.analytics_business import execute_business_plan

NOW = datetime(2026, 8, 28, 12, 0, tzinfo=UTC)


def _engine():
    engine = create_engine("sqlite+pysqlite:///:memory:")
    ddl = [
        "CREATE TABLE services (id CHAR(32) PRIMARY KEY, workspace_id CHAR(32), name VARCHAR(160), is_active BOOLEAN)",
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


def _plan(**updates) -> AnalyticsBusinessPlan:
    payload = {
        "kind": "business_analytics",
        "metrics": ["appointments"],
        "group_by": [],
        "lookback_days": 30,
        "start_date": None,
        "end_date": None,
        "comparison": "none",
        "service_ids": [],
        "branch_ids": [],
        "doctor_ids": [],
        "currency": None,
        "limit": 10,
        "sort_metric": "appointments",
        "sort_direction": "desc",
        "reason": "test",
    }
    payload.update(updates)
    return AnalyticsBusinessPlan.model_validate(payload)


def _seed(db: Session):
    ids = {key: uuid4() for key in (
        "workspace", "laser", "prp", "main", "west", "staff1", "staff2", "doctor1", "doctor2",
        "p1", "p2", "p3", "p4", "p5",
    )}
    w = ids["workspace"].hex
    for service, name in ((ids["laser"], "Laser"), (ids["prp"], "PRP")):
        db.execute(text("INSERT INTO services (id,workspace_id,name,is_active) VALUES (:id,:w,:name,1)"), {"id": service.hex, "w": w, "name": name})
    for branch, name in ((ids["main"], "Main"), (ids["west"], "West")):
        db.execute(text("INSERT INTO branches (id,workspace_id,name,is_active) VALUES (:id,:w,:name,1)"), {"id": branch.hex, "w": w, "name": name})
    for staff, first in ((ids["staff1"], "Sara"), (ids["staff2"], "Omar")):
        db.execute(text("INSERT INTO staff (id,workspace_id,first_name,last_name,is_active) VALUES (:id,:w,:first,'Doctor',1)"), {"id": staff.hex, "w": w, "first": first})
    for doctor, staff in ((ids["doctor1"], ids["staff1"]), (ids["doctor2"], ids["staff2"])):
        db.execute(text("INSERT INTO doctors (id,workspace_id,staff_id,is_active) VALUES (:id,:w,:staff,1)"), {"id": doctor.hex, "w": w, "staff": staff.hex})

    patient_dates = {
        "p1": ("2024-01-01", "2026-01-01"),
        "p2": ("2024-02-01", "2026-01-01"),
        "p3": ("2024-03-01", "2026-01-01"),
        "p4": ("2026-08-10", "2026-08-10"),
        "p5": ("2026-07-10", "2026-08-20"),
    }
    for key, (source_created, created) in patient_dates.items():
        pid = ids[key]
        db.execute(
            text("INSERT INTO patients (id,workspace_id,first_name,last_name,phone,status,marketing_consent,source_created_at,created_at,updated_at) VALUES (:id,:w,:first,'Patient',:phone,'active',1,:source,:created,:created)"),
            {"id": pid.hex, "w": w, "first": key.upper(), "phone": f"010000000{key[-1]}", "source": source_created, "created": created},
        )

    appointments: dict[str, str] = {}

    def appt(name: str, patient: str, service: str, branch: str, doctor: str, status: str, at: str) -> None:
        aid = uuid4()
        appointments[name] = aid.hex
        db.execute(
            text("INSERT INTO appointments (id,workspace_id,patient_id,branch_id,doctor_id,service_id,status,source,start_at,end_at,created_at,updated_at) VALUES (:id,:w,:p,:b,:d,:s,:status,:source,:at,:at,:at,:at)"),
            {
                "id": aid.hex, "w": w, "p": ids[patient].hex, "b": ids[branch].hex,
                "d": ids[doctor].hex, "s": ids[service].hex, "status": status,
                "source": "whatsapp" if service == "laser" else "phone", "at": at,
            },
        )

    # Current 30-day period.
    appt("laser1", "p1", "laser", "main", "doctor1", "completed", "2026-08-02T10:00:00+00:00")
    appt("laser2", "p1", "laser", "main", "doctor1", "completed", "2026-08-12T10:00:00+00:00")
    appt("laser3", "p2", "laser", "main", "doctor1", "completed", "2026-08-18T10:00:00+00:00")
    appt("laser4", "p3", "laser", "main", "doctor1", "no_show", "2026-08-20T10:00:00+00:00")
    appt("prp1", "p3", "prp", "west", "doctor2", "completed", "2026-08-08T10:00:00+00:00")
    appt("prp2", "p4", "prp", "west", "doctor2", "cancelled", "2026-08-21T10:00:00+00:00")

    # Previous 30-day period.
    appt("prev_laser1", "p1", "laser", "main", "doctor1", "completed", "2026-07-10T10:00:00+00:00")
    appt("prev_laser2", "p2", "laser", "main", "doctor1", "no_show", "2026-07-20T10:00:00+00:00")
    appt("prev_prp1", "p3", "prp", "west", "doctor2", "completed", "2026-07-05T10:00:00+00:00")
    appt("prev_prp2", "p3", "prp", "west", "doctor2", "completed", "2026-07-15T10:00:00+00:00")
    appt("prev_prp3", "p4", "prp", "west", "doctor2", "cancelled", "2026-07-25T10:00:00+00:00")

    def payment(name: str, patient: str, amount: int, at: str, appointment: str | None = None, kind: str = "payment") -> None:
        tx = uuid4().hex
        db.execute(
            text("INSERT INTO payment_transactions (id,workspace_id,patient_id,transaction_type,amount_minor,currency,created_at) VALUES (:id,:w,:p,:kind,:amount,'EGP',:at)"),
            {"id": tx, "w": w, "p": ids[patient].hex, "kind": kind, "amount": amount, "at": at},
        )
        if appointment:
            db.execute(
                text("INSERT INTO payment_allocations (id,workspace_id,transaction_id,appointment_id,amount_minor,created_at) VALUES (:id,:w,:tx,:appt,:amount,:at)"),
                {"id": uuid4().hex, "w": w, "tx": tx, "appt": appointments[appointment], "amount": amount, "at": at},
            )

    payment("cur_laser1", "p1", 100000, "2026-08-03T10:00:00+00:00", "laser1")
    payment("cur_laser2", "p1", 100000, "2026-08-13T10:00:00+00:00", "laser2")
    payment("cur_laser_refund", "p1", 20000, "2026-08-14T10:00:00+00:00", "laser1", kind="refund")
    # p2 has a huge unallocated payment. It must not be attributed to Laser.
    payment("unallocated", "p2", 5000000, "2026-08-19T10:00:00+00:00", None)
    payment("cur_prp", "p3", 150000, "2026-08-09T10:00:00+00:00", "prp1")

    payment("prev_laser", "p1", 70000, "2026-07-11T10:00:00+00:00", "prev_laser1")
    payment("prev_prp1", "p3", 100000, "2026-07-06T10:00:00+00:00", "prev_prp1")
    payment("prev_prp2", "p3", 100000, "2026-07-16T10:00:00+00:00", "prev_prp2")
    db.commit()
    return ids


def _metrics(row):
    return {item.key: item.value for item in row.metrics}


def test_grouped_service_analysis_combines_volume_revenue_and_retention() -> None:
    engine = _engine()
    with Session(engine) as db:
        ids = _seed(db)
        result = execute_business_plan(
            db,
            workspace_id=ids["workspace"],
            question="قارن الخدمات في الزيارات والإيراد والretention آخر 30 يوم",
            plan=_plan(
                metrics=["appointments", "completed_appointments", "net_paid_minor", "same_service_repeat_rate"],
                group_by=["service"],
                currency="EGP",
                sort_metric="net_paid_minor",
            ),
            now=NOW,
        )
        assert [row.label for row in result.rows] == ["Laser", "PRP"]
        laser = _metrics(result.rows[0])
        assert laser["appointments"] == 4
        assert laser["completed_appointments"] == 3
        assert laser["net_paid_minor"] == 180000
        assert laser["same_service_repeat_rate"] == 50.0
        prp = _metrics(result.rows[1])
        assert prp["appointments"] == 2
        assert prp["net_paid_minor"] == 150000
        assert prp["same_service_repeat_rate"] == 0.0
        assert any("payment allocations" in definition for definition in result.definitions)


def test_previous_period_comparison_uses_equal_window_and_rate_point_delta() -> None:
    engine = _engine()
    with Session(engine) as db:
        ids = _seed(db)
        result = execute_business_plan(
            db,
            workspace_id=ids["workspace"],
            question="قارن أداء الليزر آخر 30 يوم بالـ30 يوم اللي قبلهم",
            plan=_plan(
                metrics=["completed_appointments", "attendance_rate"],
                group_by=["service"],
                service_ids=[str(ids["laser"])],
                comparison="previous_period",
                sort_metric="completed_appointments",
            ),
            now=NOW,
        )
        assert len(result.rows) == 1
        values = _metrics(result.rows[0])
        assert values["completed_appointments"] == 3
        assert values["completed_appointments_previous"] == 1
        assert values["completed_appointments_change_percent"] == 200.0
        assert values["attendance_rate"] == 75.0
        assert values["attendance_rate_previous"] == 50.0
        assert values["attendance_rate_delta_points"] == 25.0


def test_booking_completion_payment_funnel_is_deterministic() -> None:
    engine = _engine()
    with Session(engine) as db:
        ids = _seed(db)
        result = execute_business_plan(
            db,
            workspace_id=ids["workspace"],
            question="وريني funnel من الحجز للمكتمل للدفع آخر شهر",
            plan=_plan(
                metrics=[
                    "appointments",
                    "completed_appointments",
                    "paid_completed_appointments",
                    "completion_rate",
                    "paid_completion_rate",
                    "booking_to_paid_rate",
                ],
                group_by=[],
                sort_metric="appointments",
            ),
            now=NOW,
        )
        values = _metrics(result.rows[0])
        assert values["appointments"] == 6
        assert values["completed_appointments"] == 4
        assert values["paid_completed_appointments"] == 3
        assert values["completion_rate"] == 66.7
        assert values["paid_completion_rate"] == 75.0
        assert values["booking_to_paid_rate"] == 50.0
        assert any("explicit payment allocation" in definition for definition in result.definitions)


def test_month_trend_can_combine_service_and_time_dimensions() -> None:
    engine = _engine()
    with Session(engine) as db:
        ids = _seed(db)
        result = execute_business_plan(
            db,
            workspace_id=ids["workspace"],
            question="الحجوزات لكل خدمة بالشهر آخر 60 يوم",
            plan=_plan(
                metrics=["appointments", "completed_appointments"],
                group_by=["service", "month"],
                lookback_days=60,
                sort_metric="appointments",
            ),
            now=NOW,
        )
        labels = {row.label for row in result.rows}
        assert "Laser · 2026-08" in labels
        assert "Laser · 2026-07" in labels
        assert "PRP · 2026-08" in labels
        assert "PRP · 2026-07" in labels


def test_new_patients_use_source_created_at_not_import_created_at() -> None:
    engine = _engine()
    with Session(engine) as db:
        ids = _seed(db)
        result = execute_business_plan(
            db,
            workspace_id=ids["workspace"],
            question="العملاء الجدد بالشهر آخر شهرين",
            plan=_plan(
                metrics=["new_patients"],
                group_by=["month"],
                lookback_days=60,
                sort_metric="new_patients",
            ),
            now=NOW,
        )
        counts = {row.label: _metrics(row)["new_patients"] for row in result.rows}
        assert counts["2026-08"] == 1
        assert counts["2026-07"] == 1
        # p1/p2/p3 were imported in 2026 but source-created in 2024, so they do not inflate new-patient counts.
        assert sum(counts.values()) == 2



def test_source_dimension_supports_channel_conversion_and_allocated_revenue() -> None:
    engine = _engine()
    with Session(engine) as db:
        ids = _seed(db)
        result = execute_business_plan(
            db,
            workspace_id=ids["workspace"],
            question="قارن واتساب والتليفون في التحويل والإيراد آخر شهر",
            plan=_plan(
                metrics=["appointments", "completion_rate", "net_paid_minor"],
                group_by=["source"],
                currency="EGP",
                sort_metric="net_paid_minor",
            ),
            now=NOW,
        )
        rows = {row.label: _metrics(row) for row in result.rows}
        assert rows["whatsapp"]["appointments"] == 4
        assert rows["whatsapp"]["completion_rate"] == 75.0
        assert rows["whatsapp"]["net_paid_minor"] == 180000
        assert rows["phone"]["appointments"] == 2
        assert rows["phone"]["completion_rate"] == 50.0
        assert rows["phone"]["net_paid_minor"] == 150000


def test_average_net_paid_per_paying_patient_is_currency_safe() -> None:
    engine = _engine()
    with Session(engine) as db:
        ids = _seed(db)
        result = execute_business_plan(
            db,
            workspace_id=ids["workspace"],
            question="متوسط صافي المدفوع لكل عميل دافع آخر شهر",
            plan=_plan(
                metrics=["net_paid_minor", "paying_patients", "avg_net_paid_per_paying_patient_minor"],
                currency="EGP",
                sort_metric="net_paid_minor",
            ),
            now=NOW,
        )
        values = _metrics(result.rows[0])
        assert values["net_paid_minor"] == 5330000
        assert values["paying_patients"] == 3
        assert values["avg_net_paid_per_paying_patient_minor"] == 1776667

def test_business_plan_rejects_unsafe_or_ambiguous_combinations() -> None:
    with pytest.raises(ValidationError):
        _plan(metrics=["net_paid_minor"], currency=None)
    with pytest.raises(ValidationError):
        _plan(metrics=["same_service_repeat_rate"], group_by=[], service_ids=[])
    with pytest.raises(ValidationError):
        _plan(metrics=["new_patients"], group_by=["service"])
    with pytest.raises(ValidationError):
        _plan(metrics=["appointments"], group_by=["month"], comparison="previous_period")



def test_composer_business_mode_is_read_only_and_previous_plan_context_is_typed() -> None:
    business = _plan(metrics=["appointments", "completion_rate"], group_by=["source"])
    composed = AnalyticsComposePlan.model_validate({
        "mode": "business",
        "reuse_previous_audience": False,
        "metric_plan": None,
        "business_plan": business.model_dump(mode="json"),
        "audience_plan": None,
        "action": {
            "kind": "none", "title": None, "description": None, "due_in_days": None,
            "priority": None, "reason": "read only",
        },
        "reason": "business analysis",
    })
    assert composed.business_plan == business

    with pytest.raises(ValidationError):
        AnalyticsComposePlan.model_validate({
            **composed.model_dump(mode="json"),
            "action": {
                "kind": "save_audience", "title": "x", "description": None,
                "due_in_days": None, "priority": None, "reason": "must not write",
            },
        })

    root = Path(__file__).resolve().parents[2]
    frontend_action = (root / "frontend/src/app/(dashboard)/analytics/actions.ts").read_text(encoding="utf-8")
    catalog_ui = (root / "frontend/src/app/(dashboard)/analytics/catalog.tsx").read_text(encoding="utf-8")
    orchestrator = (Path(__file__).resolve().parent.parent / "app/agents/analytics_orchestrator.py").read_text(encoding="utf-8")
    # v0.47 makes the deterministic catalog the primary frontend path. The
    # legacy composable orchestrator remains backend-compatible but is no longer
    # required by the Analytics page.
    assert "runAnalyticsCatalogAction" in frontend_action
    assert "AnalyticsCatalogPanel" in catalog_ui
    assert "previous_business_plan" in orchestrator

def test_phase71_source_has_no_runtime_sql_or_lexical_routing() -> None:
    backend = Path(__file__).resolve().parent.parent
    service = (backend / "app/services/analytics_business.py").read_text(encoding="utf-8").lower()
    orchestrator = (backend / "app/agents/analytics_orchestrator.py").read_text(encoding="utf-8").lower()
    assert "text(" not in service
    assert "exec_driver_sql" not in service
    assert "re.compile" not in orchestrator
    assert "re.search" not in orchestrator
    assert "keyword" not in orchestrator
