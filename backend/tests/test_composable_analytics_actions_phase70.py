from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path
from uuid import uuid4

from sqlalchemy import create_engine, func, select, text
from sqlalchemy.orm import Session

from app.models.crm_cohort import CRMCohortMember
from app.models.crm_task import CRMTask
from app.schemas.analytics_composable import AnalyticsAudiencePlan
from app.services.analytics_audience import execute_audience_plan
from app.services.crm_cohorts import create_analytics_cohort, execute_confirmed_audience_action

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
            phone VARCHAR(40), phone_normalized VARCHAR(40), status VARCHAR(20), marketing_consent BOOLEAN,
            source_created_at DATETIME, created_at DATETIME, updated_at DATETIME
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


def _db():
    engine = create_engine("sqlite+pysqlite:///:memory:")
    _schema(engine)
    return engine


def _plan(**updates) -> AnalyticsAudiencePlan:
    payload = {
        "kind": "patient_audience",
        "lookback_days": None,
        "inactivity_days": None,
        "limit": 25,
        "service_ids": [],
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
        "reason": "test",
    }
    payload.update(updates)
    return AnalyticsAudiencePlan.model_validate(payload)


def _seed(db: Session):
    ids = {key: uuid4() for key in (
        "workspace", "user", "laser", "prp", "branch", "staff", "doctor",
        "recent", "old", "other", "recent_laser_1", "recent_laser_2", "old_laser", "other_prp",
    )}
    w = ids["workspace"].hex
    db.execute(text("INSERT INTO services (id,workspace_id,name,is_active) VALUES (:id,:w,'Laser',1)"), {"id": ids["laser"].hex, "w": w})
    db.execute(text("INSERT INTO services (id,workspace_id,name,is_active) VALUES (:id,:w,'PRP',1)"), {"id": ids["prp"].hex, "w": w})
    db.execute(text("INSERT INTO branches (id,workspace_id,name,is_active) VALUES (:id,:w,'Main',1)"), {"id": ids["branch"].hex, "w": w})
    db.execute(text("INSERT INTO staff (id,workspace_id,first_name,last_name,is_active) VALUES (:id,:w,'Sara','Hassan',1)"), {"id": ids["staff"].hex, "w": w})
    db.execute(text("INSERT INTO doctors (id,workspace_id,staff_id,is_active) VALUES (:id,:w,:s,1)"), {"id": ids["doctor"].hex, "w": w, "s": ids["staff"].hex})

    for pid, first, phone, consent in (
        (ids["recent"], "Mona", "01000000001", 1),
        (ids["old"], "Nour", "01000000002", 0),
        (ids["other"], "Laila", "01000000003", 1),
    ):
        db.execute(
            text("INSERT INTO patients (id,workspace_id,first_name,last_name,phone,phone_normalized,status,marketing_consent,source_created_at,created_at,updated_at) VALUES (:id,:w,:first,'Ali',:phone,:phone,'active',:consent,'2023-01-01','2026-01-01','2026-01-01')"),
            {"id": pid.hex, "w": w, "first": first, "phone": phone, "consent": consent},
        )

    appointments = (
        (ids["recent_laser_1"], ids["recent"], ids["laser"], "2026-08-01T10:00:00+00:00", "completed"),
        (ids["recent_laser_2"], ids["recent"], ids["laser"], "2026-07-01T10:00:00+00:00", "completed"),
        (ids["old_laser"], ids["old"], ids["laser"], "2025-10-01T10:00:00+00:00", "completed"),
        (ids["other_prp"], ids["other"], ids["prp"], "2026-08-10T10:00:00+00:00", "completed"),
    )
    for aid, patient, service, at, status in appointments:
        db.execute(
            text("INSERT INTO appointments (id,workspace_id,patient_id,branch_id,doctor_id,service_id,status,start_at,end_at,created_at,updated_at) VALUES (:id,:w,:p,:b,:d,:s,:status,:at,:at,:at,:at)"),
            {"id": aid.hex, "w": w, "p": patient.hex, "b": ids["branch"].hex, "d": ids["doctor"].hex, "s": service.hex, "status": status, "at": at},
        )

    future = uuid4()
    db.execute(
        text("INSERT INTO appointments (id,workspace_id,patient_id,branch_id,doctor_id,service_id,status,start_at,end_at,created_at,updated_at) VALUES (:id,:w,:p,:b,:d,:s,'confirmed','2026-09-10','2026-09-10','2026-08-20','2026-08-20')"),
        {"id": future.hex, "w": w, "p": ids["recent"].hex, "b": ids["branch"].hex, "d": ids["doctor"].hex, "s": ids["laser"].hex},
    )

    # Recent patient: 6,000 EGP explicitly allocated to Laser plus 20,000 unallocated.
    tx_recent_alloc = uuid4()
    db.execute(text("INSERT INTO payment_transactions (id,workspace_id,patient_id,transaction_type,amount_minor,currency,created_at) VALUES (:id,:w,:p,'payment',600000,'EGP','2026-08-02')"), {"id": tx_recent_alloc.hex, "w": w, "p": ids["recent"].hex})
    db.execute(text("INSERT INTO payment_allocations (id,workspace_id,transaction_id,appointment_id,amount_minor,created_at) VALUES (:id,:w,:tx,:a,600000,'2026-08-02')"), {"id": uuid4().hex, "w": w, "tx": tx_recent_alloc.hex, "a": ids["recent_laser_1"].hex})
    db.execute(text("INSERT INTO payment_transactions (id,workspace_id,patient_id,transaction_type,amount_minor,currency,created_at) VALUES (:id,:w,:p,'payment',2000000,'EGP','2026-08-03')"), {"id": uuid4().hex, "w": w, "p": ids["recent"].hex})

    # Old patient: huge unallocated payment must NOT qualify for Laser-attributed value.
    db.execute(text("INSERT INTO payment_transactions (id,workspace_id,patient_id,transaction_type,amount_minor,currency,created_at) VALUES (:id,:w,:p,'payment',5000000,'EGP','2026-01-03')"), {"id": uuid4().hex, "w": w, "p": ids["old"].hex})
    db.commit()
    return ids


