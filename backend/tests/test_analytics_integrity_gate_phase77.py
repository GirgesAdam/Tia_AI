from __future__ import annotations

from datetime import timedelta
from pathlib import Path
from uuid import uuid4

from sqlalchemy import text
from sqlalchemy.orm import Session

from app.services.analytics_catalog import _DEFINITIONS
from app.services.analytics_integrity import run_analytics_integrity_gate
from tests.test_deterministic_analytics_catalog_phase72 import NOW, _engine
from tests.test_deterministic_analytics_catalog_phase73 import _seed_phase73


def _add_campaign_tables(engine) -> None:
    ddl = [
        """CREATE TABLE crm_campaigns (
            id CHAR(32) PRIMARY KEY, workspace_id CHAR(32), cohort_id CHAR(32), channel_connection_id CHAR(32),
            created_by_user_id CHAR(32), confirmed_by_user_id CHAR(32), request_key VARCHAR(64), confirmation_key VARCHAR(64),
            name VARCHAR(160), status VARCHAR(16), template_name VARCHAR(160), template_language VARCHAR(32),
            body_parameter_keys TEXT, rate_limit_per_minute INTEGER, recipient_count INTEGER, eligible_count INTEGER,
            confirmed_at DATETIME, created_at DATETIME, updated_at DATETIME
        )""",
        """CREATE TABLE crm_campaign_recipients (
            id CHAR(32) PRIMARY KEY, workspace_id CHAR(32), campaign_id CHAR(32), patient_id CHAR(32), rank INTEGER,
            status VARCHAR(32), reason VARCHAR(120), conversation_id CHAR(32), channel_identity_id CHAR(32), message_id CHAR(32),
            dispatch_id CHAR(32), scheduled_at DATETIME, created_at DATETIME, updated_at DATETIME
        )""",
        """CREATE TABLE message_dispatches (
            id CHAR(32) PRIMARY KEY, workspace_id CHAR(32), channel_connection_id CHAR(32), message_id CHAR(32), status VARCHAR(20),
            attempts INTEGER, provider_message_id VARCHAR(255), last_error VARCHAR(2000), next_attempt_at DATETIME, locked_at DATETIME,
            sent_at DATETIME, delivered_at DATETIME, read_at DATETIME, metadata TEXT, created_at DATETIME, updated_at DATETIME
        )""",
        """CREATE TABLE crm_campaign_conversions (
            id CHAR(32) PRIMARY KEY, workspace_id CHAR(32), campaign_id CHAR(32), recipient_id CHAR(32), patient_id CHAR(32),
            conversation_id CHAR(32), original_appointment_id CHAR(32), appointment_id CHAR(32), response_message_id CHAR(32),
            attribution_kind VARCHAR(48), campaign_sent_at DATETIME, patient_replied_at DATETIME, booked_at DATETIME,
            created_at DATETIME, updated_at DATETIME
        )""",
    ]
    with engine.begin() as conn:
        for statement in ddl:
            conn.exec_driver_sql(statement)


