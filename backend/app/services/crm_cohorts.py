from __future__ import annotations

from datetime import UTC, datetime
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.models.crm_cohort import CRMCohort, CRMCohortMember
from app.models.crm_task import CRMTask
from app.models.patient import Patient
from app.schemas.analytics_bi import AnalyticsBIPlan
from app.schemas.analytics_composable import AnalyticsAudiencePlan
from app.schemas.crm_cohort import CohortFollowUpResult
from app.services.activity import record_activity_event
from app.services.analytics_audience import execute_audience_plan, validate_audience_plan_entities
from app.services.analytics_bi import (
    AnalyticsBIError,
    analytics_entity_catalog,
    execute_analytics_plan,
    validate_analytics_plan_entities,
)
from app.services.crm_tasks import CRMTaskError, create_crm_task, validate_assignee

COHORTABLE_ANALYTICS_OPERATIONS = frozenset(
    {"top_repeat_patients", "top_value_patients", "lapsed_patients"}
)
MAX_COHORT_MEMBERS = 25


class CRMCohortError(ValueError):
    pass


def _snapshot_metrics(row) -> list[dict]:
    result: list[dict] = []
    for metric in row.metrics[:12]:
        value = metric.value
        if not isinstance(value, (str, int, float)):
            value = str(value)[:200]
        result.append(
            {
                "key": metric.key[:80],
                "label": metric.label[:120],
                "value": value,
                "currency": metric.currency,
            }
        )
    return result


def create_analytics_cohort(
    db: Session,
    *,
    workspace_id: UUID,
    created_by_user_id: UUID,
    request_id: UUID,
    name: str,
    question: str,
    plan: AnalyticsBIPlan | AnalyticsAudiencePlan,
    now: datetime | None = None,
) -> CRMCohort:
    name = name.strip()
    question = " ".join(question.split())
    if not name:
        raise CRMCohortError("Cohort name cannot be empty.")
    if len(name) > 160:
        raise CRMCohortError("Cohort name is too long.")
    if not question:
        raise CRMCohortError("Analytics question cannot be empty.")
    if len(question) > 1200:
        raise CRMCohortError("Analytics question is too long.")
    existing_request = db.scalar(
        select(CRMCohort).where(
            CRMCohort.workspace_id == workspace_id,
            CRMCohort.request_key == str(request_id),
        )
    )
    if existing_request is not None:
        return existing_request

    try:
        catalog = analytics_entity_catalog(db, workspace_id=workspace_id)
        if isinstance(plan, AnalyticsAudiencePlan):
            validated_plan = validate_audience_plan_entities(plan, catalog=catalog)
            answer = execute_audience_plan(
                db,
                workspace_id=workspace_id,
                plan=validated_plan,
                now=now,
            )
            analytics_operation = "patient_audience"
        else:
            if plan.operation not in COHORTABLE_ANALYTICS_OPERATIONS:
                raise CRMCohortError(
                    "Only patient-list analytics can be materialized as a CRM cohort."
                )
            validated_plan = validate_analytics_plan_entities(plan, catalog=catalog)
            answer = execute_analytics_plan(
                db,
                workspace_id=workspace_id,
                question=question,
                plan=validated_plan,
                model=None,
                now=now,
            )
            analytics_operation = validated_plan.operation
    except AnalyticsBIError as exc:
        raise CRMCohortError(str(exc)) from exc

    if not answer.rows:
        raise CRMCohortError("Analytics result has no patients to materialize.")
    if len(answer.rows) > MAX_COHORT_MEMBERS:
        raise CRMCohortError("Analytics cohort exceeds the maximum snapshot size.")

    patient_ids: list[UUID] = []
    rows_by_patient: dict[UUID, object] = {}
    for row in answer.rows:
        if row.key is None:
            raise CRMCohortError("Analytics result is not a patient cohort.")
        try:
            patient_id = UUID(str(row.key))
        except ValueError as exc:
            raise CRMCohortError("Analytics result contains an invalid patient id.") from exc
        if patient_id in rows_by_patient:
            raise CRMCohortError("Analytics result contains duplicate patients.")
        patient_ids.append(patient_id)
        rows_by_patient[patient_id] = row

    if patient_ids:
        existing = set(
            db.scalars(
                select(Patient.id).where(
                    Patient.workspace_id == workspace_id,
                    Patient.id.in_(patient_ids),
                )
            ).all()
        )
        if existing != set(patient_ids):
            raise CRMCohortError("Analytics result referenced a patient outside this workspace.")

    cohort = CRMCohort(
        workspace_id=workspace_id,
        created_by_user_id=created_by_user_id,
        name=name,
        request_key=str(request_id),
        source="analytics_bi",
        status="active",
        analytics_operation=analytics_operation,
        question=question,
        plan_json=validated_plan.model_dump(mode="json"),
        period_label=answer.period_label,
        member_count=len(patient_ids),
    )
    savepoint = db.begin_nested()
    db.add(cohort)
    try:
        db.flush([cohort])
        savepoint.commit()
    except IntegrityError as exc:
        savepoint.rollback()
        existing_request = db.scalar(
            select(CRMCohort).where(
                CRMCohort.workspace_id == workspace_id,
                CRMCohort.request_key == str(request_id),
            )
        )
        if existing_request is not None:
            return existing_request
        raise CRMCohortError("CRM cohort could not be created because of a concurrent conflict.") from exc

    for rank, patient_id in enumerate(patient_ids, start=1):
        db.add(
            CRMCohortMember(
                workspace_id=workspace_id,
                cohort_id=cohort.id,
                patient_id=patient_id,
                rank=rank,
                snapshot_metrics_json=_snapshot_metrics(rows_by_patient[patient_id]),
            )
        )
    db.flush()
    record_activity_event(
        db,
        workspace_id=workspace_id,
        actor_type="staff",
        actor_user_id=created_by_user_id,
        action="crm_cohort.created",
        entity_type="crm_cohort",
        entity_id=cohort.id,
        summary="Analytics CRM cohort created",
        metadata={
            "operation": cohort.analytics_operation,
            "member_count": cohort.member_count,
            "period_label": cohort.period_label,
        },
    )
    db.commit()
    db.refresh(cohort)
    return cohort


