from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import UTC, datetime, timedelta
from typing import Any
from uuid import UUID

from sqlalchemy import case, distinct, func, select, text
from sqlalchemy.orm import Session

from app.models.appointment import Appointment
from app.models.crm_campaign import CRMCampaign, CRMCampaignRecipient
from app.models.crm_campaign_conversion import CRMCampaignConversion
from app.models.message_dispatch import MessageDispatch
from app.models.payment_transaction import PaymentAllocation, PaymentTransaction
from app.schemas.analytics_catalog import AnalyticsCatalogRunRequest
from app.services.analytics_catalog import _DEFINITIONS, run_catalog_analysis
from app.services.campaign_analytics import campaign_analytics_overview


@dataclass(frozen=True)
class AnalyticsIntegrityCheck:
    key: str
    passed: bool
    expected: Any
    actual: Any
    detail: str


@dataclass(frozen=True)
class AnalyticsPlanAudit:
    key: str
    execution_ms: float | None
    planning_ms: float | None
    root_node: str | None
    plan_rows: int | None


@dataclass(frozen=True)
class AnalyticsIntegrityReport:
    workspace_id: str
    generated_at: str
    catalog_analysis_count: int
    catalog_failures: tuple[str, ...]
    checks: tuple[AnalyticsIntegrityCheck, ...]
    plan_audits: tuple[AnalyticsPlanAudit, ...]

    @property
    def passed(self) -> bool:
        return not self.catalog_failures and all(check.passed for check in self.checks)

    def as_dict(self) -> dict[str, Any]:
        payload = asdict(self)
        payload["passed"] = self.passed
        return payload


def _aware(value: datetime | None) -> datetime:
    current = value or datetime.now(UTC)
    if current.tzinfo is None:
        return current.replace(tzinfo=UTC)
    return current.astimezone(UTC)


def _metrics(result) -> dict[str, int | float | str | None]:
    if not result.rows:
        return {}
    return {metric.key: metric.value for metric in result.rows[0].metrics}


def _check(key: str, expected: Any, actual: Any, detail: str) -> AnalyticsIntegrityCheck:
    return AnalyticsIntegrityCheck(
        key=key,
        passed=expected == actual,
        expected=expected,
        actual=actual,
        detail=detail,
    )


def _smoke_catalog(
    db: Session,
    *,
    workspace_id: UUID,
    now: datetime,
) -> tuple[str, ...]:
    failures: list[str] = []
    for definition in _DEFINITIONS:
        try:
            result = run_catalog_analysis(
                db,
                workspace_id=workspace_id,
                request=AnalyticsCatalogRunRequest(analysis_key=definition.key),
                now=now,
                use_cache=False,
            )
            if result.analysis_key != definition.key:
                failures.append(f"{definition.key}: returned {result.analysis_key}")
        except Exception as exc:  # pragma: no cover - exercised by live validation script.
            db.rollback()
            failures.append(f"{definition.key}: {type(exc).__name__}: {exc}")
    return tuple(failures)


def _appointment_reconciliation(
    db: Session,
    *,
    workspace_id: UUID,
    now: datetime,
    days: int,
) -> list[AnalyticsIntegrityCheck]:
    start = now - timedelta(days=days)
    row = db.execute(
        select(
            func.count(Appointment.id).label("appointments"),
            func.coalesce(func.sum(case((Appointment.status == "completed", 1), else_=0)), 0).label("completed"),
            func.coalesce(func.sum(case((Appointment.status == "no_show", 1), else_=0)), 0).label("no_show"),
            func.coalesce(func.sum(case((Appointment.status == "cancelled", 1), else_=0)), 0).label("cancelled"),
        ).where(
            Appointment.workspace_id == workspace_id,
            Appointment.status != "rescheduled",
            Appointment.start_at >= start,
            Appointment.start_at < now,
        )
    ).one()
    direct = {
        "appointments": int(row.appointments or 0),
        "completed_appointments": int(row.completed or 0),
        "no_show_appointments": int(row.no_show or 0),
        "cancelled_appointments": int(row.cancelled or 0),
    }
    result = run_catalog_analysis(
        db,
        workspace_id=workspace_id,
        request=AnalyticsCatalogRunRequest(analysis_key="appointment_overview", lookback_days=days),
        now=now,
        use_cache=False,
    )
    metrics = _metrics(result)
    return [
        _check(
            f"appointments.{metric}",
            expected,
            metrics.get(metric),
            "Independent canonical appointment aggregate must match the public catalog result.",
        )
        for metric, expected in direct.items()
    ]