def _seed_scale_rows(db: Session, ids: dict, *, patients: int = 1200) -> None:
    patient_rows = []
    appointment_rows = []
    tx_rows = []
    allocation_rows = []
    services = [ids["laser"], ids["prp"]]

    for index in range(patients):
        patient_id = uuid4()
        patient_rows.append(
            {
                "id": patient_id.hex,
                "w": ids["workspace"].hex,
                "first": f"Scale{index}",
                "phone": f"0119{index:07d}",
                "created": (NOW - timedelta(days=(index % 700) + 20)).replace(tzinfo=None).isoformat(),
            }
        )
        visit_count = 1 + (index % 4)
        for visit in range(visit_count):
            appointment_id = uuid4()
            at = NOW - timedelta(days=(index % 300) + visit * 14 + 1, hours=index % 20)
            status = "completed"
            if visit == visit_count - 1 and index % 17 == 0:
                status = "no_show"
            elif visit == visit_count - 1 and index % 19 == 0:
                status = "cancelled"
            service = services[(index + visit) % len(services)]
            appointment_rows.append(
                {
                    "id": appointment_id.hex,
                    "w": ids["workspace"].hex,
                    "p": patient_id.hex,
                    "b": ids["branch"].hex,
                    "d": ids["doctor"].hex,
                    "s": service.hex,
                    "status": status,
                    "source": "whatsapp" if index % 2 == 0 else "phone",
                    "at": at.replace(tzinfo=None).isoformat(),
                }
            )
            if status == "completed" and index % 5 != 0:
                transaction_id = uuid4()
                amount = 80_000 + ((index + visit) % 5) * 25_000
                tx_rows.append(
                    {
                        "id": transaction_id.hex,
                        "w": ids["workspace"].hex,
                        "p": patient_id.hex,
                        "amount": amount,
                        "at": (at + timedelta(hours=1)).replace(tzinfo=None).isoformat(),
                    }
                )
                allocation_rows.append(
                    {
                        "id": uuid4().hex,
                        "w": ids["workspace"].hex,
                        "tx": transaction_id.hex,
                        "appointment": appointment_id.hex,
                        "amount": amount,
                        "at": (at + timedelta(hours=1)).replace(tzinfo=None).isoformat(),
                    }
                )

    db.execute(
        text(
            "INSERT INTO patients (id,workspace_id,first_name,last_name,phone,status,marketing_consent,source_created_at,created_at,updated_at) "
            "VALUES (:id,:w,:first,'Validation',:phone,'active',1,:created,:created,:created)"
        ),
        patient_rows,
    )
    db.execute(
        text(
            "INSERT INTO appointments (id,workspace_id,patient_id,branch_id,doctor_id,service_id,status,source,start_at,end_at,created_at,updated_at) "
            "VALUES (:id,:w,:p,:b,:d,:s,:status,:source,:at,:at,:at,:at)"
        ),
        appointment_rows,
    )
    db.execute(
        text(
            "INSERT INTO payment_transactions (id,workspace_id,patient_id,transaction_type,amount_minor,currency,created_at) "
            "VALUES (:id,:w,:p,'payment',:amount,'EGP',:at)"
        ),
        tx_rows,
    )
    db.execute(
        text(
            "INSERT INTO payment_allocations (id,workspace_id,transaction_id,appointment_id,amount_minor,created_at) "
            "VALUES (:id,:w,:tx,:appointment,:amount,:at)"
        ),
        allocation_rows,
    )
    db.commit()


