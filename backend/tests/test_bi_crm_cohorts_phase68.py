from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path
from uuid import uuid4

import pytest
from sqlalchemy import create_engine, func, select, text
from sqlalchemy.orm import Session

from app.models.crm_cohort import CRMCohort, CRMCohortMember
from app.models.crm_task import CRMTask
from app.schemas.analytics_bi import AnalyticsBIPlan
from app.services.crm_cohorts import (
    CRMCohortError,
    create_analytics_cohort,
    create_cohort_follow_up_tasks,
)

NOW = datetime(2026, 8, 27, 0, 0, tzinfo=UTC)


def _schema(engine) -> None:
    ddl = [
        "CREATE TABLE services (id CHAR(32) PRIMARY KEY, workspace_id CHAR(32), name VARCHAR(160), is_active BOOLEAN)",
        "CREATE TABLE branches (id CHAR(32) PRIMARY KEY, workspace_id CHAR(32), name VARCHAR(160), is_active BOOLEAN)",
        "CREATE TABLE staff (id CHAR(32) PRIMARY KEY, workspace_id CHAR(32), first_name VARCHAR(120), last_name VARCHAR(120), is_active BOOLEAN)",
        "CREATE TABLE doctors (id CHAR(32) PRIMARY KEY, workspace_id CHAR(32), staff_id CHAR(32), is_active BOOLEAN)",
        """
        CREATE TABLE patients (
            id CHAR(32) PRIMARY KEY, workspace_id CHAR(32), first_name VARCHAR(120), last_name VARCHAR(120),
            phone VARCHAR(40), phone_normalized VARCHAR(40), status VARCHAR(20), source_created_at DATETIME,
            created_at DATETIME, updated_at DATETIME
        )
        """,
        """
        CREATE TABLE appointments (
            id CHAR(32) PRIMARY KEY, workspace_id CHAR(32), patient_id CHAR(32), branch_id CHAR(32),
            doctor_id CHAR(32), service_id CHAR(32), status VARCHAR(20), start_at DATETIME, end_at DATETIME,
            created_at DATETIME, updated_at DATETIME
        )
        """,
        """
        CREATE TABLE payment_transactions (
            id CHAR(32) PRIMARY KEY, workspace_id CHAR(32), patient_id CHAR(32), transaction_type VARCHAR(16),
            amount_minor INTEGER, currency VARCHAR(3), created_at DATETIME
        )
        """,
        """
        CREATE TABLE payment_allocations (
            id CHAR(32) PRIMARY KEY, workspace_id CHAR(32), transaction_id CHAR(32), appointment_id CHAR(32),
            amount_minor INTEGER, created_at DATETIME
        )
        """,
        """
        CREATE TABLE crm_cohorts (
            id CHAR(32) PRIMARY KEY, workspace_id CHAR(32), created_by_user_id CHAR(32), name VARCHAR(160),
            request_key VARCHAR(64), source VARCHAR(24), status VARCHAR(16), analytics_operation VARCHAR(48), question TEXT, plan TEXT,
            period_label VARCHAR(120), member_count INTEGER, created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
            updated_at DATETIME DEFAULT CURRENT_TIMESTAMP
        )
        """,
        """
        CREATE TABLE crm_cohort_members (
            id CHAR(32) PRIMARY KEY, workspace_id CHAR(32), cohort_id CHAR(32), patient_id CHAR(32), rank INTEGER,
            snapshot_metrics TEXT, created_at DATETIME DEFAULT CURRENT_TIMESTAMP, updated_at DATETIME DEFAULT CURRENT_TIMESTAMP
        )
        """,
        """
        CREATE TABLE crm_tasks (
            id CHAR(32) PRIMARY KEY, workspace_id CHAR(32), patient_id CHAR(32), lead_id CHAR(32), conversation_id CHAR(32),
            assigned_user_id CHAR(32), created_by_user_id CHAR(32), completed_by_user_id CHAR(32), task_type VARCHAR(24),
            source VARCHAR(20), status VARCHAR(20), execution_mode VARCHAR(16), priority VARCHAR(20), title VARCHAR(200),
            description TEXT, due_at DATETIME, completed_at DATETIME, dedupe_key VARCHAR(255),
            created_at DATETIME DEFAULT CURRENT_TIMESTAMP, updated_at DATETIME DEFAULT CURRENT_TIMESTAMP
        )
        """,
        """
        CREATE TABLE activity_events (
            id CHAR(32) PRIMARY KEY, workspace_id CHAR(32), actor_type VARCHAR(20), actor_user_id CHAR(32),
            action VARCHAR(80), entity_type VARCHAR(40), entity_id CHAR(32), summary VARCHAR(500), metadata JSON,
            created_at DATETIME DEFAULT CURRENT_TIMESTAMP
        )
        """,
    ]
    with engine.begin() as conn:
        for statement in ddl:
            conn.exec_driver_sql(statement)