def _revenue_reconciliation(
    db: Session,
    *,
    workspace_id: UUID,
    now: datetime,
    days: int,
) -> list[AnalyticsIntegrityCheck]:
    start = now - timedelta(days=days)
    row = db.execute(
        select(
            func.coalesce(
                func.sum(case((PaymentTransaction.transaction_type == "payment", PaymentTransaction.amount_minor), else_=0)),
                0,
            ).label("gross"),
            func.coalesce(
                func.sum(case((PaymentTransaction.transaction_type == "refund", PaymentTransaction.amount_minor), else_=0)),
                0,
            ).label("refunds"),
            func.coalesce(
                func.sum(
                    case(
                        (PaymentTransaction.transaction_type == "payment", PaymentTransaction.amount_minor),
                        else_=-PaymentTransaction.amount_minor,
                    )
                ),
                0,
            ).label("net"),
        ).where(
            PaymentTransaction.workspace_id == workspace_id,
            PaymentTransaction.currency == "EGP",
            PaymentTransaction.created_at >= start,
            PaymentTransaction.created_at < now,
        )
    ).one()
    direct = {
        "gross_paid_minor": int(row.gross or 0),
        "refunded_minor": int(row.refunds or 0),
        "net_paid_minor": int(row.net or 0),
    }
    result = run_catalog_analysis(
        db,
        workspace_id=workspace_id,
        request=AnalyticsCatalogRunRequest(analysis_key="revenue_overview", lookback_days=days),
        now=now,
        use_cache=False,
    )
    metrics = _metrics(result)
    checks = [
        _check(
            f"revenue.{metric}",
            expected,
            metrics.get(metric),
            "Independent payment-ledger aggregate must match the public catalog result.",
        )
        for metric, expected in direct.items()
    ]

    # Entity-attributed revenue is intentionally allocation-only. Compare the
    # top service rows independently so an accidental list-price/unallocated
    # shortcut cannot pass the clinic-wide ledger check above.
    signed = case(
        (PaymentTransaction.transaction_type == "payment", PaymentAllocation.amount_minor),
        else_=-PaymentAllocation.amount_minor,
    )
    direct_rows = db.execute(
        select(Appointment.service_id, func.coalesce(func.sum(signed), 0).label("net"))
        .join(
            PaymentAllocation,
            (PaymentAllocation.workspace_id == Appointment.workspace_id)
            & (PaymentAllocation.appointment_id == Appointment.id),
        )
        .join(
            PaymentTransaction,
            (PaymentTransaction.workspace_id == PaymentAllocation.workspace_id)
            & (PaymentTransaction.id == PaymentAllocation.transaction_id),
        )
        .where(
            Appointment.workspace_id == workspace_id,
            PaymentTransaction.workspace_id == workspace_id,
            PaymentTransaction.currency == "EGP",
            PaymentTransaction.created_at >= start,
            PaymentTransaction.created_at < now,
        )
        .group_by(Appointment.service_id)
        .order_by(func.coalesce(func.sum(signed), 0).desc())
        .limit(25)
    ).all()
    expected_by_service = {str(row.service_id): int(row.net or 0) for row in direct_rows}
    grouped = run_catalog_analysis(
        db,
        workspace_id=workspace_id,
        request=AnalyticsCatalogRunRequest(analysis_key="revenue_by_service", lookback_days=days, limit=25),
        now=now,
        use_cache=False,
    )
    actual_by_service = {
        str(row.key).removeprefix("service:"): int(next((metric.value for metric in row.metrics if metric.key == "net_paid_minor"), 0) or 0)
        for row in grouped.rows
    }
    checks.append(
        _check(
            "revenue.by_service_allocation_only",
            expected_by_service,
            actual_by_service,
            "Service revenue must come only from explicit payment allocations joined to appointments.",
        )
    )
    return checks


