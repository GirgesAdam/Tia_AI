from __future__ import annotations

from calendar import monthrange
from datetime import UTC, date, datetime
from uuid import UUID
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.expense import Expense
from app.models.payment_transaction import PaymentTransaction
from app.schemas.finance import FinanceTrendPoint, FinanceTrendRead
from app.services.finance import FinanceOperationError, _utc_bounds


def _financial_period_buckets(
    *, start_date: date, end_date: date, mode: str
) -> list[tuple[str, date, date]]:
    if start_date > end_date:
        raise FinanceOperationError("start_date must be on or before end_date.")
    if mode == "month":
        if start_date.year != end_date.year or start_date.month != end_date.month:
            raise FinanceOperationError("Monthly dashboard trend requires one calendar month.")
        month_end = monthrange(start_date.year, start_date.month)[1]
        if start_date.day != 1 or end_date.day != month_end:
            raise FinanceOperationError("Monthly dashboard trend must cover the full calendar month.")
        ranges = ((1, 7), (8, 14), (15, 21), (22, month_end))
        return [
            (
                f"الأسبوع {index}",
                date(start_date.year, start_date.month, first_day),
                date(start_date.year, start_date.month, last_day),
            )
            for index, (first_day, last_day) in enumerate(ranges, start=1)
        ]
    if mode == "year":
        if (
            start_date.year != end_date.year
            or start_date.month != 1
            or start_date.day != 1
            or end_date.month != 12
            or end_date.day != 31
        ):
            raise FinanceOperationError("Annual dashboard trend must cover one full calendar year.")
        return [
            (
                f"{start_date.year}-{month:02d}",
                date(start_date.year, month, 1),
                date(start_date.year, month, monthrange(start_date.year, month)[1]),
            )
            for month in range(1, 13)
        ]
    raise FinanceOperationError("mode must be month or year.")


def _workspace_date(value: datetime, timezone: ZoneInfo) -> date:
    if value.tzinfo is None:
        value = value.replace(tzinfo=UTC)
    return value.astimezone(timezone).date()


def financial_dashboard_trend(
    db: Session,
    *,
    workspace_id: UUID,
    timezone_name: str,
    start_date: date,
    end_date: date,
    mode: str,
    currency: str = "EGP",
) -> FinanceTrendRead:
    buckets = _financial_period_buckets(start_date=start_date, end_date=end_date, mode=mode)
    try:
        timezone = ZoneInfo(timezone_name)
    except ZoneInfoNotFoundError:
        timezone = ZoneInfo("Africa/Cairo")
    start_at, end_at = _utc_bounds(
        start_date=start_date,
        end_date=end_date,
        timezone_name=timezone.key,
    )
    currency = currency.upper()

    payment_rows = db.execute(
        select(
            PaymentTransaction.created_at,
            PaymentTransaction.transaction_type,
            PaymentTransaction.amount_minor,
        ).where(
            PaymentTransaction.workspace_id == workspace_id,
            PaymentTransaction.currency == currency,
            PaymentTransaction.created_at >= start_at,
            PaymentTransaction.created_at < end_at,
        )
    ).all()
    expense_rows = db.execute(
        select(Expense.incurred_on, Expense.amount_minor).where(
            Expense.workspace_id == workspace_id,
            Expense.currency == currency,
            Expense.incurred_on >= start_date,
            Expense.incurred_on <= end_date,
        )
    ).all()

    totals = [
        {"gross": 0, "refunds": 0, "expenses": 0}
        for _ in buckets
    ]

    def bucket_index(day: date) -> int | None:
        for index, (_, bucket_start, bucket_end) in enumerate(buckets):
            if bucket_start <= day <= bucket_end:
                return index
        return None

    for created_at, transaction_type, amount_minor in payment_rows:
        index = bucket_index(_workspace_date(created_at, timezone))
        if index is None:
            continue
        if transaction_type == "payment":
            totals[index]["gross"] += int(amount_minor or 0)
        elif transaction_type == "refund":
            totals[index]["refunds"] += int(amount_minor or 0)

    for incurred_on, amount_minor in expense_rows:
        index = bucket_index(incurred_on)
        if index is not None:
            totals[index]["expenses"] += int(amount_minor or 0)

    points: list[FinanceTrendPoint] = []
    for (label, bucket_start, bucket_end), total in zip(buckets, totals, strict=True):
        net = total["gross"] - total["refunds"]
        points.append(
            FinanceTrendPoint(
                label=label,
                start_date=bucket_start,
                end_date=bucket_end,
                gross_payments_minor=total["gross"],
                refunds_minor=total["refunds"],
                net_revenue_minor=net,
                expenses_minor=total["expenses"],
                profit_minor=net - total["expenses"],
            )
        )

    return FinanceTrendRead(
        start_date=start_date,
        end_date=end_date,
        currency=currency,
        mode=mode,
        points=points,
    )
