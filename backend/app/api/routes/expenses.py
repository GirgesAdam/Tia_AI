from __future__ import annotations

from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.dependencies.security import WorkspaceAccess, get_workspace_admin
from app.database.session import get_db
from app.models.clinic_expense import ClinicExpense
from app.schemas.expense import ExpenseCreate, ExpenseRead, ExpenseSummary, ExpenseUpdate
from app.services.activity import record_activity_event
from app.services.expenses import expense_summary, list_expenses

router = APIRouter()


def _expense_or_404(
    db: Session,
    *,
    workspace_id: UUID,
    expense_id: UUID,
) -> ClinicExpense:
    expense = db.scalar(
        select(ClinicExpense).where(
            ClinicExpense.workspace_id == workspace_id,
            ClinicExpense.id == expense_id,
        )
    )
    if expense is None:
        raise HTTPException(status_code=404, detail="Expense not found.")
    return expense


@router.get("", response_model=list[ExpenseRead])
def read_expenses(
    access: Annotated[WorkspaceAccess, Depends(get_workspace_admin)],
    db: Annotated[Session, Depends(get_db)],
    days: Annotated[int, Query(ge=1, le=3650)] = 30,
    limit: Annotated[int, Query(ge=1, le=500)] = 100,
) -> list[ClinicExpense]:
    return list_expenses(
        db,
        workspace_id=access.workspace.id,
        days=days,
        limit=limit,
    )


@router.get("/summary", response_model=ExpenseSummary)
def read_expense_summary(
    access: Annotated[WorkspaceAccess, Depends(get_workspace_admin)],
    db: Annotated[Session, Depends(get_db)],
    days: Annotated[int, Query(ge=1, le=3650)] = 30,
    currency: Annotated[str, Query(min_length=3, max_length=3)] = "EGP",
) -> ExpenseSummary:
    return expense_summary(
        db,
        workspace_id=access.workspace.id,
        days=days,
        currency=currency,
    )


@router.post("", response_model=ExpenseRead, status_code=status.HTTP_201_CREATED)
def create_expense(
    payload: ExpenseCreate,
    access: Annotated[WorkspaceAccess, Depends(get_workspace_admin)],
    db: Annotated[Session, Depends(get_db)],
) -> ClinicExpense:
    expense = ClinicExpense(
        workspace_id=access.workspace.id,
        **payload.model_dump(),
    )
    db.add(expense)
    db.flush()
    record_activity_event(
        db,
        workspace_id=access.workspace.id,
        actor_type="staff",
        actor_user_id=access.user.id,
        action="expense.created",
        entity_type="clinic_expense",
        entity_id=expense.id,
        summary="Clinic expense created.",
        metadata={"category": expense.category, "amount_minor": expense.amount_minor},
    )
    db.commit()
    db.refresh(expense)
    return expense


@router.patch("/{expense_id}", response_model=ExpenseRead)
def update_expense(
    expense_id: UUID,
    payload: ExpenseUpdate,
    access: Annotated[WorkspaceAccess, Depends(get_workspace_admin)],
    db: Annotated[Session, Depends(get_db)],
) -> ClinicExpense:
    expense = _expense_or_404(
        db,
        workspace_id=access.workspace.id,
        expense_id=expense_id,
    )
    changes = payload.model_dump(exclude_unset=True)
    for key, value in changes.items():
        setattr(expense, key, value)
    if changes:
        record_activity_event(
            db,
            workspace_id=access.workspace.id,
            actor_type="staff",
            actor_user_id=access.user.id,
            action="expense.updated",
            entity_type="clinic_expense",
            entity_id=expense.id,
            summary="Clinic expense updated.",
            metadata={"changed_fields": sorted(changes)},
        )
    db.commit()
    db.refresh(expense)
    return expense


@router.delete("/{expense_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_expense(
    expense_id: UUID,
    access: Annotated[WorkspaceAccess, Depends(get_workspace_admin)],
    db: Annotated[Session, Depends(get_db)],
) -> None:
    expense = _expense_or_404(
        db,
        workspace_id=access.workspace.id,
        expense_id=expense_id,
    )
    record_activity_event(
        db,
        workspace_id=access.workspace.id,
        actor_type="staff",
        actor_user_id=access.user.id,
        action="expense.deleted",
        entity_type="clinic_expense",
        entity_id=expense.id,
        summary="Clinic expense deleted.",
        metadata={"category": expense.category, "amount_minor": expense.amount_minor},
    )
    db.delete(expense)
    db.commit()
