from __future__ import annotations

from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, Header, HTTPException, status
from sqlalchemy.orm import Session

from app.api.dependencies.security import (
    WorkspaceAccess,
    get_workspace_admin,
    get_workspace_reader,
)
from app.database.session import get_db
from app.schemas.payments import AppointmentPaymentSummaryRead, PaymentCreate, RefundCreate
from app.services.payments import (
    PaymentOperationError,
    PaymentOperationNotFound,
    get_appointment_payment_summary,
    record_payment,
    record_refund,
)

router = APIRouter()


def _not_found(detail: str) -> HTTPException:
    return HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=detail)


def _conflict(detail: str) -> HTTPException:
    return HTTPException(status_code=status.HTTP_409_CONFLICT, detail=detail)


@router.get("/appointments/{appointment_id}", response_model=AppointmentPaymentSummaryRead)
def appointment_payment_summary(
    appointment_id: UUID,
    access: Annotated[WorkspaceAccess, Depends(get_workspace_reader)],
    db: Annotated[Session, Depends(get_db)],
) -> AppointmentPaymentSummaryRead:
    try:
        return get_appointment_payment_summary(
            db,
            workspace_id=access.workspace.id,
            appointment_id=appointment_id,
            can_refund=access.membership.role == "admin",
        )
    except PaymentOperationNotFound as exc:
        raise _not_found(str(exc)) from exc


@router.post(
    "/appointments/{appointment_id}/payments",
    response_model=AppointmentPaymentSummaryRead,
    status_code=status.HTTP_201_CREATED,
)
def create_payment(
    appointment_id: UUID,
    payload: PaymentCreate,
    access: Annotated[WorkspaceAccess, Depends(get_workspace_reader)],
    db: Annotated[Session, Depends(get_db)],
    idempotency_key: Annotated[
        str | None,
        Header(alias="Idempotency-Key", max_length=128),
    ] = None,
) -> AppointmentPaymentSummaryRead:
    try:
        record_payment(
            db,
            workspace_id=access.workspace.id,
            appointment_id=appointment_id,
            amount_minor=payload.amount_minor,
            payment_method=payload.payment_method,
            external_reference=payload.external_reference,
            created_by_user_id=access.user.id,
            idempotency_key=idempotency_key,
        )
        db.commit()
    except PaymentOperationNotFound as exc:
        db.rollback()
        raise _not_found(str(exc)) from exc
    except PaymentOperationError as exc:
        db.rollback()
        raise _conflict(str(exc)) from exc

    return get_appointment_payment_summary(
        db,
        workspace_id=access.workspace.id,
        appointment_id=appointment_id,
        can_refund=access.membership.role == "admin",
    )


@router.post(
    "/appointments/{appointment_id}/refunds",
    response_model=AppointmentPaymentSummaryRead,
    status_code=status.HTTP_201_CREATED,
)
def create_refund(
    appointment_id: UUID,
    payload: RefundCreate,
    access: Annotated[WorkspaceAccess, Depends(get_workspace_admin)],
    db: Annotated[Session, Depends(get_db)],
    idempotency_key: Annotated[
        str | None,
        Header(alias="Idempotency-Key", max_length=128),
    ] = None,
) -> AppointmentPaymentSummaryRead:
    try:
        record_refund(
            db,
            workspace_id=access.workspace.id,
            appointment_id=appointment_id,
            payment_transaction_id=payload.payment_transaction_id,
            amount_minor=payload.amount_minor,
            reason=payload.reason,
            created_by_user_id=access.user.id,
            idempotency_key=idempotency_key,
        )
        db.commit()
    except PaymentOperationNotFound as exc:
        db.rollback()
        raise _not_found(str(exc)) from exc
    except PaymentOperationError as exc:
        db.rollback()
        raise _conflict(str(exc)) from exc

    return get_appointment_payment_summary(
        db,
        workspace_id=access.workspace.id,
        appointment_id=appointment_id,
        can_refund=True,
    )
