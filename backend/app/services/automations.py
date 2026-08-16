from __future__ import annotations

import hashlib
import secrets
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from uuid import UUID
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from sqlalchemy import and_, or_, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.core.automation_rules import DEFAULT_AUTOMATION_RULES, scheduled_for
from app.models.appointment import Appointment
from app.models.automation_job import AutomationJob
from app.models.automation_rule import AutomationRule
from app.models.automation_worker import AutomationWorker
from app.models.branch import Branch
from app.models.channel_connection import ChannelConnection
from app.models.channel_identity import ChannelIdentity
from app.models.conversation import Conversation
from app.models.doctor import Doctor
from app.models.message import Message
from app.models.message_dispatch import MessageDispatch
from app.models.patient import Patient
from app.models.service import Service
from app.models.staff import Staff
from app.models.workspace import Workspace
from app.schemas.automation import AutomationClaimedJob


class AutomationError(ValueError):
    pass


@dataclass(frozen=True)
class PlanningResult:
    planned: int
    cancelled: int


@dataclass(frozen=True)
class ExecutionResult:
    job: AutomationJob
    reason: str | None


def generate_worker_token() -> tuple[str, str]:
    raw = "tia_auto_" + secrets.token_urlsafe(32)
    return raw, hashlib.sha256(raw.encode("utf-8")).hexdigest()


def worker_token_hash(raw: str) -> str:
    return hashlib.sha256(raw.strip().encode("utf-8")).hexdigest()


def get_worker_by_token(db: Session, raw_token: str) -> AutomationWorker | None:
    if not raw_token or not raw_token.strip():
        return None
    return db.scalar(
        select(AutomationWorker).where(
            AutomationWorker.token_hash == worker_token_hash(raw_token),
            AutomationWorker.status == "active",
        )
    )


def ensure_default_rules(db: Session, workspace_id: UUID, *, commit: bool = True) -> list[AutomationRule]:
    existing = {
        row.key: row
        for row in db.scalars(
            select(AutomationRule).where(AutomationRule.workspace_id == workspace_id)
        )
    }
    created = False
    for definition in DEFAULT_AUTOMATION_RULES:
        if definition.key in existing:
            continue
        row = AutomationRule(
            workspace_id=workspace_id,
            key=definition.key,
            name=definition.name,
            enabled=False,
            trigger_kind=definition.trigger_kind,
            offset_minutes=definition.offset_minutes,
            channel=definition.channel,
            template_name=definition.template_name,
            template_language=definition.template_language,
            max_lateness_minutes=definition.max_lateness_minutes,
            config_json={},
        )
        db.add(row)
        existing[row.key] = row
        created = True
    if created:
        if commit:
            db.commit()
        else:
            db.flush()
    return sorted(existing.values(), key=lambda row: row.key)


def _job_dedupe_key(appointment_id: UUID, rule_key: str) -> str:
    return f"appointment:{appointment_id}:rule:{rule_key}"


def _eligible_for_rule(appointment: Appointment, rule: AutomationRule) -> bool:
    if rule.trigger_kind in {"appointment_created", "before_appointment"}:
        return appointment.status in {"pending", "confirmed"}
    if rule.trigger_kind == "after_completed":
        return appointment.status == "completed" and appointment.completed_at is not None
    if rule.trigger_kind == "after_no_show":
        return appointment.status == "no_show" and appointment.no_show_at is not None
    return False


def _candidate_appointments(
    db: Session,
    *,
    workspace_id: UUID,
    rule: AutomationRule,
    now: datetime,
    horizon: datetime,
) -> list[Appointment]:
    if rule.trigger_kind in {"appointment_created", "before_appointment"}:
        return list(
            db.scalars(
                select(Appointment).where(
                    Appointment.workspace_id == workspace_id,
                    Appointment.status.in_(("pending", "confirmed")),
                    Appointment.start_at > now,
                    Appointment.start_at <= horizon,
                )
            )
        )
    if rule.trigger_kind == "after_completed":
        oldest = now - timedelta(days=14)
        return list(
            db.scalars(
                select(Appointment).where(
                    Appointment.workspace_id == workspace_id,
                    Appointment.status == "completed",
                    Appointment.completed_at.is_not(None),
                    Appointment.completed_at >= oldest,
                )
            )
        )
    if rule.trigger_kind == "after_no_show":
        oldest = now - timedelta(days=7)
        return list(
            db.scalars(
                select(Appointment).where(
                    Appointment.workspace_id == workspace_id,
                    Appointment.status == "no_show",
                    Appointment.no_show_at.is_not(None),
                    Appointment.no_show_at >= oldest,
                )
            )
        )
    return []


