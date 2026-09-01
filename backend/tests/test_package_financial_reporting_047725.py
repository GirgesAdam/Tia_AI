from __future__ import annotations

from datetime import UTC, datetime
from uuid import uuid4

from sqlalchemy import create_engine, text
from sqlalchemy.orm import Session

from app.schemas.analytics_catalog import AnalyticsCatalogRunRequest
from app.services.analytics_catalog import run_catalog_analysis

NOW = datetime(2026, 8, 28, 12, 0, tzinfo=UTC)


def _engine():
    engine = create_engine("sqlite+pysqlite:///:memory:")
    ddl = [
        "CREATE TABLE services (id CHAR(32) PRIMARY KEY, workspace_id CHAR(32), name VARCHAR(160), currency VARCHAR(3), is_active BOOLEAN)",
        "CREATE TABLE branches (id CHAR(32) PRIMARY KEY, workspace_id CHAR(32), name VARCHAR(160), is_active BOOLEAN)",
        "CREATE TABLE staff (id CHAR(32) PRIMARY KEY, workspace_id CHAR(32), first_name VARCHAR(120), last_name VARCHAR(120), is_active BOOLEAN)",
        "CREATE TABLE doctors (id CHAR(32) PRIMARY KEY, workspace_id CHAR(32), staff_id CHAR(32), is_active BOOLEAN)",
        "CREATE TABLE patients (id CHAR(32) PRIMARY KEY, workspace_id CHAR(32), first_name VARCHAR(120), last_name VARCHAR(120), phone VARCHAR(40), status VARCHAR(20), marketing_consent BOOLEAN, source_created_at DATETIME, created_at DATETIME, updated_at DATETIME)",
        "CREATE TABLE appointments (id CHAR(32) PRIMARY KEY, workspace_id CHAR(32), patient_id CHAR(32), branch_id CHAR(32), doctor_id CHAR(32), service_id CHAR(32), status VARCHAR(20), source VARCHAR(20), start_at DATETIME, end_at DATETIME, created_at DATETIME, updated_at DATETIME)",
        "CREATE TABLE payment_transactions (id CHAR(32) PRIMARY KEY, workspace_id CHAR(32), patient_id CHAR(32), transaction_type VARCHAR(16), amount_minor INTEGER, currency VARCHAR(3), reference_transaction_id CHAR(32), created_at DATETIME, patient_package_id CHAR(32))",
        "CREATE TABLE payment_allocations (id CHAR(32) PRIMARY KEY, workspace_id CHAR(32), transaction_id CHAR(32), appointment_id CHAR(32), amount_minor INTEGER, created_at DATETIME)",
        "CREATE TABLE patient_packages (id CHAR(32) PRIMARY KEY, workspace_id CHAR(32), patient_id CHAR(32), service_id CHAR(32), purchase_transaction_id CHAR(32), name VARCHAR(200), sessions_purchased INTEGER, sale_price_minor INTEGER, currency VARCHAR(3), purchased_at DATETIME, status VARCHAR(16), source VARCHAR(16))",
    ]
    with engine.begin() as conn:
        for statement in ddl:
            conn.exec_driver_sql(statement)
    return engine


def _metric(row, key: str):
    return next(metric.value for metric in row.metrics if metric.key == key)


def test_package_sale_and_refund_are_attributed_once_to_service_not_sessions() -> None:
    engine = _engine()
    with Session(engine) as db:
        w, service, branch, staff, doctor, patient = [uuid4() for _ in range(6)]
        db.execute(text("INSERT INTO services VALUES (:id,:w,'Laser Bikini','EGP',1)"), {"id": service.hex, "w": w.hex})
        db.execute(text("INSERT INTO branches VALUES (:id,:w,'Main',1)"), {"id": branch.hex, "w": w.hex})
        db.execute(text("INSERT INTO staff VALUES (:id,:w,'Sara','Ali',1)"), {"id": staff.hex, "w": w.hex})
        db.execute(text("INSERT INTO doctors VALUES (:id,:w,:s,1)"), {"id": doctor.hex, "w": w.hex, "s": staff.hex})
        db.execute(text("INSERT INTO patients VALUES (:id,:w,'Mona','Ali','01000000000','active',1,'2026-01-01','2026-01-01','2026-01-01')"), {"id": patient.hex, "w": w.hex})

        purchase = uuid4()
        db.execute(text("INSERT INTO payment_transactions VALUES (:id,:w,:p,'payment',480000,'EGP',NULL,'2026-08-10',NULL)"), {"id": purchase.hex, "w": w.hex, "p": patient.hex})
        db.execute(text("INSERT INTO patient_packages VALUES (:id,:w,:p,:s,:tx,'6 Laser',6,480000,'EGP','2026-08-10','active','staff')"), {"id": uuid4().hex, "w": w.hex, "p": patient.hex, "s": service.hex, "tx": purchase.hex})

        # A legacy allocation on the same package purchase must not double-count it.
        appointment = uuid4()
        db.execute(text("INSERT INTO appointments VALUES (:id,:w,:p,:b,:d,:s,'completed','staff','2026-08-11','2026-08-11','2026-08-11','2026-08-11')"), {"id": appointment.hex, "w": w.hex, "p": patient.hex, "b": branch.hex, "d": doctor.hex, "s": service.hex})
        db.execute(text("INSERT INTO payment_allocations VALUES (:id,:w,:tx,:a,80000,'2026-08-11')"), {"id": uuid4().hex, "w": w.hex, "tx": purchase.hex, "a": appointment.hex})

        refund = uuid4()
        db.execute(text("INSERT INTO payment_transactions VALUES (:id,:w,:p,'refund',60000,'EGP',:ref,'2026-08-20',NULL)"), {"id": refund.hex, "w": w.hex, "p": patient.hex, "ref": purchase.hex})
        db.commit()

        result = run_catalog_analysis(db, workspace_id=w, request=AnalyticsCatalogRunRequest(analysis_key="revenue_by_service", lookback_days=30), now=NOW, use_cache=False)
        row = next(row for row in result.rows if row.label == "Laser Bikini")
        assert _metric(row, "net_paid_minor") == 420000

        total = run_catalog_analysis(db, workspace_id=w, request=AnalyticsCatalogRunRequest(analysis_key="revenue_overview", lookback_days=30), now=NOW, use_cache=False)
        assert _metric(total.rows[0], "net_paid_minor") == 420000