def _retention_reconciliation(
    db: Session,
    *,
    workspace_id: UUID,
    now: datetime,
    days: int,
) -> list[AnalyticsIntegrityCheck]:
    start = now - timedelta(days=days)
    per_patient = (
        select(Appointment.patient_id.label("patient_id"), func.count(Appointment.id).label("visits"))
        .where(
            Appointment.workspace_id == workspace_id,
            Appointment.status == "completed",
            Appointment.start_at >= start,
            Appointment.start_at < now,
        )
        .group_by(Appointment.patient_id)
        .subquery()
    )
    row = db.execute(
        select(
            func.count().label("patients"),
            func.coalesce(func.sum(case((per_patient.c.visits >= 2, 1), else_=0)), 0).label("second"),
            func.coalesce(func.sum(case((per_patient.c.visits >= 3, 1), else_=0)), 0).label("third"),
        ).select_from(per_patient)
    ).one()
    expected_patients = int(row.patients or 0)
    expected_second = int(row.second or 0)
    expected_third = int(row.third or 0)

    second = _metrics(
        run_catalog_analysis(
            db,
            workspace_id=workspace_id,
            request=AnalyticsCatalogRunRequest(analysis_key="second_visit_conversion", lookback_days=days),
            now=now,
            use_cache=False,
        )
    )
    third = _metrics(
        run_catalog_analysis(
            db,
            workspace_id=workspace_id,
            request=AnalyticsCatalogRunRequest(analysis_key="third_visit_conversion", lookback_days=days),
            now=now,
            use_cache=False,
        )
    )
    return [
        _check(
            "retention.denominator",
            expected_patients,
            second.get("patients_with_completed_visit", 0),
            "Second-visit denominator must equal canonical patients with at least one completed visit.",
        ),
        _check(
            "retention.second_visit",
            expected_second,
            second.get("patients_with_second_visit", 0),
            "Second-visit conversion must be based on canonical completed-visit counts per patient.",
        ),
        _check(
            "retention.third_visit",
            expected_third,
            third.get("patients_with_third_visit", 0),
            "Third-visit conversion must be based on canonical completed-visit counts per patient.",
        ),
    ]


