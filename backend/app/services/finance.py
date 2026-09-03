from __future__ import annotations

from datetime import UTC, date, datetime, time, timedelta
from uuid import UUID
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from sqlalchemy import case, func, select
from sqlalchemy.orm import Session

from app.models.expense import Expense
from app.models.payment_transaction import PaymentTransaction
from app.schemas.finance import (
    ExpenseCreate,
    ExpenseUpdate,
    ProfitabilityCurrencyRead,
    ProfitabilityRead,
)
from app.services.activity import record_activity_event


class FinanceNotFound(ValueError):
    pass


class FinanceOperationError(ValueError):
    pass


def _expense_or_raise(db: Session, *, workspace_id: UUID, expense_id: UUID) -> Expense:
    expense = db.scalar(
        select(Expense).where(
            Expense.workspace_id == workspace_id,
            Expense.id == expense_id,
        )
    )
    if expense is None:
        raise FinanceNotFound("Expense not found.")
    return expense


def list_expenses(
    db: Session,
    *,
    workspace_id: UUID,
    start_date: date | None = None,
    end_date: date | None = None,
    limit: int = 200,
) -> list[Expense]:
    if start_date and end_date and start_date > end_date:
        raise FinanceOperationError("start_date must be on or before end_date.")
    stmt = select(Expense).where(Expense.workspace_id == workspace_id)
    if start_date is not None:
        stmt = stmt.where(Expense.incurred_on >= start_date)
    if end_date is not None:
        stmt = stmt.where(Expense.incurred_on <= end_date)
    return list(
        db.scalars(
            stmt.order_by(Expense.incurred_on.desc(), Expense.created_at.desc()).limit(limit)
        )
    )


def create_expense(
    db: Session,
    *,
    workspace_id: UUID,
    created_by_user_id: UUID,
    payload: ExpenseCreate,
) -> Expense:
    expense = Expense(
        workspace_id=workspace_id,
        created_by_user_id=created_by_user_id,
        **payload.model_dump(),
    )
    db.add(expense)
    db.flush()
    record_activity_event(
        db,
        workspace_id=workspace_id,
        actor_type="staff",
        actor_user_id=created_by_user_id,
        action="expense.created",
        entity_type="expense",
        entity_id=expense.id,
        summary="Added an expense record.",
        metadata={
            "category": expense.category,
            "amount_minor": expense.amount_minor,
            "currency": expense.currency,
            "incurred_on": expense.incurred_on.isoformat(),
        },
    )
    return expense


def update_expense(
    db: Session,
    *,
    workspace_id: UUID,
    expense_id: UUID,
    actor_user_id: UUID,
    payload: ExpenseUpdate,
) -> Expense:
    expense = _expense_or_raise(db, workspace_id=workspace_id, expense_id=expense_id)
    requested_changes = payload.model_dump(exclude_unset=True)
    changed_fields: list[str] = []
    for field_name, value in requested_changes.items():
        if getattr(expense, field_name) == value:
            continue
        setattr(expense, field_name, value)
        changed_fields.append(field_name)
    if not changed_fields:
        return expense

    db.flush()
    record_activity_event(
        db,
        workspace_id=workspace_id,
        actor_type="staff",
        actor_user_id=actor_user_id,
        action="expense.updated",
        entity_type="expense",
        entity_id=expense.id,
        summary="Updated an expense record.",
        metadata={"changed_fields": sorted(changed_fields)},
    )
    return expense


def delete_expense(
    db: Session,
    *,
    workspace_id: UUID,
    expense_id: UUID,
    actor_user_id: UUID,
) -> None:
    expense = _expense_or_raise(db, workspace_id=workspace_id, expense_id=expense_id)
    metadata = {
        "category": expense.category,
        "amount_minor": expense.amount_minor,
        "currency": expense.currency,
        "incurred_on": expense.incurred_on.isoformat(),
    }
    db.delete(expense)
    record_activity_event(
        db,
        workspace_id=workspace_id,
        actor_type="staff",
        actor_user_id=actor_user_id,
        action="expense.deleted",
        entity_type="expense",
        entity_id=expense.id,
        summary="Deleted an expense record.",
        metadata=metadata,
    )
    db.flush()


def _utc_bounds(
    *,
    start_date: date,
    end_date: date,
    timezone_name: str,
) -> tuple[datetime, datetime]:
    if start_date > end_date:
        raise FinanceOperationError("start_date must be on or before end_date.")
    try:
        timezone = ZoneInfo(timezone_name)
    except ZoneInfoNotFoundError:
        timezone = ZoneInfo("UTC")
    start_local = datetime.combine(start_date, time.min, tzinfo=timezone)
    end_local = datetime.combine(end_date + timedelta(days=1), time.min, tzinfo=timezone)
    return start_local.astimezone(UTC), end_local.astimezone(UTC)


def profitability_summary(
    db: Session,
    *,
    workspace_id: UUID,
    timezone_name: str,
    start_date: date,
    end_date: date,
) -> ProfitabilityRead:
    start_at, end_at = _utc_bounds(
        start_date=start_date,
        end_date=end_date,
        timezone_name=timezone_name,
    )

    payment_rows = db.execute(
        select(
            PaymentTransaction.currency,
            func.coalesce(
                func.sum(
                    case(
                        (
                            PaymentTransaction.transaction_type == "payment",
                            PaymentTransaction.amount_minor,
                        ),
                        else_=0,
                    )
                ),
                0,
            ).label("gross_payments_minor"),
            func.coalesce(
                func.sum(
                    case(
                        (
                            PaymentTransaction.transaction_type == "refund",
                            PaymentTransaction.amount_minor,
                        ),
                        else_=0,
                    )
                ),
                0,
            ).label("refunds_minor"),
        )
        .where(
            PaymentTransaction.workspace_id == workspace_id,
            PaymentTransaction.created_at >= start_at,
            PaymentTransaction.created_at < end_at,
        )
        .group_by(PaymentTransaction.currency)
    ).all()
    expense_rows = db.execute(
        select(
            Expense.currency,
            func.coalesce(func.sum(Expense.amount_minor), 0).label("expenses_minor"),
        )
        .where(
            Expense.workspace_id == workspace_id,
            Expense.incurred_on >= start_date,
            Expense.incurred_on <= end_date,
        )
        .group_by(Expense.currency)
    ).all()

    payments = {
        str(currency).upper(): (int(gross or 0), int(refunds or 0))
        for currency, gross, refunds in payment_rows
    }
    expenses = {
        str(currency).upper(): int(amount or 0)
        for currency, amount in expense_rows
    }
    currencies = sorted(set(payments) | set(expenses))
    rows: list[ProfitabilityCurrencyRead] = []
    for currency in currencies:
        gross, refunds = payments.get(currency, (0, 0))
        expense_total = expenses.get(currency, 0)
        net_revenue = gross - refunds
        rows.append(
            ProfitabilityCurrencyRead(
                currency=currency,
                gross_payments_minor=gross,
                refunds_minor=refunds,
                net_revenue_minor=net_revenue,
                expenses_minor=expense_total,
                profit_minor=net_revenue - expense_total,
            )
        )
    return ProfitabilityRead(
        start_date=start_date,
        end_date=end_date,
        currencies=rows,
    )