def _plan(operation="lapsed_patients", **updates) -> AnalyticsBIPlan:
    payload = {
        "operation": operation,
        "lookback_days": None,
        "inactivity_days": 180 if operation == "lapsed_patients" else None,
        "limit": 10,
        "service_ids": [],
        "branch_ids": [],
        "doctor_ids": [],
        "currency": None,
        "patient_name": None,
        "patient_phone": None,
        "reason": "test",
    }
    payload.update(updates)
    return AnalyticsBIPlan.model_validate(payload)


def _seed(db: Session):
    ids = {key: uuid4() for key in ("workspace", "user", "service", "branch", "staff", "doctor", "recent", "lapsed")}
    w = ids["workspace"].hex
    db.execute(text("INSERT INTO services (id,workspace_id,name,is_active) VALUES (:id,:w,'Laser',1)"), {"id": ids["service"].hex, "w": w})
    db.execute(text("INSERT INTO branches (id,workspace_id,name,is_active) VALUES (:id,:w,'Main',1)"), {"id": ids["branch"].hex, "w": w})
    db.execute(text("INSERT INTO staff (id,workspace_id,first_name,last_name,is_active) VALUES (:id,:w,'Sara','Hassan',1)"), {"id": ids["staff"].hex, "w": w})
    db.execute(text("INSERT INTO doctors (id,workspace_id,staff_id,is_active) VALUES (:id,:w,:s,1)"), {"id": ids["doctor"].hex, "w": w, "s": ids["staff"].hex})
    for pid, first, phone in ((ids["recent"], "Mona", "01000000001"), (ids["lapsed"], "Nour", "01000000002")):
        db.execute(
            text("INSERT INTO patients (id,workspace_id,first_name,last_name,phone,phone_normalized,status,source_created_at,created_at,updated_at) VALUES (:id,:w,:first,'Ali',:phone,:phone,'active','2023-01-01','2026-01-01','2026-01-01')"),
            {"id": pid.hex, "w": w, "first": first, "phone": phone},
        )
    for pid, at in ((ids["recent"], "2026-08-20T10:00:00+00:00"), (ids["lapsed"], "2025-10-10T10:00:00+00:00")):
        db.execute(
            text("INSERT INTO appointments (id,workspace_id,patient_id,branch_id,doctor_id,service_id,status,start_at,end_at,created_at,updated_at) VALUES (:id,:w,:p,:b,:d,:s,'completed',:at,:at,:at,:at)"),
            {"id": uuid4().hex, "w": w, "p": pid.hex, "b": ids["branch"].hex, "d": ids["doctor"].hex, "s": ids["service"].hex, "at": at},
        )
    db.commit()
    return ids


def _db():
    engine = create_engine("sqlite+pysqlite:///:memory:")
    _schema(engine)
    return engine