def _campaign_reconciliation(
    db: Session,
    *,
    workspace_id: UUID,
    now: datetime,
    days: int,
) -> list[AnalyticsIntegrityCheck]:
    since = now - timedelta(days=days)
    campaign_ids = list(
        db.scalars(
            select(CRMCampaign.id).where(
                CRMCampaign.workspace_id == workspace_id,
                CRMCampaign.status.in_(("confirmed", "cancelled")),
                CRMCampaign.confirmed_at.is_not(None),
                CRMCampaign.confirmed_at >= since,
            )
        )
    )
    result = campaign_analytics_overview(
        db,
        workspace_id=workspace_id,
        days=days,
        now=now,
        limit=max(100, len(campaign_ids)),
    )
    if not campaign_ids:
        return [
            _check(
                "campaign.empty_scope",
                0,
                result.totals.sent_count,
                "A workspace with no confirmed campaigns in scope must report zero campaign sends.",
            )
        ]

    dispatch = db.execute(
        select(
            func.coalesce(func.sum(case((MessageDispatch.sent_at.is_not(None), 1), else_=0)), 0).label("sent"),
            func.coalesce(func.sum(case((MessageDispatch.delivered_at.is_not(None), 1), else_=0)), 0).label("delivered"),
            func.coalesce(func.sum(case((MessageDispatch.read_at.is_not(None), 1), else_=0)), 0).label("read"),
            func.coalesce(func.sum(case((MessageDispatch.status == "failed", 1), else_=0)), 0).label("failed"),
        )
        .select_from(CRMCampaignRecipient)
        .outerjoin(
            MessageDispatch,
            (MessageDispatch.workspace_id == CRMCampaignRecipient.workspace_id)
            & (MessageDispatch.id == CRMCampaignRecipient.dispatch_id),
        )
        .where(
            CRMCampaignRecipient.workspace_id == workspace_id,
            CRMCampaignRecipient.campaign_id.in_(campaign_ids),
        )
    ).one()

    signed = case(
        (PaymentTransaction.transaction_type == "payment", PaymentAllocation.amount_minor),
        (PaymentTransaction.transaction_type == "refund", -PaymentAllocation.amount_minor),
        else_=0,
    )
    conversions = db.execute(
        select(
            func.count(distinct(CRMCampaignConversion.id)).label("bookings"),
            func.count(
                distinct(case((Appointment.status == "completed", CRMCampaignConversion.id), else_=None))
            ).label("completed"),
            func.coalesce(func.sum(signed), 0).label("revenue"),
        )
        .select_from(CRMCampaignConversion)
        .join(
            Appointment,
            (Appointment.workspace_id == CRMCampaignConversion.workspace_id)
            & (Appointment.id == CRMCampaignConversion.appointment_id),
        )
        .outerjoin(
            PaymentAllocation,
            (PaymentAllocation.workspace_id == CRMCampaignConversion.workspace_id)
            & (PaymentAllocation.appointment_id == CRMCampaignConversion.appointment_id),
        )
        .outerjoin(
            PaymentTransaction,
            (PaymentTransaction.workspace_id == PaymentAllocation.workspace_id)
            & (PaymentTransaction.id == PaymentAllocation.transaction_id)
            & (PaymentTransaction.currency == "EGP"),
        )
        .where(
            CRMCampaignConversion.workspace_id == workspace_id,
            CRMCampaignConversion.campaign_id.in_(campaign_ids),
        )
    ).one()

    expected = {
        "sent_count": int(dispatch.sent or 0),
        "delivered_count": int(dispatch.delivered or 0),
        "read_count": int(dispatch.read or 0),
        "failed_count": int(dispatch.failed or 0),
        "tracked_booking_count": int(conversions.bookings or 0),
        "completed_booking_count": int(conversions.completed or 0),
        "attributed_revenue_minor": int(conversions.revenue or 0),
    }
    actual = result.totals.model_dump()
    return [
        _check(
            f"campaign.{metric}",
            value,
            actual.get(metric),
            "Campaign analytics must reconcile to provider dispatch facts and explicit campaign conversions.",
        )
        for metric, value in expected.items()
    ]


def _explain_json(db: Session, statement: str, params: dict[str, Any]) -> AnalyticsPlanAudit:
    result = db.execute(text(f"EXPLAIN (ANALYZE, BUFFERS, FORMAT JSON) {statement}"), params).scalar_one()
    payload = result[0] if isinstance(result, list) else result
    if isinstance(payload, list):
        payload = payload[0]
    plan = payload.get("Plan", {}) if isinstance(payload, dict) else {}
    return AnalyticsPlanAudit(
        key=str(params.get("audit_key") or "query"),
        execution_ms=float(payload.get("Execution Time")) if isinstance(payload, dict) and payload.get("Execution Time") is not None else None,
        planning_ms=float(payload.get("Planning Time")) if isinstance(payload, dict) and payload.get("Planning Time") is not None else None,
        root_node=str(plan.get("Node Type")) if plan.get("Node Type") else None,
        plan_rows=int(plan.get("Plan Rows")) if plan.get("Plan Rows") is not None else None,
    )