def plan_automation_jobs(
    db: Session,
    *,
    workspace_id: UUID,
    planning_horizon_days: int = 14,
    now: datetime | None = None,
) -> PlanningResult:
    now = (now or datetime.now(timezone.utc)).astimezone(timezone.utc)
    horizon = now + timedelta(days=planning_horizon_days)
    rules = ensure_default_rules(db, workspace_id, commit=False)
    planned = 0
    cancelled = 0

    enabled_rules = [rule for rule in rules if rule.enabled]
    for rule in enabled_rules:
        for appointment in _candidate_appointments(
            db,
            workspace_id=workspace_id,
            rule=rule,
            now=now,
            horizon=horizon,
        ):
            when = scheduled_for(
                trigger_kind=rule.trigger_kind,
                offset_minutes=rule.offset_minutes,
                appointment_created_at=appointment.created_at,
                appointment_start_at=appointment.start_at,
                completed_at=appointment.completed_at,
                no_show_at=appointment.no_show_at,
            )
            if when is None:
                continue
            when = when.astimezone(timezone.utc)

            latest_allowed = when + timedelta(minutes=rule.max_lateness_minutes)
            if latest_allowed < now:
                continue

            dedupe_key = _job_dedupe_key(appointment.id, rule.key)
            existing = db.scalar(
                select(AutomationJob).where(
                    AutomationJob.workspace_id == workspace_id,
                    AutomationJob.dedupe_key == dedupe_key,
                )
            )
            if existing is not None:
                if existing.status in {"queued", "failed"} and existing.scheduled_for != when:
                    existing.scheduled_for = when
                    existing.next_attempt_at = None
                continue

            db.add(
                AutomationJob(
                    workspace_id=workspace_id,
                    rule_id=rule.id,
                    appointment_id=appointment.id,
                    patient_id=appointment.patient_id,
                    status="queued",
                    scheduled_for=when,
                    dedupe_key=dedupe_key,
                    attempts=0,
                    payload_json={
                        "rule_key": rule.key,
                        "appointment_status_at_plan": appointment.status,
                    },
                    result_json={},
                )
            )
            planned += 1

    active_rule_ids = {rule.id for rule in enabled_rules}
    stale_stmt = (
        select(AutomationJob, Appointment)
        .join(
            Appointment,
            and_(
                Appointment.workspace_id == AutomationJob.workspace_id,
                Appointment.id == AutomationJob.appointment_id,
            ),
        )
        .where(
            AutomationJob.workspace_id == workspace_id,
            AutomationJob.status.in_(("queued", "failed")),
        )
    )
    for job, appointment in db.execute(stale_stmt).all():
        rule = db.get(AutomationRule, job.rule_id)
        if rule is None or rule.id not in active_rule_ids or not _eligible_for_rule(appointment, rule):
            job.status = "cancelled"
            job.completed_at = now
            job.result_json = {"reason": "rule_disabled_or_appointment_no_longer_eligible"}
            cancelled += 1

    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        # Another planner may have inserted the same dedupe key concurrently.
        # A retry on the next scheduler tick is safe.
    return PlanningResult(planned=planned, cancelled=cancelled)


def claim_due_jobs(
    db: Session,
    *,
    workspace_id: UUID,
    limit: int,
    now: datetime | None = None,
) -> list[AutomationClaimedJob]:
    now = (now or datetime.now(timezone.utc)).astimezone(timezone.utc)
    stale_before = now - timedelta(minutes=10)

    stmt = (
        select(AutomationJob)
        .where(
            AutomationJob.workspace_id == workspace_id,
            AutomationJob.scheduled_for <= now,
            or_(
                and_(
                    AutomationJob.status.in_(("queued", "failed")),
                    or_(
                        AutomationJob.next_attempt_at.is_(None),
                        AutomationJob.next_attempt_at <= now,
                    ),
                ),
                and_(
                    AutomationJob.status == "processing",
                    AutomationJob.locked_at.is_not(None),
                    AutomationJob.locked_at <= stale_before,
                ),
            ),
        )
        .order_by(AutomationJob.scheduled_for, AutomationJob.created_at)
        .with_for_update(skip_locked=True)
        .limit(limit)
    )
    jobs = list(db.scalars(stmt))
    claimed: list[AutomationClaimedJob] = []

    for job in jobs:
        rule = db.get(AutomationRule, job.rule_id)
        if rule is None or not rule.enabled:
            job.status = "cancelled"
            job.completed_at = now
            job.result_json = {"reason": "rule_disabled"}
            continue
        job.status = "processing"
        job.attempts += 1
        job.locked_at = now
        job.last_error = None
        job.next_attempt_at = None
        claimed.append(
            AutomationClaimedJob(
                job_id=job.id,
                rule_key=rule.key,
                appointment_id=job.appointment_id,
                patient_id=job.patient_id,
                scheduled_for=job.scheduled_for,
                attempt=job.attempts,
            )
        )

    db.commit()
    return claimed


