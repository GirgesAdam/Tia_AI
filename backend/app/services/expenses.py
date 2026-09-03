from __future__ import annotations

from datetime import UTC, datetime, timedelta
from uuid import UUID

from sqlalchemy import case, func, select
from sqlalchemy.orm import Session

from app.models.clinic_expense import ClinicExpense
from app.models.payment_transaction import PaymentTransaction
from app.schemas.expense import ExpenseSummary


def list_expenses(
    db: Session,
    *,
    workspace_id: UUID,
    days: int = 30,
    limit: int = 100,
) -> list[ClinicExpense]:
    cutoff = (datetime.now(UTC) - timedelta(days=days)).date()
    return list(
        db.scalars(
            select(ClinicExpense)
            .where(
                ClinicExpense.workspace_id == workspace_id,
                ClinicExpense.incurred_on >= cutoff,
            )
            .order_by(ClinicExpense.incurred_on.desc(), ClinicExpense.created_at.desc())
            .limit(limit)
        )
    )


def expense_summary(
    db: Session,
    *,
    workspace_id: UUID,
    days: int = 30,
    currency: str = "EGP",
) -> ExpenseSummary:
    now = datetime.now(UTC)
    start = now - timedelta(days=days)
    start_date = start.date()
    currency = currency.upper()

    signed_payment = case(
        (PaymentTransaction.transaction_type == "payment", PaymentTransaction.amount_minor),
        else_=-PaymentTransaction.amount_minor,
    )
    revenue = db.scalar(
        select(func.coalesce(func.sum(signed_payment), 0)).where(
            PaymentTransaction.workspace_id == workspace_id,
            PaymentTransaction.currency == currency,
            PaymentTransaction.created_at >= start,
            PaymentTransaction.created_at <= now,
        )
    )
    expenses = db.scalar(
        select(func.coalesce(func.sum(ClinicExpense.amount_minor), 0)).where(
            ClinicExpense.workspace_id == workspace_id,
            ClinicExpense.currency == currency,
            ClinicExpense.incurred_on >= start_date,
        )
    )

    revenue_minor = int(revenue or 0)
    expenses_minor = int(expenses or 0)
    return ExpenseSummary(
        days=days,
        currency=currency,
        revenue_minor=revenue_minor,
        expenses_minor=expenses_minor,
        operating_profit_minor=revenue_minor - expenses_minor,
    )