def create_cohort_follow_up_tasks(
    db: Session,
    *,
    workspace_id: UUID,
    cohort_id: UUID,
    request_id: UUID,
    actor_user_id: UUID,
    assigned_user_id: UUID | None,
    title: str,
    description: str | None,
    priority: str,
    due_at: datetime,
) -> CohortFollowUpResult:
    cohort = db.scalar(
        select(CRMCohort)
        .where(
            CRMCohort.workspace_id == workspace_id,
            CRMCohort.id == cohort_id,
        )
        .with_for_update()
    )
    if cohort is None:
        raise CRMCohortError("CRM cohort not found in this workspace.")
    if cohort.status != "active":
        raise CRMCohortError("Only active CRM cohorts can create follow-up tasks.")
    if due_at.tzinfo is None or due_at.utcoffset() is None:
        raise CRMCohortError("Follow-up due_at must include a timezone offset.")
    try:
        validate_assignee(db, workspace_id=workspace_id, user_id=assigned_user_id)
    except CRMTaskError as exc:
        raise CRMCohortError(str(exc)) from exc

    members = list(
        db.scalars(
            select(CRMCohortMember)
            .where(
                CRMCohortMember.workspace_id == workspace_id,
                CRMCohortMember.cohort_id == cohort_id,
            )
            .order_by(CRMCohortMember.rank, CRMCohortMember.id)
        ).all()
    )
    if len(members) != cohort.member_count:
        raise CRMCohortError("CRM cohort membership snapshot is inconsistent.")

    created = 0
    reused = 0
    task_ids: list[UUID] = []
    for member in members:
        dedupe_key = f"cohort:{cohort.id}:followup:{request_id}:patient:{member.patient_id}"
        existing = db.scalar(
            select(CRMTask).where(
                CRMTask.workspace_id == workspace_id,
                CRMTask.dedupe_key == dedupe_key,
            )
        )
        if existing is not None:
            task = existing
            reused += 1
        else:
            task = create_crm_task(
                db,
                workspace_id=workspace_id,
                patient_id=member.patient_id,
                assigned_user_id=assigned_user_id,
                created_by_user_id=actor_user_id,
                task_type="follow_up",
                execution_mode="human",
                priority=priority,
                title=title,
                description=description,
                due_at=due_at.astimezone(UTC),
                source="ai",
                dedupe_key=dedupe_key,
                commit=False,
            )
            created += 1
        task_ids.append(task.id)

    if created > 0:
        record_activity_event(
            db,
            workspace_id=workspace_id,
            actor_type="staff",
            actor_user_id=actor_user_id,
            action="crm_cohort.follow_up_tasks_created",
            entity_type="crm_cohort",
            entity_id=cohort.id,
            summary="CRM cohort follow-up tasks confirmed",
            metadata={
                "member_count": cohort.member_count,
                "created_tasks": created,
                "reused_tasks": reused,
                "assigned_user_id": assigned_user_id,
                "priority": priority,
                "due_at": due_at,
                "request_id": request_id,
            },
        )
    db.commit()
    return CohortFollowUpResult(
        cohort_id=cohort.id,
        request_id=request_id,
        member_count=cohort.member_count,
        created_tasks=created,
        reused_tasks=reused,
        task_ids=task_ids,
    )


def execute_confirmed_audience_action(
    db: Session,
    *,
    workspace_id: UUID,
    actor_user_id: UUID,
    audience_request_id: UUID,
    action_request_id: UUID,
    name: str,
    question: str,
    plan: AnalyticsAudiencePlan,
    action_kind: str,
    assigned_user_id: UUID | None = None,
    priority: str = "normal",
    title: str | None = None,
    description: str | None = None,
    due_at: datetime | None = None,
    now: datetime | None = None,
) -> tuple[CRMCohort, CohortFollowUpResult | None, str]:
    """Backend-owned audience materialization plus one explicitly confirmed action.

    The caller never supplies member IDs. The typed audience plan is re-executed
    and snapshotted first, then the existing idempotent CRM task pipeline is
    reused for follow-up actions. WhatsApp remains a separate preview/confirm
    flow because channel/template details must be reviewed before sending.
    """
    cohort = create_analytics_cohort(
        db,
        workspace_id=workspace_id,
        created_by_user_id=actor_user_id,
        request_id=audience_request_id,
        name=name,
        question=question,
        plan=plan,
        now=now,
    )
    if action_kind == "save_audience":
        return cohort, None, "saved"
    if action_kind == "whatsapp_campaign":
        return cohort, None, "campaign_setup"
    if action_kind != "follow_up_tasks":
        raise CRMCohortError("Unsupported audience action.")
    if due_at is None:
        raise CRMCohortError("Follow-up action requires a due date.")
    follow_up = create_cohort_follow_up_tasks(
        db,
        workspace_id=workspace_id,
        cohort_id=cohort.id,
        request_id=action_request_id,
        actor_user_id=actor_user_id,
        assigned_user_id=assigned_user_id,
        title=(title or f"متابعة {cohort.name}"),
        description=description,
        priority=priority,
        due_at=due_at,
    )
    return cohort, follow_up, "tasks_created"