def postgres_plan_audits(
    db: Session,
    *,
    workspace_id: UUID,
    now: datetime,
    days: int = 365,
) -> tuple[AnalyticsPlanAudit, ...]:
    """Run representative read-only EXPLAIN ANALYZE checks on PostgreSQL.

    These queries mirror the heaviest access patterns rather than relying on
    planner implementation details. The validation command records execution
    time and root plan shape so staging/production-like datasets can be audited
    before releases.
    """
    if db.get_bind().dialect.name != "postgresql":
        raise RuntimeError("EXPLAIN ANALYZE validation requires PostgreSQL.")
    start = now - timedelta(days=days)
    common = {"workspace_id": workspace_id, "start_at": start, "end_at": now}
    audits: list[AnalyticsPlanAudit] = []
    queries = (
        (
            "appointments",
            "SELECT patient_id, count(*) FROM appointments "
            "WHERE workspace_id=:workspace_id AND status='completed' AND start_at>=:start_at AND start_at<:end_at "
            "GROUP BY patient_id",
        ),
        (
            "payment_ledger",
            "SELECT transaction_type, sum(amount_minor) FROM payment_transactions "
            "WHERE workspace_id=:workspace_id AND currency='EGP' AND created_at>=:start_at AND created_at<:end_at "
            "GROUP BY transaction_type",
        ),
        (
            "allocated_revenue",
            "SELECT a.service_id, sum(CASE WHEN t.transaction_type='payment' THEN pa.amount_minor ELSE -pa.amount_minor END) "
            "FROM payment_transactions t JOIN payment_allocations pa "
            "ON pa.workspace_id=t.workspace_id AND pa.transaction_id=t.id "
            "JOIN appointments a ON a.workspace_id=pa.workspace_id AND a.id=pa.appointment_id "
            "WHERE t.workspace_id=:workspace_id AND t.currency='EGP' AND t.created_at>=:start_at AND t.created_at<:end_at "
            "GROUP BY a.service_id",
        ),
        (
            "campaign_attribution",
            "SELECT c.campaign_id, count(DISTINCT c.id), sum(CASE WHEN t.transaction_type='payment' THEN pa.amount_minor WHEN t.transaction_type='refund' THEN -pa.amount_minor ELSE 0 END) "
            "FROM crm_campaign_conversions c JOIN appointments a "
            "ON a.workspace_id=c.workspace_id AND a.id=c.appointment_id "
            "LEFT JOIN payment_allocations pa ON pa.workspace_id=c.workspace_id AND pa.appointment_id=c.appointment_id "
            "LEFT JOIN payment_transactions t ON t.workspace_id=pa.workspace_id AND t.id=pa.transaction_id AND t.currency='EGP' "
            "WHERE c.workspace_id=:workspace_id GROUP BY c.campaign_id",
        ),
    )
    for key, query in queries:
        params = dict(common)
        params["audit_key"] = key
        audits.append(_explain_json(db, query, params))
    return tuple(audits)


def run_analytics_integrity_gate(
    db: Session,
    *,
    workspace_id: UUID,
    now: datetime | None = None,
    include_postgres_explain: bool = False,
) -> AnalyticsIntegrityReport:
    current = _aware(now)
    catalog_failures = _smoke_catalog(db, workspace_id=workspace_id, now=current)
    checks: list[AnalyticsIntegrityCheck] = []
    checks.extend(_appointment_reconciliation(db, workspace_id=workspace_id, now=current, days=90))
    checks.extend(_revenue_reconciliation(db, workspace_id=workspace_id, now=current, days=90))
    checks.extend(_retention_reconciliation(db, workspace_id=workspace_id, now=current, days=365))
    checks.extend(_campaign_reconciliation(db, workspace_id=workspace_id, now=current, days=90))
    plans = (
        postgres_plan_audits(db, workspace_id=workspace_id, now=current)
        if include_postgres_explain
        else ()
    )
    return AnalyticsIntegrityReport(
        workspace_id=str(workspace_id),
        generated_at=current.isoformat(),
        catalog_analysis_count=len(_DEFINITIONS),
        catalog_failures=catalog_failures,
        checks=tuple(checks),
        plan_audits=plans,
    )