def _resolve_timezone(workspace: Workspace, branch: Branch | None) -> ZoneInfo:
    name = (branch.timezone if branch and branch.timezone else workspace.timezone) or "Africa/Cairo"
    try:
        return ZoneInfo(name)
    except ZoneInfoNotFoundError:
        return ZoneInfo("Africa/Cairo")


def _appointment_display_data(
    db: Session,
    *,
    workspace: Workspace,
    appointment: Appointment,
    patient: Patient,
) -> dict:
    branch = db.get(Branch, appointment.branch_id)
    service = db.get(Service, appointment.service_id)
    doctor = db.get(Doctor, appointment.doctor_id)
    staff = db.get(Staff, doctor.staff_id) if doctor is not None else None

    tz = _resolve_timezone(workspace, branch)
    local_start = appointment.start_at.astimezone(tz)

    doctor_name = "الدكتور المتاح"
    if staff is not None:
        doctor_name = f"{staff.first_name or ''} {staff.last_name or ''}".strip() or doctor_name

    return {
        "patient_name": patient.first_name,
        "service_name": service.name if service else "الخدمة",
        "branch_name": branch.name if branch else "الفرع",
        "doctor_name": doctor_name,
        "date": local_start.strftime("%d/%m/%Y"),
        "time": local_start.strftime("%H:%M"),
        "timezone": tz.key,
    }


def _fallback_text(rule_key: str, data: dict) -> str:
    if rule_key == "booking_confirmation":
        return (
            f"تم تسجيل حجزك في Tia يوم {data['date']} الساعة {data['time']}. "
            "ردي «تأكيد» لتأكيد الموعد أو «تعديل» لو حابة تغيّريه."
        )
    if rule_key == "appointment_reminder_24h":
        return (
            f"تذكير بموعدك في Tia يوم {data['date']} الساعة {data['time']}. "
            "لو حابة تعدّلي الموعد ابعتي «تعديل»."
        )
    if rule_key == "appointment_reminder_2h":
        return (
            f"فاضل تقريبًا ساعتين على موعدك في Tia الساعة {data['time']}. "
            "مستنيينك."
        )
    if rule_key == "post_visit_followup":
        return "نتمنى تكون زيارتك لـTia كانت كويسة. لو عندك سؤال بعد الزيارة ابعتيه هنا."
    if rule_key == "no_show_followup":
        return "لاحظنا إن الموعد فات. لو حابة نحجزلك ميعاد جديد ابعتي «حجز» ونساعدك."
    return "عندك تحديث جديد من Tia."


def _resolve_external_route(
    db: Session,
    *,
    workspace_id: UUID,
    patient_id: UUID,
    channel: str,
    now: datetime,
) -> tuple[Conversation, ChannelConnection] | None:
    channel_filter = [] if channel == "auto" else [ChannelConnection.channel == channel]

    conversation = db.scalar(
        select(Conversation)
        .join(
            ChannelConnection,
            and_(
                ChannelConnection.workspace_id == Conversation.workspace_id,
                ChannelConnection.id == Conversation.channel_connection_id,
            ),
        )
        .where(
            Conversation.workspace_id == workspace_id,
            Conversation.patient_id == patient_id,
            Conversation.channel_connection_id.is_not(None),
            ChannelConnection.status == "active",
            *channel_filter,
        )
        .order_by(
            Conversation.last_message_at.desc().nulls_last(),
            Conversation.started_at.desc(),
        )
        .limit(1)
    )
    if conversation is not None:
        connection = db.get(ChannelConnection, conversation.channel_connection_id)
        if connection is not None:
            return conversation, connection

    identity = db.scalar(
        select(ChannelIdentity)
        .join(
            ChannelConnection,
            and_(
                ChannelConnection.workspace_id == ChannelIdentity.workspace_id,
                ChannelConnection.id == ChannelIdentity.channel_connection_id,
            ),
        )
        .where(
            ChannelIdentity.workspace_id == workspace_id,
            ChannelIdentity.patient_id == patient_id,
            ChannelConnection.status == "active",
            *channel_filter,
        )
        .order_by(ChannelIdentity.updated_at.desc())
        .limit(1)
    )
    if identity is None:
        return None

    connection = db.get(ChannelConnection, identity.channel_connection_id)
    if connection is None:
        return None

    conversation = Conversation(
        workspace_id=workspace_id,
        patient_id=patient_id,
        channel=connection.channel,
        status="open",
        external_conversation_id=identity.external_user_id,
        channel_connection_id=connection.id,
        started_at=now,
        last_message_at=None,
    )
    db.add(conversation)
    db.flush()
    return conversation, connection