def test_analytics_patient_list_materializes_durable_snapshot() -> None:
    engine = _db()
    with Session(engine) as db:
        ids = _seed(db)
        cohort = create_analytics_cohort(
            db,
            workspace_id=ids["workspace"],
            created_by_user_id=ids["user"],
            request_id=uuid4(),
            name="عملاء غائبون 6 شهور",
            question="مين العملاء اللي اختفوا من 6 شهور؟",
            plan=_plan(),
            now=NOW,
        )
        assert cohort.member_count == 1
        member = db.scalar(select(CRMCohortMember).where(CRMCohortMember.cohort_id == cohort.id))
        assert member is not None
        assert member.patient_id == ids["lapsed"]
        assert cohort.analytics_operation == "lapsed_patients"
        assert cohort.plan_json["inactivity_days"] == 180



def test_cohort_creation_is_idempotent_per_request_id() -> None:
    engine = _db()
    with Session(engine) as db:
        ids = _seed(db)
        request_id = uuid4()
        first = create_analytics_cohort(
            db,
            workspace_id=ids["workspace"],
            created_by_user_id=ids["user"],
            request_id=request_id,
            name="Lapsed",
            question="مين العملاء اللي اختفوا؟",
            plan=_plan(),
            now=NOW,
        )
        second = create_analytics_cohort(
            db,
            workspace_id=ids["workspace"],
            created_by_user_id=ids["user"],
            request_id=request_id,
            name="Lapsed",
            question="مين العملاء اللي اختفوا؟",
            plan=_plan(),
            now=NOW,
        )
        assert first.id == second.id
        assert db.scalar(select(func.count(CRMCohort.id))) == 1
        assert db.scalar(select(func.count(CRMCohortMember.id))) == 1

def test_cohort_snapshot_does_not_change_when_clinic_data_changes() -> None:
    engine = _db()
    with Session(engine) as db:
        ids = _seed(db)
        cohort = create_analytics_cohort(
            db,
            workspace_id=ids["workspace"],
            created_by_user_id=ids["user"],
            request_id=uuid4(),
            name="Snapshot",
            question="مين العملاء اللي اختفوا؟",
            plan=_plan(),
            now=NOW,
        )
        new_patient = uuid4()
        db.execute(text("INSERT INTO patients (id,workspace_id,first_name,last_name,phone,phone_normalized,status,created_at,updated_at) VALUES (:id,:w,'Later','Patient','01000000003','01000000003','active','2024-01-01','2024-01-01')"), {"id": new_patient.hex, "w": ids["workspace"].hex})
        db.execute(text("INSERT INTO appointments (id,workspace_id,patient_id,branch_id,doctor_id,service_id,status,start_at,end_at,created_at,updated_at) VALUES (:id,:w,:p,:b,:d,:s,'completed','2025-01-01','2025-01-01','2025-01-01','2025-01-01')"), {"id": uuid4().hex, "w": ids["workspace"].hex, "p": new_patient.hex, "b": ids["branch"].hex, "d": ids["doctor"].hex, "s": ids["service"].hex})
        db.commit()
        members = list(db.scalars(select(CRMCohortMember).where(CRMCohortMember.cohort_id == cohort.id)).all())
        assert [m.patient_id for m in members] == [ids["lapsed"]]


def test_non_patient_analytics_cannot_become_cohort() -> None:
    engine = _db()
    with Session(engine) as db:
        ids = _seed(db)
        with pytest.raises(CRMCohortError, match="patient-list"):
            create_analytics_cohort(
                db,
                workspace_id=ids["workspace"],
                created_by_user_id=ids["user"],
                request_id=uuid4(),
                name="Not allowed",
                question="احسب الإيراد",
                plan=_plan("clinic_summary", inactivity_days=None),
                now=NOW,
            )


