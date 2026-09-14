"""Functional release gate on migrated CI PostgreSQL or explicitly pinned Staging.

Every service commit stays inside an outer transaction which is rolled back.
HTTP is blocked by default; provider tests inject only controlled responses.
This is engine/DB evidence, never live Meta or deployed Staging evidence.
"""

import os
from datetime import UTC, datetime, timedelta
from types import SimpleNamespace
from uuid import uuid4

import httpx
import pytest
from sqlalchemy import create_engine, func, select
from sqlalchemy.engine import make_url
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.meta_whatsapp_config import meta_whatsapp_settings
from app.models.appointment import Appointment
from app.models.automation_job import AutomationJob
from app.models.branch import Branch
from app.models.channel_connection import ChannelConnection
from app.models.channel_delivery_event import ChannelDeliveryEvent
from app.models.channel_identity import ChannelIdentity
from app.models.doctor import Doctor
from app.models.message import Message
from app.models.message_dispatch import MessageDispatch
from app.models.patient import Patient
from app.models.service import Service
from app.models.staff import Staff
from app.models.workspace import Workspace
from app.services import automations, channels
from app.services import meta_whatsapp_transport as transport


@pytest.fixture
def case(monkeypatch):
    url = make_url(os.environ["DATABASE_URL"])
    staging_ref = "ycuxjlkhnubztgqmhtom"
    staging = os.environ.get("AUTOMATION_GATE_STAGING_PROJECT") == staging_ref
    if staging:
        direct = url.host == f"db.{staging_ref}.supabase.co"
        pooled = (url.host or "").endswith(
            ".pooler.supabase.com"
        ) and url.username == f"postgres.{staging_ref}"
        if not (direct or pooled) or url.database != "postgres":
            pytest.fail("Staging gate DB URL must identify the approved Staging project.")
    elif url.host not in {"localhost", "127.0.0.1", "::1"} or url.database != "ci_db":
        pytest.fail("Automation DB gate requires disposable local ci_db.")
    if settings.environment != "test":
        pytest.fail("Automation DB gate requires ENVIRONMENT=test.")

    def block_http(*args, **kwargs):
        raise AssertionError("External HTTP is forbidden in the automation DB gate")

    monkeypatch.setattr(httpx.Client, "send", block_http)
    monkeypatch.setattr(httpx.AsyncClient, "send", block_http)
    monkeypatch.setattr(settings, "demo_mode", False)
    monkeypatch.setattr(settings, "channel_dispatch_max_attempts", 3)
    monkeypatch.setattr(meta_whatsapp_settings, "meta_graph_api_version", "v23.0")
    engine = create_engine(url, connect_args={"connect_timeout": 3})
    try:
        conn = engine.connect()
    except Exception:
        engine.dispose()
        if os.environ.get("CI") or staging:
            raise
        pytest.skip("Start disposable local ci_db and apply Alembic migrations")
    outer = conn.begin()
    db = Session(bind=conn, join_transaction_mode="create_savepoint")
    try:
        now = datetime.now(UTC).replace(microsecond=0)
        workspace = Workspace(name="Automation gate", slug=f"gate-{uuid4()}", timezone="UTC")
        db.add(workspace)
        db.flush()
        workspace_id = workspace.id
        patient = Patient(
            workspace_id=workspace.id,
            first_name="Gate",
            phone="01001112223",
            status="active",
            whatsapp_opt_in=True,
        )
        branch = Branch(
            workspace_id=workspace.id, name="Cairo", code="gate", timezone="Africa/Cairo"
        )
        staff = Staff(workspace_id=workspace.id, first_name="Gate", last_name="Doctor")
        service = Service(
            workspace_id=workspace.id, name="Gate service", slug="gate", duration_minutes=30
        )
        connection = ChannelConnection(
            workspace_id=workspace.id,
            channel="whatsapp",
            provider="meta_cloud",
            display_name="Gate",
            external_account_id=str(uuid4()),
            adapter_token_hash=uuid4().hex + uuid4().hex,
            config_json={"runtime_kind": "real"},
        )
        db.add_all([patient, branch, staff, service, connection])
        db.flush()
        doctor = Doctor(workspace_id=workspace.id, staff_id=staff.id)
        db.add(doctor)
        db.flush()
        start = now + timedelta(hours=6)
        appointment = Appointment(
            workspace_id=workspace.id,
            patient_id=patient.id,
            branch_id=branch.id,
            doctor_id=doctor.id,
            service_id=service.id,
            status="confirmed",
            start_at=start,
            end_at=start + timedelta(minutes=30),
            busy_start_at=start,
            busy_end_at=start + timedelta(minutes=30),
            duration_minutes=30,
            created_at=now - timedelta(days=2),
        )
        db.add(appointment)
        rules = automations.ensure_default_rules(db, workspace.id)
        rule = next(r for r in rules if r.key == "appointment_reminder_6h")
        yield SimpleNamespace(
            db=db,
            now=now,
            workspace=workspace,
            patient=patient,
            appointment=appointment,
            connection=connection,
            rule=rule,
            rules=rules,
        )
    finally:
        db.close()
        outer.rollback()
        try:
            if "workspace_id" in locals():
                assert conn.scalar(select(Workspace.id).where(Workspace.id == workspace_id)) is None
        finally:
            conn.close()
            engine.dispose()