def test_composable_audience_finds_laser_patients_in_last_six_months() -> None:
    engine = _db()
    with Session(engine) as db:
        ids = _seed(db)
        result = execute_audience_plan(
            db,
            workspace_id=ids["workspace"],
            plan=_plan(lookback_days=180, service_ids=[str(ids["laser"])]),
            now=NOW,
        )
        assert [row.key for row in result.rows] == [str(ids["recent"])]
        assert result.rows[0].metrics[0].value == 2


def test_composable_audience_combines_inactivity_future_booking_and_consent() -> None:
    engine = _db()
    with Session(engine) as db:
        ids = _seed(db)
        result = execute_audience_plan(
            db,
            workspace_id=ids["workspace"],
            plan=_plan(
                service_ids=[str(ids["laser"])],
                inactivity_days=180,
                has_future_appointment=False,
                marketing_consent=False,
            ),
            now=NOW,
        )
        assert [row.key for row in result.rows] == [str(ids["old"])]


def test_service_value_filter_uses_explicit_allocations_not_unallocated_patient_money() -> None:
    engine = _db()
    with Session(engine) as db:
        ids = _seed(db)
        result = execute_audience_plan(
            db,
            workspace_id=ids["workspace"],
            plan=_plan(
                service_ids=[str(ids["laser"])],
                min_net_paid_minor=500000,
                currency="EGP",
                sort_by="net_paid_desc",
            ),
            now=NOW,
        )
        assert [row.key for row in result.rows] == [str(ids["recent"])]
        money = next(metric for metric in result.rows[0].metrics if metric.key == "net_paid_minor")
        assert money.value == 600000