def execute_job(
    db: Session,
    *,
    workspace_id: UUID,
    job_id: UUID,
    now: datetime | None = None,
) -> ExecutionResult:
    now = (now or datetime.now(timezone.utc)).astimezone(timezone.utc)
    job = db.scalar(
        select(AutomationJob)
        .where(
            AutomationJob.workspace_id == workspace_id,
            AutomationJob.id == job_id,
        )
        .with_for_update()
    )
    if job is None:
        raise AutomationError("Automation job not found.")
    if job.status in {"dispatched", "skipped", "cancelled"}:
        return ExecutionResult(job=job, reason=job.result_json.get("reason"))
    if job.status != "processing":
        raise AutomationError(f"Automation job is '{job.status}', not processing.")

    rule = db.get(AutomationRule, job.rule_id)
    appointment = db.get(Appointment, job.appointment_id)
    patient = db.get(Patient, job.patient_id)
    workspace = db.get(Workspace, workspace_id)

    if rule is None or appointment is None or patient is None or workspace is None:
        job.status = "skipped"
        job.completed_at = now
        job.locked_at = None
        job.result_json = {"reason": "automation_target_missing"}
        db.commit()
        return ExecutionResult(job=job, reason="automation_target_missing")

    if not rule.enabled or not _eligible_for_rule(appointment, rule):
        job.status = "cancelled"
        job.completed_at = now
        job.locked_at = None
        job.result_json = {"reason": "rule_disabled_or_appointment_no_longer_eligible"}
        db.commit()
        return ExecutionResult(job=job, reason=job.result_json["reason"])

    if patient.status != "active":
        job.status = "skipped"
        job.completed_at = now
        job.locked_at = None
        job.result_json = {"reason": "patient_not_active"}
        db.commit()
        return ExecutionResult(job=job, reason="patient_not_active")

    route = _resolve_external_route(
        db,
        workspace_id=workspace_id,
        patient_id=patient.id,
        channel=rule.channel,
        now=now,
    )
    if route is None:
        job.status = "skipped"
        job.completed_at = now
        job.locked_at = None
        job.result_json = {"reason": "no_active_external_channel_identity"}
        db.commit()
        return ExecutionResult(job=job, reason=job.result_json["reason"])

    conversation, connection = route
    display = _appointment_display_data(
        db,
        workspace=workspace,
        appointment=appointment,
        patient=patient,
    )
    fallback = _fallback_text(rule.key, display)

    metadata = {
        "source": "automation_engine",
        "automation_job_id": str(job.id),
        "automation_rule_key": rule.key,
        "appointment_id": str(appointment.id),
        "whatsapp_template": {
            "name": rule.template_name,
            "language_code": rule.template_language,
        },
        "appointment": display,
    }

    message_type = "template" if connection.channel == "whatsapp" else "text"
    message = Message(
        workspace_id=workspace_id,
        conversation_id=conversation.id,
        channel_connection_id=connection.id,
        sender_type="system",
        direction="outbound",
        message_type=message_type,
        content=fallback,
        delivery_status="queued",
        metadata_json=metadata,
    )
    db.add(message)
    db.flush()

    dispatch = MessageDispatch(
        workspace_id=workspace_id,
        channel_connection_id=connection.id,
        message_id=message.id,
        status="queued",
        attempts=0,
        metadata_json={
            "conversation_id": str(conversation.id),
            "sender_type": "system",
            "source": "automation_engine",
            "automation_job_id": str(job.id),
        },
    )
    db.add(dispatch)
    db.flush()

    conversation.last_message_at = now
    job.status = "dispatched"
    job.message_id = message.id
    job.dispatch_id = dispatch.id
    job.completed_at = now
    job.locked_at = None
    job.result_json = {
        "message_id": str(message.id),
        "dispatch_id": str(dispatch.id),
        "channel": connection.channel,
        "channel_connection_id": str(connection.id),
        "message_type": message_type,
    }
    db.commit()
    db.refresh(job)
    return ExecutionResult(job=job, reason=None)


def mark_job_failed(
    db: Session,
    *,
    workspace_id: UUID,
    job_id: UUID,
    error: str,
    retry_after_seconds: int = 60,
) -> AutomationJob:
    job = db.scalar(
        select(AutomationJob)
        .where(
            AutomationJob.workspace_id == workspace_id,
            AutomationJob.id == job_id,
        )
        .with_for_update()
    )
    if job is None:
        raise AutomationError("Automation job not found.")
    now = datetime.now(timezone.utc)
    job.status = "failed"
    job.locked_at = None
    job.last_error = error[:4000]
    job.next_attempt_at = now + timedelta(seconds=max(1, retry_after_seconds))
    db.commit()
    db.refresh(job)
    return job