def plan(case):
    automations.plan_automation_jobs(case.db, workspace_id=case.workspace.id, now=case.now)
    return case.db.scalar(
        select(AutomationJob).where(AutomationJob.workspace_id == case.workspace.id)
    )


def execute(case):
    job = plan(case)
    claimed = automations.claim_due_jobs(
        case.db, workspace_id=case.workspace.id, limit=10, now=case.now
    )
    assert [c.job_id for c in claimed] == [job.id]
    result = automations.execute_job(
        case.db, workspace_id=case.workspace.id, job_id=job.id, now=case.now
    )
    return result.job


def claim(case):
    return channels.claim_dispatches(case.db, connection=case.connection, limit=10)


def record(case, dispatch_id, status="sent", provider_id="wamid.gate", retry=None, metadata=None):
    return channels.record_dispatch_result(
        case.db,
        connection=case.connection,
        dispatch_id=dispatch_id,
        result_status=status,
        provider_message_id=provider_id,
        error="controlled failure" if status == "failed" else None,
        retry_after_seconds=retry,
        metadata=metadata or {},
    )


def webhook(case, status, timestamp=None, provider_id="wamid.gate"):
    return transport.ingest_meta_webhook(
        case.db,
        {
            "entry": [
                {
                    "changes": [
                        {
                            "value": {
                                "metadata": {
                                    "phone_number_id": case.connection.external_account_id
                                },
                                "statuses": [
                                    {
                                        "id": provider_id,
                                        "status": status,
                                        "timestamp": str(timestamp or int(case.now.timestamp())),
                                        "recipient_id": "201001112223",
                                    }
                                ],
                            }
                        }
                    ]
                }
            ]
        },
    )


def test_reminder_plan_claim_execute_payload_and_dedupe(case):
    job = execute(case)
    assert job.scheduled_for == case.now
    assert plan(case).id == job.id
    assert (
        automations.claim_due_jobs(case.db, workspace_id=case.workspace.id, limit=10, now=case.now)
        == []
    )
    repeated = automations.execute_job(
        case.db, workspace_id=case.workspace.id, job_id=job.id, now=case.now
    )
    assert repeated.job.dispatch_id == job.dispatch_id
    assert (
        case.db.scalar(
            select(func.count())
            .select_from(MessageDispatch)
            .where(MessageDispatch.workspace_id == case.workspace.id)
        )
        == 1
    )
    (item,) = claim(case)
    assert item.external_user_id == "201001112223"
    assert (
        case.db.scalar(
            select(ChannelIdentity).where(ChannelIdentity.workspace_id == case.workspace.id)
        ).patient_id
        == case.patient.id
    )
    display = item.metadata["appointment"]
    assert display["timezone"] == "Africa/Cairo"  # branch overrides workspace UTC
    from zoneinfo import ZoneInfo

    expected_time = case.appointment.start_at.astimezone(ZoneInfo("Africa/Cairo")).strftime("%H:%M")
    body = transport.build_meta_message_payload(item)
    assert body["to"] == "201001112223"
    assert body["template"]["name"] == "tia_reminder_01"
    params = body["template"]["components"][0]["parameters"]
    assert [p["text"] for p in params] == ["Gate", "Gate service", expected_time]
    assert claim(case) == []


def test_post_visit_follows_completion_anchor(case):
    case.rule.enabled = False
    followup = next(r for r in case.rules if r.key == "post_visit_followup")
    followup.enabled = True
    case.appointment.status = "completed"
    case.appointment.completed_at = case.now - timedelta(days=1)
    case.db.commit()
    job = execute(case)
    assert job.scheduled_for == case.now
    (item,) = claim(case)
    assert item.metadata["whatsapp_template"]["name"] == "tia_post_visit_01"


@pytest.mark.parametrize(
    "status,opt_in,reason",
    [
        ("blocked", True, "patient_not_active"),
        ("inactive", True, "patient_not_active"),
        ("active", False, "whatsapp_opt_in_required"),
    ],
)
def test_ineligible_patient_does_not_create_dispatch(case, status, opt_in, reason):
    case.patient.status = status
    case.patient.whatsapp_opt_in = opt_in
    case.db.commit()
    job = execute(case)
    assert job.status == "skipped"
    assert job.result_json["reason"] == reason
    assert (
        case.db.scalar(
            select(func.count())
            .select_from(MessageDispatch)
            .where(MessageDispatch.workspace_id == case.workspace.id)
        )
        == 0
    )