def _seed_campaign(db: Session, ids: dict) -> None:
    campaign, cohort, connection, recipient, dispatch, message, conversation = (uuid4() for _ in range(7))
    appointment = ids["laser_recent"]
    patient = ids["recent"]
    sent = (NOW - timedelta(days=2)).replace(tzinfo=None)
    db.execute(
        text(
            "INSERT INTO crm_campaigns "
            "(id,workspace_id,cohort_id,channel_connection_id,created_by_user_id,confirmed_by_user_id,request_key,confirmation_key,name,status,template_name,template_language,body_parameter_keys,rate_limit_per_minute,recipient_count,eligible_count,confirmed_at,created_at,updated_at) "
            "VALUES (:id,:w,:cohort,:connection,NULL,NULL,'phase77','confirm','Validation campaign','confirmed','validation_ar','ar','[]',10,1,1,:sent,:sent,:sent)"
        ),
        {"id": campaign.hex, "w": ids["workspace"].hex, "cohort": cohort.hex, "connection": connection.hex, "sent": sent},
    )
    db.execute(
        text(
            "INSERT INTO message_dispatches "
            "(id,workspace_id,channel_connection_id,message_id,status,attempts,provider_message_id,last_error,next_attempt_at,locked_at,sent_at,delivered_at,read_at,metadata,created_at,updated_at) "
            "VALUES (:id,:w,:connection,:message,'read',1,'phase77-provider',NULL,NULL,NULL,:sent,:sent,:sent,'{}',:sent,:sent)"
        ),
        {"id": dispatch.hex, "w": ids["workspace"].hex, "connection": connection.hex, "message": message.hex, "sent": sent},
    )
    db.execute(
        text(
            "INSERT INTO crm_campaign_recipients "
            "(id,workspace_id,campaign_id,patient_id,rank,status,reason,conversation_id,channel_identity_id,message_id,dispatch_id,scheduled_at,created_at,updated_at) "
            "VALUES (:id,:w,:campaign,:patient,1,'read',NULL,:conversation,NULL,:message,:dispatch,:sent,:sent,:sent)"
        ),
        {
            "id": recipient.hex,
            "w": ids["workspace"].hex,
            "campaign": campaign.hex,
            "patient": patient.hex,
            "conversation": conversation.hex,
            "message": message.hex,
            "dispatch": dispatch.hex,
            "sent": sent,
        },
    )
    db.execute(
        text(
            "INSERT INTO crm_campaign_conversions "
            "(id,workspace_id,campaign_id,recipient_id,patient_id,conversation_id,original_appointment_id,appointment_id,response_message_id,attribution_kind,campaign_sent_at,patient_replied_at,booked_at,created_at,updated_at) "
            "VALUES (:id,:w,:campaign,:recipient,:patient,:conversation,:appointment,:appointment,:response,'direct_same_conversation_response',:sent,:reply,:reply,:reply,:reply)"
        ),
        {
            "id": uuid4().hex,
            "w": ids["workspace"].hex,
            "campaign": campaign.hex,
            "recipient": recipient.hex,
            "patient": patient.hex,
            "conversation": conversation.hex,
            "appointment": appointment.hex,
            "response": uuid4().hex,
            "sent": sent,
            "reply": (NOW - timedelta(days=1)).replace(tzinfo=None),
        },
    )
    db.commit()


def test_phase77_integrity_gate_reconciles_large_fixture_and_smokes_all_analyses() -> None:
    engine = _engine()
    _add_campaign_tables(engine)
    with Session(engine) as db:
        ids = _seed_phase73(db)
        _seed_scale_rows(db, ids)
        _seed_campaign(db, ids)
        report = run_analytics_integrity_gate(db, workspace_id=ids["workspace"], now=NOW)
        assert report.catalog_analysis_count == 35 == len(_DEFINITIONS)
        assert report.catalog_failures == ()
        assert report.passed, [check for check in report.checks if not check.passed]
        assert {check.key for check in report.checks}.issuperset(
            {
                "appointments.appointments",
                "revenue.net_paid_minor",
                "revenue.by_service_allocation_only",
                "retention.second_visit",
                "retention.third_visit",
                "campaign.sent_count",
                "campaign.attributed_revenue_minor",
            }
        )


def test_phase77_live_gate_is_read_only_and_supports_postgres_explain_analyze() -> None:
    root = Path(__file__).resolve().parents[1]
    service = (root / "app/services/analytics_integrity.py").read_text(encoding="utf-8")
    script = (root / "scripts/run_analytics_integrity_gate.py").read_text(encoding="utf-8")
    assert "EXPLAIN (ANALYZE, BUFFERS, FORMAT JSON)" in service
    assert "include_postgres_explain" in service
    assert "--explain" in script and "--max-query-ms" in script
    assert ".commit(" not in service and ".add(" not in service and ".delete(" not in service


def test_phase77_retires_public_ai_analytics_routes_and_cleans_metric_copy() -> None:
    root = Path(__file__).resolve().parents[1]
    route = (root / "app/api/routes/analytics.py").read_text(encoding="utf-8")
    business = (root / "app/services/analytics_business.py").read_text(encoding="utf-8")
    assert '@router.post("/ask"' not in route
    assert '@router.post("/compose"' not in route
    assert "analytics_planner" not in route and "analytics_orchestrator" not in route
    assert '"no_show_appointments": "حالات عدم الحضور"' in business
    assert '"no_show_rate": "نسبة عدم الحضور"' in business
    assert '"refunded_minor": "المبالغ المرتجعة"' in business
    assert '"same_service_repeat_rate": "العودة لنفس الخدمة"' in business