def test_follow_up_task_bulk_action_is_idempotent_per_request_id() -> None:
    engine = _db()
    with Session(engine) as db:
        ids = _seed(db)
        cohort = create_analytics_cohort(
            db,
            workspace_id=ids["workspace"],
            created_by_user_id=ids["user"],
            request_id=uuid4(),
            name="Lapsed",
            question="مين العملاء اللي اختفوا؟",
            plan=_plan(),
            now=NOW,
        )
        request_id = uuid4()
        first = create_cohort_follow_up_tasks(
            db,
            workspace_id=ids["workspace"],
            cohort_id=cohort.id,
            request_id=request_id,
            actor_user_id=ids["user"],
            assigned_user_id=None,
            title="Follow up with lapsed customer",
            description="Generated after staff confirmation from BI cohort.",
            priority="normal",
            due_at=datetime(2026, 8, 28, 10, tzinfo=UTC),
        )
        second = create_cohort_follow_up_tasks(
            db,
            workspace_id=ids["workspace"],
            cohort_id=cohort.id,
            request_id=request_id,
            actor_user_id=ids["user"],
            assigned_user_id=None,
            title="Follow up with lapsed customer",
            description="Generated after staff confirmation from BI cohort.",
            priority="normal",
            due_at=datetime(2026, 8, 28, 10, tzinfo=UTC),
        )
        assert first.created_tasks == 1 and first.reused_tasks == 0
        assert second.created_tasks == 0 and second.reused_tasks == 1
        assert first.task_ids == second.task_ids
        assert db.scalar(select(func.count(CRMTask.id))) == 1


def test_new_request_id_can_create_new_follow_up_campaign_for_same_cohort() -> None:
    engine = _db()
    with Session(engine) as db:
        ids = _seed(db)
        cohort = create_analytics_cohort(
            db,
            workspace_id=ids["workspace"],
            created_by_user_id=ids["user"],
            request_id=uuid4(),
            name="Lapsed",
            question="مين العملاء اللي اختفوا؟",
            plan=_plan(),
            now=NOW,
        )
        for request_id in (uuid4(), uuid4()):
            create_cohort_follow_up_tasks(
                db,
                workspace_id=ids["workspace"],
                cohort_id=cohort.id,
                request_id=request_id,
                actor_user_id=ids["user"],
                assigned_user_id=None,
                title="Follow up",
                description=None,
                priority="normal",
                due_at=datetime(2026, 8, 28, 10, tzinfo=UTC),
            )
        assert db.scalar(select(func.count(CRMTask.id))) == 2


def test_crm_cohort_write_path_never_invokes_llm_planner() -> None:
    source = Path(__file__).resolve().parents[1] / "app" / "services" / "crm_cohorts.py"
    text_source = source.read_text(encoding="utf-8")
    assert "plan_analytics_question" not in text_source
    assert "generateContent" not in text_source
    assert "google.genai" not in text_source


def test_cohort_migration_revision_is_short_and_follows_patient_history() -> None:
    migration = Path(__file__).resolve().parents[1] / "alembic" / "versions" / "0038_crm_cohorts.py"
    source = migration.read_text(encoding="utf-8")
    assert 'revision: str = "0038_crm_cohorts"' in source
    assert 'down_revision: str | Sequence[str] | None = "0037_patient_history"' in source
    assert len("0038_crm_cohorts") <= 32


def test_write_routes_live_under_crm_not_analytics_and_actions_are_human_only() -> None:
    root = Path(__file__).resolve().parents[1]
    crm_route = (root / "app/api/routes/crm.py").read_text(encoding="utf-8")
    analytics_route = (root / "app/api/routes/analytics.py").read_text(encoding="utf-8")
    service = (root / "app/services/crm_cohorts.py").read_text(encoding="utf-8")
    assert '"/cohorts/from-analytics"' in crm_route
    assert '"/cohorts/{cohort_id}/follow-up-tasks"' in crm_route
    assert "crm_cohort" not in analytics_route
    assert 'execution_mode="human"' in service
    assert 'execution_mode="ai"' not in service


def test_frontend_requires_explicit_cohort_then_task_confirmation() -> None:
    root = Path(__file__).resolve().parents[2]
    ui = (root / "frontend/src/app/(dashboard)/analytics/cohort-actions.tsx").read_text(encoding="utf-8")
    assert "احفظ الـcohort" in ui
    assert "مهام متابعة" in ui
    assert "مفيش رسائل أو outreach تلقائي" in ui
    assert "createClientRequestId" in ui
    assert "crypto.randomUUID" not in ui