def test_package_sale_is_not_attributed_to_doctor_or_branch() -> None:
    engine = _engine()
    with Session(engine) as db:
        w, service, branch, staff, doctor, patient = [uuid4() for _ in range(6)]
        db.execute(text("INSERT INTO services VALUES (:id,:w,'Laser','EGP',1)"), {"id": service.hex, "w": w.hex})
        db.execute(text("INSERT INTO branches VALUES (:id,:w,'Main',1)"), {"id": branch.hex, "w": w.hex})
        db.execute(text("INSERT INTO staff VALUES (:id,:w,'Sara','Ali',1)"), {"id": staff.hex, "w": w.hex})
        db.execute(text("INSERT INTO doctors VALUES (:id,:w,:s,1)"), {"id": doctor.hex, "w": w.hex, "s": staff.hex})
        db.execute(text("INSERT INTO patients VALUES (:id,:w,'Mona','Ali','01000000000','active',1,'2026-01-01','2026-01-01','2026-01-01')"), {"id": patient.hex, "w": w.hex})
        purchase = uuid4()
        db.execute(text("INSERT INTO payment_transactions VALUES (:id,:w,:p,'payment',480000,'EGP',NULL,'2026-08-10',NULL)"), {"id": purchase.hex, "w": w.hex, "p": patient.hex})
        db.execute(text("INSERT INTO patient_packages VALUES (:id,:w,:p,:s,:tx,'6 Laser',6,480000,'EGP','2026-08-10','active','staff')"), {"id": uuid4().hex, "w": w.hex, "p": patient.hex, "s": service.hex, "tx": purchase.hex})
        db.commit()
        for key in ("revenue_by_doctor", "revenue_by_branch"):
            result = run_catalog_analysis(db, workspace_id=w, request=AnalyticsCatalogRunRequest(analysis_key=key, lookback_days=30), now=NOW, use_cache=False)
            assert all(_metric(row, "net_paid_minor") == 0 for row in result.rows)