@pytest.mark.parametrize("change", ["reschedule", "cancel", "disable"])
def test_lifecycle_invalidates_queued_delivery(case, change):
    job = execute(case)
    old_dispatch = case.db.get(MessageDispatch, job.dispatch_id)
    old_message = case.db.get(Message, job.message_id)
    if change == "reschedule":
        for field in ("start_at", "end_at", "busy_start_at", "busy_end_at"):
            setattr(case.appointment, field, getattr(case.appointment, field) + timedelta(days=1))
    elif change == "cancel":
        case.appointment.status = "cancelled"
        case.appointment.cancelled_at = case.now
    else:
        case.rule.enabled = False
    case.db.commit()
    plan(case)
    assert old_dispatch.status == "cancelled"
    assert old_message.delivery_status == "cancelled"
    assert claim(case) == []
    assert job.status == ("queued" if change == "reschedule" else "cancelled")
    if change == "reschedule":
        assert job.scheduled_for == case.now + timedelta(days=1)
    if change == "disable":
        case.rule.enabled = True
        case.db.commit()
        replanned = execute(case)
        assert replanned.id == job.id
        assert replanned.dispatch_id != old_dispatch.id
        assert len(claim(case)) == 1


def test_overdue_dispatch_expires_before_provider_claim(case):
    job = execute(case)
    assert (
        transport._cancel_expired_automation_dispatches(
            case.db, connection=case.connection, now=case.now + timedelta(minutes=31)
        )
        == 1
    )
    assert job.status == "cancelled"
    assert claim(case) == []


def test_engine_reclaims_expired_lease_once(case):
    job = plan(case)
    assert (
        len(
            automations.claim_due_jobs(
                case.db, workspace_id=case.workspace.id, limit=10, now=case.now
            )
        )
        == 1
    )
    assert (
        automations.claim_due_jobs(case.db, workspace_id=case.workspace.id, limit=10, now=case.now)
        == []
    )
    reclaimed = automations.claim_due_jobs(
        case.db, workspace_id=case.workspace.id, limit=10, now=case.now + timedelta(minutes=11)
    )
    assert [(j.job_id, j.attempt) for j in reclaimed] == [(job.id, 2)]


def test_dispatch_lease_recovery_and_max_attempts(case):
    job = execute(case)
    (item,) = claim(case)
    dispatch = case.db.get(MessageDispatch, item.dispatch_id)
    dispatch.locked_at = case.now - timedelta(hours=1)
    case.db.commit()
    (recovered,) = claim(case)
    assert recovered.dispatch_id == item.dispatch_id
    assert recovered.attempt == 2
    dispatch.attempts = settings.channel_dispatch_max_attempts
    dispatch.locked_at = case.now - timedelta(hours=1)
    case.db.commit()
    assert claim(case) == []
    assert dispatch.status == "failed"
    assert case.db.get(Message, job.message_id).delivery_status == "failed"


def test_demo_guard_does_not_claim_or_mutate_queue(case, monkeypatch):
    job = execute(case)
    monkeypatch.setattr(settings, "demo_mode", True)
    monkeypatch.setattr(settings, "demo_allow_external_dispatch", False)
    assert claim(case) == []
    dispatch = case.db.get(MessageDispatch, job.dispatch_id)
    assert (dispatch.status, dispatch.attempts, dispatch.locked_at) == ("queued", 0, None)


def test_transient_failure_waits_then_retries_same_dispatch(case):
    job = execute(case)
    claim(case)
    before = datetime.now(UTC)
    dispatch = record(case, job.dispatch_id, status="failed", provider_id=None, retry=60)
    assert dispatch.status == "queued"
    assert (
        before + timedelta(seconds=60)
        <= dispatch.next_attempt_at
        <= datetime.now(UTC) + timedelta(seconds=60)
    )
    assert dispatch.locked_at is None
    assert case.db.get(Message, job.message_id).delivery_status == "queued"
    assert claim(case) == []
    dispatch.next_attempt_at = case.now - timedelta(seconds=1)
    case.db.commit()
    (item,) = claim(case)
    assert (item.dispatch_id, item.attempt) == (job.dispatch_id, 2)
    assert record(case, job.dispatch_id).status == "sent"
    assert claim(case) == []