def test_composable_audience_can_be_saved_without_user_knowing_cohort_term() -> None:
    engine = _db()
    with Session(engine) as db:
        ids = _seed(db)
        saved = create_analytics_cohort(
            db,
            workspace_id=ids["workspace"],
            created_by_user_id=ids["user"],
            request_id=uuid4(),
            name="عملاء الليزر آخر 6 شهور",
            question="جمعلي الناس اللي عملوا ليزر آخر 6 شهور",
            plan=_plan(lookback_days=180, service_ids=[str(ids["laser"])]),
            now=NOW,
        )
        assert saved.analytics_operation == "patient_audience"
        assert saved.member_count == 1
        assert saved.plan_json["kind"] == "patient_audience"
        member = db.scalar(select(CRMCohortMember).where(CRMCohortMember.cohort_id == saved.id))
        assert member is not None and member.patient_id == ids["recent"]


def test_confirmed_follow_up_reexecutes_audience_and_is_idempotent() -> None:
    engine = _db()
    with Session(engine) as db:
        ids = _seed(db)
        audience_request_id = uuid4()
        action_request_id = uuid4()
        kwargs = dict(
            workspace_id=ids["workspace"],
            actor_user_id=ids["user"],
            audience_request_id=audience_request_id,
            action_request_id=action_request_id,
            name="عملاء الليزر",
            question="هاتلي اللي عملوا ليزر آخر 6 شهور واعمل follow up",
            plan=_plan(lookback_days=180, service_ids=[str(ids["laser"])]),
            action_kind="follow_up_tasks",
            priority="high",
            title="متابعة عملاء الليزر",
            description=None,
            due_at=datetime(2026, 8, 28, 10, 0, tzinfo=UTC),
            now=NOW,
        )
        audience, first, step = execute_confirmed_audience_action(db, **kwargs)
        assert step == "tasks_created"
        assert audience.member_count == 1
        assert first is not None and first.created_tasks == 1 and first.reused_tasks == 0

        audience2, second, step2 = execute_confirmed_audience_action(db, **kwargs)
        assert audience2.id == audience.id
        assert step2 == "tasks_created"
        assert second is not None and second.created_tasks == 0 and second.reused_tasks == 1
        assert db.scalar(select(func.count(CRMTask.id))) == 1


def test_whatsapp_action_only_materializes_audience_until_campaign_setup_is_confirmed() -> None:
    engine = _db()
    with Session(engine) as db:
        ids = _seed(db)
        audience, follow_up, step = execute_confirmed_audience_action(
            db,
            workspace_id=ids["workspace"],
            actor_user_id=ids["user"],
            audience_request_id=uuid4(),
            action_request_id=uuid4(),
            name="مجموعة ليزر",
            question="جمعهم وجهز حملة واتساب",
            plan=_plan(lookback_days=180, service_ids=[str(ids["laser"])]),
            action_kind="whatsapp_campaign",
            now=NOW,
        )
        assert audience.member_count == 1
        assert follow_up is None
        assert step == "campaign_setup"
        assert db.scalar(select(func.count(CRMTask.id))) == 0


def test_planner_is_semantic_and_user_does_not_need_the_word_cohort() -> None:
    root = Path(__file__).resolve().parents[1]
    planner = (root / "app/agents/analytics_orchestrator.py").read_text(encoding="utf-8").lower()
    schema = (root / "app/schemas/analytics_composable.py").read_text(encoding="utf-8").lower()
    route = (root / "app/api/routes/crm.py").read_text(encoding="utf-8").lower()
    assert "هاتلي" in planner
    assert "جمعلي الناس" in planner
    assert "reuse_previous_audience" in planner
    assert "re.compile" not in planner
    assert "re.search" not in planner
    assert "patient_ids" not in schema
    assert '"/audiences/actions/confirm"' in route