def test_service_paying_patient_is_distinct_across_direct_payment_and_package_purchase() -> None:
    from app.schemas.analytics_business import AnalyticsBusinessPlan
    from app.services.analytics_business import execute_business_plan

    engine = _engine()
    with Session(engine) as db:
        w, service, branch, staff, doctor, patient = [uuid4() for _ in range(6)]
        db.execute(text("INSERT INTO services VALUES (:id,:w,'Laser','EGP',1)"), {"id": service.hex, "w": w.hex})
        db.execute(text("INSERT INTO branches VALUES (:id,:w,'Main',1)"), {"id": branch.hex, "w": w.hex})
        db.execute(text("INSERT INTO staff VALUES (:id,:w,'Sara','Ali',1)"), {"id": staff.hex, "w": w.hex})
        db.execute(text("INSERT INTO doctors VALUES (:id,:w,:s,1)"), {"id": doctor.hex, "w": w.hex, "s": staff.hex})
        db.execute(text("INSERT INTO patients VALUES (:id,:w,'Mona','Ali','01000000000','active',1,'2026-01-01','2026-01-01','2026-01-01')"), {"id": patient.hex, "w": w.hex})
        appointment = uuid4()
        db.execute(text("INSERT INTO appointments VALUES (:id,:w,:p,:b,:d,:s,'completed','staff','2026-08-05','2026-08-05','2026-08-05','2026-08-05')"), {"id": appointment.hex, "w": w.hex, "p": patient.hex, "b": branch.hex, "d": doctor.hex, "s": service.hex})
        direct = uuid4()
        db.execute(text("INSERT INTO payment_transactions VALUES (:id,:w,:p,'payment',100000,'EGP',NULL,'2026-08-05',NULL)"), {"id": direct.hex, "w": w.hex, "p": patient.hex})
        db.execute(text("INSERT INTO payment_allocations VALUES (:id,:w,:tx,:a,100000,'2026-08-05')"), {"id": uuid4().hex, "w": w.hex, "tx": direct.hex, "a": appointment.hex})
        purchase = uuid4()
        db.execute(text("INSERT INTO payment_transactions VALUES (:id,:w,:p,'payment',480000,'EGP',NULL,'2026-08-10',NULL)"), {"id": purchase.hex, "w": w.hex, "p": patient.hex})
        db.execute(text("INSERT INTO patient_packages VALUES (:id,:w,:p,:s,:tx,'6 Laser',6,480000,'EGP','2026-08-10','active','staff')"), {"id": uuid4().hex, "w": w.hex, "p": patient.hex, "s": service.hex, "tx": purchase.hex})
        db.commit()
        plan = AnalyticsBusinessPlan.model_validate({
            "kind": "business_analytics",
            "metrics": ["net_paid_minor", "paying_patients", "avg_net_paid_per_paying_patient_minor"],
            "group_by": ["service"],
            "lookback_days": 30,
            "start_date": None,
            "end_date": None,
            "comparison": "none",
            "service_ids": [],
            "branch_ids": [],
            "doctor_ids": [],
            "currency": "EGP",
            "limit": 10,
            "sort_metric": "net_paid_minor",
            "sort_direction": "desc",
            "reason": "test package payer de-duplication",
        })
        result = execute_business_plan(db, workspace_id=w, question="service revenue", plan=plan, now=NOW)
        row = next(row for row in result.rows if row.label == "Laser")
        assert _metric(row, "net_paid_minor") == 580000
        assert _metric(row, "paying_patients") == 1
        assert _metric(row, "avg_net_paid_per_paying_patient_minor") == 580000


def test_installment_package_payments_and_cancellation_refunds_stay_on_service() -> None:
    engine = _engine()
    with Session(engine) as db:
        w, service, patient, package = [uuid4() for _ in range(4)]
        db.execute(text("INSERT INTO services VALUES (:id,:w,'Full Body Laser','EGP',1)"), {"id": service.hex, "w": w.hex})
        db.execute(text("INSERT INTO patients VALUES (:id,:w,'Mona','Ali','01000000000','active',1,'2026-01-01','2026-01-01','2026-01-01')"), {"id": patient.hex, "w": w.hex})
        first, second = uuid4(), uuid4()
        db.execute(
            text("INSERT INTO payment_transactions VALUES (:id,:w,:p,'payment',600000,'EGP',NULL,'2026-08-01',:pkg)"),
            {"id": first.hex, "w": w.hex, "p": patient.hex, "pkg": package.hex},
        )
        db.execute(
            text("INSERT INTO payment_transactions VALUES (:id,:w,:p,'payment',600000,'EGP',NULL,'2026-08-05',:pkg)"),
            {"id": second.hex, "w": w.hex, "p": patient.hex, "pkg": package.hex},
        )
        db.execute(
            text("INSERT INTO patient_packages VALUES (:id,:w,:p,:s,:tx,'6 Full Body',6,1200000,'EGP','2026-08-01','cancelled','staff')"),
            {"id": package.hex, "w": w.hex, "p": patient.hex, "s": service.hex, "tx": first.hex},
        )
        refund_a, refund_b = uuid4(), uuid4()
        db.execute(
            text("INSERT INTO payment_transactions VALUES (:id,:w,:p,'refund',600000,'EGP',:ref,'2026-08-20',:pkg)"),
            {"id": refund_a.hex, "w": w.hex, "p": patient.hex, "ref": second.hex, "pkg": package.hex},
        )
        db.execute(
            text("INSERT INTO payment_transactions VALUES (:id,:w,:p,'refund',350000,'EGP',:ref,'2026-08-20',:pkg)"),
            {"id": refund_b.hex, "w": w.hex, "p": patient.hex, "ref": first.hex, "pkg": package.hex},
        )
        db.commit()

        by_service = run_catalog_analysis(
            db,
            workspace_id=w,
            request=AnalyticsCatalogRunRequest(analysis_key="revenue_by_service", lookback_days=30),
            now=NOW,
            use_cache=False,
        )
        row = next(row for row in by_service.rows if row.label == "Full Body Laser")
        assert _metric(row, "net_paid_minor") == 250_000

        total = run_catalog_analysis(
            db,
            workspace_id=w,
            request=AnalyticsCatalogRunRequest(analysis_key="revenue_overview", lookback_days=30),
            now=NOW,
            use_cache=False,
        )
        assert _metric(total.rows[0], "net_paid_minor") == 250_000