@pytest.mark.parametrize("failure", ["permanent", "cap"])
def test_permanent_failure_or_exhaustion_is_terminal(case, failure):
    job = execute(case)
    claim(case)
    dispatch = case.db.get(MessageDispatch, job.dispatch_id)
    metadata = (
        {"errors": [{"code": 131031, "title": "Business Account locked"}]}
        if failure == "permanent"
        else {}
    )
    if failure == "cap":
        dispatch.attempts = settings.channel_dispatch_max_attempts
        case.db.commit()
    record(case, job.dispatch_id, status="failed", provider_id=None, retry=60, metadata=metadata)
    assert dispatch.status == "failed"
    assert dispatch.next_attempt_at is None
    assert dispatch.locked_at is None
    assert case.db.get(Message, job.message_id).delivery_status == "failed"
    assert claim(case) == []
    if failure == "permanent":
        assert case.connection.status == "paused"
    else:
        assert dispatch.metadata_json["retry_exhausted"] is True


def test_provider_id_persists_and_cannot_be_remapped(case):
    job = execute(case)
    claim(case)
    dispatch = record(case, job.dispatch_id)
    assert dispatch.provider_message_id == "wamid.gate"
    assert case.db.get(Message, job.message_id).external_message_id == "wamid.gate"
    assert record(case, job.dispatch_id).id == dispatch.id
    with pytest.raises(channels.ChannelConflictError):
        record(case, job.dispatch_id, provider_id="wamid.other")
    assert dispatch.provider_message_id == "wamid.gate"


def test_webhooks_update_db_and_audit_without_duplicates_or_downgrades(case):
    job = execute(case)
    claim(case)
    dispatch = record(case, job.dispatch_id)
    webhook(case, "delivered")
    webhook(case, "delivered")
    assert (
        case.db.scalar(
            select(func.count())
            .select_from(ChannelDeliveryEvent)
            .where(ChannelDeliveryEvent.workspace_id == case.workspace.id)
        )
        == 1
    )
    assert dispatch.status == "delivered"
    webhook(case, "read")
    webhook(case, "sent")
    webhook(case, "failed")
    assert dispatch.status == "read"
    assert case.db.get(Message, job.message_id).delivery_status == "read"
    assert dispatch.read_at == case.now
    events = list(
        case.db.scalars(
            select(ChannelDeliveryEvent).where(
                ChannelDeliveryEvent.workspace_id == case.workspace.id
            )
        )
    )
    assert len(events) == 4
    assert all(e.processed_at and e.provider_message_id == "wamid.gate" for e in events)
    assert all(e.payload_json["metadata"]["recipient_id"] == "201001112223" for e in events)


def test_webhook_before_send_result_is_reconciled(case):
    job = execute(case)
    claim(case)
    webhook(case, "read")
    event = case.db.scalar(
        select(ChannelDeliveryEvent).where(ChannelDeliveryEvent.workspace_id == case.workspace.id)
    )
    assert event.processed_at is None
    dispatch = record(case, job.dispatch_id)
    assert dispatch.status == "read"
    case.db.refresh(event)
    assert event.processed_at is not None
    webhook(case, "read")
    assert (
        case.db.scalar(
            select(func.count())
            .select_from(ChannelDeliveryEvent)
            .where(ChannelDeliveryEvent.workspace_id == case.workspace.id)
        )
        == 1
    )


@pytest.mark.parametrize("outcome", ["success", "transient", "permanent", "timeout"])
def test_native_transport_records_controlled_provider_response(case, monkeypatch, outcome):
    job = execute(case)
    (item,) = claim(case)
    calls = []

    def fake_post(url, **kwargs):
        calls.append(kwargs["json"])
        if outcome == "timeout":
            raise httpx.ConnectTimeout("controlled")
        if outcome == "success":
            return httpx.Response(200, json={"messages": [{"id": "wamid.gate"}]})
        code = 131031 if outcome == "permanent" else 130429
        return httpx.Response(
            400 if outcome == "permanent" else 429,
            json={"error": {"code": code, "message": "controlled"}},
        )

    monkeypatch.setattr(transport.httpx, "post", fake_post)
    accepted = transport._send_claimed_dispatch(
        case.db, connection=case.connection, token="test-only", item=item
    )
    assert accepted is (outcome == "success")
    assert len(calls) == 1
    assert calls[0]["to"] == "201001112223"
    dispatch = case.db.get(MessageDispatch, job.dispatch_id)
    expected = {
        "success": "sent",
        "transient": "queued",
        "permanent": "failed",
        "timeout": "queued",
    }[outcome]
    assert dispatch.status == expected
    assert case.db.get(Message, job.message_id).delivery_status == expected
    if outcome == "success":
        assert dispatch.provider_message_id == "wamid.gate"
        webhook(case, "delivered")
        assert dispatch.status == "delivered"
