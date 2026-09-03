from __future__ import annotations

from datetime import date, timedelta
from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, Response, status
from sqlalchemy.orm import Session

from app.api.dependencies.security import WorkspaceAccess, get_workspace_admin, get_workspace_reader
from app.database.session import get_db
from app.schemas.finance import ExpenseCreate, ExpenseRead, ExpenseUpdate, ProfitabilityRead
from app.services.finance import (
    FinanceNotFound,
    FinanceOperationError,
    create_expense,
    delete_expense,
    list_expenses,
    profitability_summary,
    update_expense,
)

router = APIRouter()


def _bad_request(detail: str) -> HTTPException:
    return HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=detail)


def _not_found(detail: str) -> HTTPException:
    return HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=detail)


@router.get("/expenses", response_model=list[ExpenseRead])
def expense_list(
    access: Annotated[WorkspaceAccess, Depends(get_workspace_reader)],
    db: Annotated[Session, Depends(get_db)],
    start_date: date | None = None,
    end_date: date | None = None,
    limit: int = Query(default=200, ge=1, le=500),
) -> list[ExpenseRead]:
    try:
        rows = list_expenses(
            db,
            workspace_id=access.workspace.id,
            start_date=start_date,
            end_date=end_date,
            limit=limit,
        )
    except FinanceOperationError as exc:
        raise _bad_request(str(exc)) from exc
    return [ExpenseRead.model_validate(row) for row in rows]


@router.post("/expenses", response_model=ExpenseRead, status_code=status.HTTP_201_CREATED)
def expense_create(
    payload: ExpenseCreate,
    access: Annotated[WorkspaceAccess, Depends(get_workspace_admin)],
    db: Annotated[Session, Depends(get_db)],
) -> ExpenseRead:
    expense = create_expense(
        db,
        workspace_id=access.workspace.id,
        created_by_user_id=access.user.id,
        payload=payload,
    )
    db.commit()
    db.refresh(expense)
    return ExpenseRead.model_validate(expense)


@router.patch("/expenses/{expense_id}", response_model=ExpenseRead)
def expense_update(
    expense_id: UUID,
    payload: ExpenseUpdate,
    access: Annotated[WorkspaceAccess, Depends(get_workspace_admin)],
    db: Annotated[Session, Depends(get_db)],
) -> ExpenseRead:
    try:
        expense = update_expense(
            db,
            workspace_id=access.workspace.id,
            expense_id=expense_id,
            payload=payload,
        )
        db.commit()
        db.refresh(expense)
    except FinanceNotFound as exc:
        db.rollback()
        raise _not_found(str(exc)) from exc
    return ExpenseRead.model_validate(expense)


@router.delete("/expenses/{expense_id}", status_code=status.HTTP_204_NO_CONTENT)
def expense_delete(
    expense_id: UUID,
    access: Annotated[WorkspaceAccess, Depends(get_workspace_admin)],
    db: Annotated[Session, Depends(get_db)],
) -> Response:
    try:
        delete_expense(db, workspace_id=access.workspace.id, expense_id=expense_id)
        db.commit()
    except FinanceNotFound as exc:
        db.rollback()
        raise _not_found(str(exc)) from exc
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.get("/profitability", response_model=ProfitabilityRead)
def profitability(
    access: Annotated[WorkspaceAccess, Depends(get_workspace_reader)],
    db: Annotated[Session, Depends(get_db)],
    end_date: date = Query(default_factory=date.today),
    start_date: date | None = None,
) -> ProfitabilityRead:
    resolved_start = start_date or (end_date - timedelta(days=29))
    try:
        return profitability_summary(
            db,
            workspace_id=access.workspace.id,
            timezone_name=access.workspace.timezone,
            start_date=resolved_start,
            end_date=end_date,
        )
    except FinanceOperationError as exc:
        raise _bad_request(str(exc)) from exc
