from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
from uuid import UUID

from sqlalchemy import select, update
from sqlalchemy.orm import Session

from app.integrations.clinic.authority import (
    ClinicIntegrationAuthorityError,
    require_tia_workspace_domain_write,
)
from app.models.appointment import Appointment
from app.models.payment_transaction import PAYMENT_METHODS, PaymentAllocation, PaymentTransaction
from app.schemas.payments import AppointmentPaymentSummaryRead, PaymentTransactionRead
from app.services.activity import record_activity_event


class PaymentOperationError(ValueError):
    pass


class PaymentOperationNotFound(PaymentOperationError):
    pass


@dataclass(frozen=True)
class PaymentTotals:
    gross_paid_minor: int
    refunded_minor: int
    net_paid_minor: int
    balance_minor: int
    payment_status: str
    payment_method: str


@dataclass(frozen=True)
class AppointmentLedgerEntry:
    """One transaction sliced to the amount explicitly allocated to an appointment."""

    transaction: PaymentTransaction
    allocated_amount_minor: int


def _row_transaction(row: PaymentTransaction | AppointmentLedgerEntry) -> PaymentTransaction:
    if isinstance(row, AppointmentLedgerEntry):
        return row.transaction
    return row


def _row_amount_minor(row: object) -> int:
    allocated = getattr(row, "allocated_amount_minor", None)
    if allocated is not None:
        return int(allocated)
    return int(getattr(row, "amount_minor"))


def _locked_appointment(db: Session, *, workspace_id: UUID, appointment_id: UUID) -> Appointment:
    appointment = db.scalar(
        select(Appointment)
        .where(
            Appointment.workspace_id == workspace_id,
            Appointment.id == appointment_id,
        )
        .with_for_update()
    )
    if appointment is None:
        raise PaymentOperationNotFound("Appointment not found.")
    return appointment


def _ledger_rows(
    db: Session,
    *,
    workspace_id: UUID,
    appointment_id: UUID,
    for_update: bool = False,
) -> list[AppointmentLedgerEntry]:
    """Return only the financial amounts explicitly allocated to one appointment.

    Patient-level/unallocated transactions are intentionally absent. A payment
    split across appointments contributes only its allocation amount to each
    appointment's balance and analytics.
    """

    stmt = (
        select(PaymentTransaction, PaymentAllocation.amount_minor)
        .join(
            PaymentAllocation,
            (PaymentAllocation.workspace_id == PaymentTransaction.workspace_id)
            & (PaymentAllocation.transaction_id == PaymentTransaction.id),
        )
        .where(
            PaymentTransaction.workspace_id == workspace_id,
            PaymentAllocation.appointment_id == appointment_id,
        )
        .order_by(PaymentTransaction.created_at, PaymentTransaction.id)
    )
    if for_update:
        stmt = stmt.with_for_update()
    return [
        AppointmentLedgerEntry(transaction=transaction, allocated_amount_minor=int(amount_minor))
        for transaction, amount_minor in db.execute(stmt).all()
    ]


def _payment_totals(*, appointment: Appointment, rows: list[object]) -> PaymentTotals:
    # A prepaid-package session is financially settled by a package purchase that
    # happened elsewhere. With no appointment-level ledger rows it must show zero
    # balance without manufacturing payment revenue for this visit.
    if not rows and getattr(appointment, "billing_context", "standard") == "package_prepaid":
        return PaymentTotals(
            gross_paid_minor=0,
            refunded_minor=0,
            net_paid_minor=0,
            balance_minor=0,
            payment_status="paid",
            payment_method="unknown",
        )

    payments = [row for row in rows if _row_transaction(row).transaction_type == "payment"]
    refunds = [row for row in rows if _row_transaction(row).transaction_type == "refund"]
    gross = sum(_row_amount_minor(row) for row in payments)
    refunded = sum(_row_amount_minor(row) for row in refunds)
    net = max(gross - refunded, 0)
    balance = max(int(appointment.price_minor) - net, 0)

    if gross > 0 and net == 0 and refunded > 0:
        status = "refunded"
    elif net <= 0:
        status = "unpaid"
    elif appointment.price_minor > 0 and net >= appointment.price_minor:
        status = "paid"
    else:
        status = "partial"

    methods = {
        _row_transaction(row).payment_method
        for row in payments
        if _row_transaction(row).payment_method != "unknown"
    }
    if not payments:
        method = "unknown"
    elif len(methods) == 1:
        method = next(iter(methods))
    elif not methods:
        method = "unknown"
    else:
        method = "other"
    # Appointment's compatibility field predates the explicit online method.
    if method == "online":
        method = "other"

    return PaymentTotals(
        gross_paid_minor=gross,
        refunded_minor=refunded,
        net_paid_minor=net,
        balance_minor=balance,
        payment_status=status,
        payment_method=method,
    )


def _refunds_by_payment(rows: list[object]) -> dict[UUID, int]:
    result: dict[UUID, int] = {}
    for row in rows:
        transaction = _row_transaction(row)
        if transaction.transaction_type == "refund" and transaction.reference_transaction_id is not None:
            result[transaction.reference_transaction_id] = (
                result.get(transaction.reference_transaction_id, 0) + _row_amount_minor(row)
            )
    return result


def _transaction_reads(rows: list[PaymentTransaction | AppointmentLedgerEntry]) -> list[PaymentTransactionRead]:
    refunds = _refunds_by_payment(list(rows))
    result: list[PaymentTransactionRead] = []
    for row in rows:
        transaction = _row_transaction(row)
        allocated_amount_minor = _row_amount_minor(row)
        refunded_minor = (
            refunds.get(transaction.id, 0) if transaction.transaction_type == "payment" else 0
        )
        refundable_minor = (
            max(allocated_amount_minor - refunded_minor, 0)
            if transaction.transaction_type == "payment"
            else 0
        )
        result.append(
            PaymentTransactionRead(
                id=transaction.id,
                workspace_id=transaction.workspace_id,
                appointment_id=transaction.appointment_id,
                origin_appointment_id=transaction.origin_appointment_id,
                patient_id=transaction.patient_id,
                created_by_user_id=transaction.created_by_user_id,
                reference_transaction_id=transaction.reference_transaction_id,
                transaction_type=transaction.transaction_type,
                amount_minor=transaction.amount_minor,
                allocated_amount_minor=allocated_amount_minor,
                currency=transaction.currency,
                payment_method=transaction.payment_method,
                source=transaction.source,
                external_reference=transaction.external_reference,
                reason=transaction.reason,
                created_at=transaction.created_at,
                refunded_minor=refunded_minor,
                refundable_minor=refundable_minor,
            )
        )
    return result


def _transaction_has_allocation(
    db: Session,
    *,
    workspace_id: UUID,
    transaction_id: UUID,
    appointment_id: UUID,
) -> bool:
    allocation_id = db.scalar(
        select(PaymentAllocation.id).where(
            PaymentAllocation.workspace_id == workspace_id,
            PaymentAllocation.transaction_id == transaction_id,
            PaymentAllocation.appointment_id == appointment_id,
        )
    )
    return allocation_id is not None


def _add_single_appointment_allocation(
    db: Session,
    *,
    transaction: PaymentTransaction,
    appointment_id: UUID,
    amount_minor: int,
) -> PaymentAllocation:
    if amount_minor <= 0 or amount_minor > int(transaction.amount_minor):
        raise PaymentOperationError("Payment allocation must be positive and cannot exceed the transaction amount.")
    allocation = PaymentAllocation(
        workspace_id=transaction.workspace_id,
        transaction_id=transaction.id,
        appointment_id=appointment_id,
        amount_minor=amount_minor,
        created_at=transaction.created_at,
    )
    db.add(allocation)
    db.flush()
    return allocation


def validate_allocation_total(*, transaction_amount_minor: int, allocation_amounts: list[int]) -> None:
    """Fail closed when explicit allocations overstate the financial fact.

    Less than the transaction amount is valid and leaves the remainder at the
    patient level. Zero allocations is the canonical unallocated-payment case.
    """

    if transaction_amount_minor <= 0:
        raise PaymentOperationError("Payment amount must be positive.")
    if any(int(amount) <= 0 for amount in allocation_amounts):
        raise PaymentOperationError("Payment allocations must be positive.")
    if sum(int(amount) for amount in allocation_amounts) > int(transaction_amount_minor):
        raise PaymentOperationError("Payment allocations cannot exceed the transaction amount.")


def sync_appointment_payment_snapshot(
    appointment: Appointment,
    rows: list[object],
) -> PaymentTotals:
    totals = _payment_totals(appointment=appointment, rows=rows)
    appointment.payment_status = totals.payment_status
    if (
        getattr(appointment, "billing_context", "standard") == "package_prepaid"
        and totals.gross_paid_minor == 0
        and totals.refunded_minor == 0
    ):
        appointment.amount_paid_minor = None
    else:
        appointment.amount_paid_minor = totals.net_paid_minor
    appointment.payment_method = totals.payment_method
    return totals


def refresh_appointment_payment_snapshots(
    db: Session,
    *,
    workspace_id: UUID,
    appointment_ids: set[UUID],
) -> None:
    """Recompute appointment compatibility snapshots from explicit allocations.

    External sync can create patient-level or multi-appointment transactions,
    so callers must refresh only appointments that received explicit allocations.
    Row locks keep the financial snapshot deterministic against concurrent staff
    payment operations.
    """

    for appointment_id in sorted(appointment_ids, key=str):
        appointment = _locked_appointment(
            db, workspace_id=workspace_id, appointment_id=appointment_id
        )
        rows = _ledger_rows(
            db,
            workspace_id=workspace_id,
            appointment_id=appointment_id,
            for_update=True,
        )
        sync_appointment_payment_snapshot(appointment, list(rows))


def get_appointment_payment_summary(
    db: Session,
    *,
    workspace_id: UUID,
    appointment_id: UUID,
    can_refund: bool = False,
) -> AppointmentPaymentSummaryRead:
    appointment = db.scalar(
        select(Appointment).where(
            Appointment.workspace_id == workspace_id,
            Appointment.id == appointment_id,
        )
    )
    if appointment is None:
        raise PaymentOperationNotFound("Appointment not found.")
    rows = _ledger_rows(db, workspace_id=workspace_id, appointment_id=appointment.id)
    totals = _payment_totals(appointment=appointment, rows=list(rows))
    return AppointmentPaymentSummaryRead(
        appointment_id=appointment.id,
        patient_id=appointment.patient_id,
        currency=appointment.currency,
        price_minor=appointment.price_minor,
        gross_paid_minor=totals.gross_paid_minor,
        refunded_minor=totals.refunded_minor,
        net_paid_minor=totals.net_paid_minor,
        balance_minor=totals.balance_minor,
        payment_status=totals.payment_status,
        billing_context=getattr(appointment, "billing_context", "standard"),
        package_external_id=getattr(appointment, "package_external_id", None),
        transactions=_transaction_reads(rows),
        can_refund=can_refund,
    )


def record_payment(
    db: Session,
    *,
    workspace_id: UUID,
    appointment_id: UUID,
    amount_minor: int,
    payment_method: str,
    created_by_user_id: UUID | None,
    external_reference: str | None = None,
    idempotency_key: str | None = None,
    source: str = "staff",
) -> PaymentTransaction:
    if amount_minor <= 0:
        raise PaymentOperationError("Payment amount must be positive.")
    if payment_method not in PAYMENT_METHODS or payment_method == "unknown":
        raise PaymentOperationError("Unsupported payment method.")
    if source not in {"staff", "integration", "system"}:
        raise PaymentOperationError("Unsupported payment source.")
    if source != "integration":
        try:
            require_tia_workspace_domain_write(
                db, workspace_id=workspace_id, domain="payments"
            )
        except ClinicIntegrationAuthorityError as exc:
            raise PaymentOperationError(str(exc)) from exc

    if idempotency_key:
        existing = db.scalar(
            select(PaymentTransaction).where(
                PaymentTransaction.workspace_id == workspace_id,
                PaymentTransaction.idempotency_key == idempotency_key,
            )
        )
        if existing is not None:
            if (
                existing.transaction_type != "payment"
                or not _transaction_has_allocation(
                    db,
                    workspace_id=workspace_id,
                    transaction_id=existing.id,
                    appointment_id=appointment_id,
                )
            ):
                raise PaymentOperationError("Idempotency key is already used by another payment operation.")
            return existing

    appointment = _locked_appointment(
        db,
        workspace_id=workspace_id,
        appointment_id=appointment_id,
    )
    if appointment.status not in {"pending", "confirmed", "completed"}:
        raise PaymentOperationError(
            f"Payments cannot be recorded for an appointment in '{appointment.status}' status."
        )
    rows = _ledger_rows(
        db,
        workspace_id=workspace_id,
        appointment_id=appointment.id,
        for_update=True,
    )
    totals = _payment_totals(appointment=appointment, rows=list(rows))
    if totals.balance_minor <= 0:
        raise PaymentOperationError("This appointment has no outstanding balance.")
    if amount_minor > totals.balance_minor:
        raise PaymentOperationError(
            f"Payment exceeds outstanding balance of {totals.balance_minor} {appointment.currency} minor units."
        )

    transaction = PaymentTransaction(
        workspace_id=workspace_id,
        appointment_id=appointment.id,
        origin_appointment_id=appointment.id,
        patient_id=appointment.patient_id,
        created_by_user_id=created_by_user_id,
        reference_transaction_id=None,
        transaction_type="payment",
        amount_minor=amount_minor,
        currency=appointment.currency,
        payment_method=payment_method,
        source=source,
        external_reference=external_reference,
        reason=None,
        idempotency_key=idempotency_key,
        created_at=datetime.now(UTC),
    )
    db.add(transaction)
    db.flush()
    _add_single_appointment_allocation(
        db,
        transaction=transaction,
        appointment_id=appointment.id,
        amount_minor=amount_minor,
    )
    rows.append(AppointmentLedgerEntry(transaction=transaction, allocated_amount_minor=amount_minor))
    sync_appointment_payment_snapshot(appointment, list(rows))
    record_activity_event(
        db,
        workspace_id=workspace_id,
        actor_type="staff" if created_by_user_id else "system",
        actor_user_id=created_by_user_id,
        action="payment.recorded",
        entity_type="payment_transaction",
        entity_id=transaction.id,
        summary="Payment recorded",
        metadata={
            "appointment_id": appointment.id,
            "amount_minor": amount_minor,
            "currency": appointment.currency,
            "payment_method": payment_method,
            "source": source,
        },
    )
    db.flush()
    return transaction


def record_refund(
    db: Session,
    *,
    workspace_id: UUID,
    appointment_id: UUID,
    payment_transaction_id: UUID,
    amount_minor: int,
    reason: str,
    created_by_user_id: UUID,
    idempotency_key: str | None = None,
) -> PaymentTransaction:
    if amount_minor <= 0:
        raise PaymentOperationError("Refund amount must be positive.")
    try:
        require_tia_workspace_domain_write(
            db, workspace_id=workspace_id, domain="payments"
        )
    except ClinicIntegrationAuthorityError as exc:
        raise PaymentOperationError(str(exc)) from exc
    reason = reason.strip()
    if not reason:
        raise PaymentOperationError("Refund reason cannot be empty.")

    if idempotency_key:
        existing = db.scalar(
            select(PaymentTransaction).where(
                PaymentTransaction.workspace_id == workspace_id,
                PaymentTransaction.idempotency_key == idempotency_key,
            )
        )
        if existing is not None:
            if (
                existing.transaction_type != "refund"
                or not _transaction_has_allocation(
                    db,
                    workspace_id=workspace_id,
                    transaction_id=existing.id,
                    appointment_id=appointment_id,
                )
            ):
                raise PaymentOperationError("Idempotency key is already used by another payment operation.")
            return existing

    appointment = _locked_appointment(
        db,
        workspace_id=workspace_id,
        appointment_id=appointment_id,
    )
    if appointment.status == "rescheduled":
        raise PaymentOperationError("Refunds must be recorded on the replacement appointment.")
    rows = _ledger_rows(
        db,
        workspace_id=workspace_id,
        appointment_id=appointment.id,
        for_update=True,
    )
    payment_entry = next(
        (
            row
            for row in rows
            if row.transaction.id == payment_transaction_id
            and row.transaction.transaction_type == "payment"
        ),
        None,
    )
    if payment_entry is None:
        raise PaymentOperationNotFound("Payment transaction not found for this appointment.")
    payment = payment_entry.transaction
    already_refunded = _refunds_by_payment(list(rows)).get(payment.id, 0)
    refundable = max(int(payment_entry.allocated_amount_minor) - already_refunded, 0)
    if amount_minor > refundable:
        raise PaymentOperationError(
            f"Refund exceeds refundable amount of {refundable} {appointment.currency} minor units."
        )

    transaction = PaymentTransaction(
        workspace_id=workspace_id,
        appointment_id=appointment.id,
        origin_appointment_id=appointment.id,
        patient_id=appointment.patient_id,
        created_by_user_id=created_by_user_id,
        reference_transaction_id=payment.id,
        transaction_type="refund",
        amount_minor=amount_minor,
        currency=appointment.currency,
        payment_method=payment.payment_method,
        source="staff",
        external_reference=None,
        reason=reason[:500],
        idempotency_key=idempotency_key,
        created_at=datetime.now(UTC),
    )
    db.add(transaction)
    db.flush()
    _add_single_appointment_allocation(
        db,
        transaction=transaction,
        appointment_id=appointment.id,
        amount_minor=amount_minor,
    )
    rows.append(AppointmentLedgerEntry(transaction=transaction, allocated_amount_minor=amount_minor))
    sync_appointment_payment_snapshot(appointment, list(rows))
    record_activity_event(
        db,
        workspace_id=workspace_id,
        actor_type="staff",
        actor_user_id=created_by_user_id,
        action="payment.refunded",
        entity_type="payment_transaction",
        entity_id=transaction.id,
        summary="Payment refunded",
        metadata={
            "appointment_id": appointment.id,
            "payment_transaction_id": payment.id,
            "amount_minor": amount_minor,
            "currency": appointment.currency,
            "reason_present": True,
        },
    )
    db.flush()
    return transaction


def reallocate_appointment_payments_on_reschedule(
    db: Session,
    *,
    workspace_id: UUID,
    from_appointment_id: UUID,
    to_appointment_id: UUID,
) -> None:
    """Move appointment allocations without changing immutable financial facts.

    Amount, type, origin_appointment_id and timestamps remain immutable. The
    allocation row is authoritative; the nullable transaction appointment_id is
    updated only as a compatibility hint for legacy single-appointment readers.
    """
    db.execute(
        update(PaymentAllocation)
        .where(
            PaymentAllocation.workspace_id == workspace_id,
            PaymentAllocation.appointment_id == from_appointment_id,
        )
        .values(appointment_id=to_appointment_id)
    )
    db.execute(
        update(PaymentTransaction)
        .where(
            PaymentTransaction.workspace_id == workspace_id,
            PaymentTransaction.appointment_id == from_appointment_id,
        )
        .values(appointment_id=to_appointment_id)
    )


def seed_payment_ledger_from_appointment_snapshot(
    db: Session,
    *,
    appointment: Appointment,
    source_key: str,
    payment_external_reference: str | None = None,
    refund_amount_minor: int | None = None,
    refund_reason: str | None = None,
    refunded_at: datetime | None = None,
) -> None:
    """Seed imported appointment-embedded financial facts once.

    A direct payment becomes an immutable payment + allocation. An optional
    embedded refund becomes a refund transaction referencing that payment.
    Package-prepaid sessions intentionally produce no ledger rows: the package
    purchase is a separate financial event and must not be counted once per use.

    Re-running a tabular import must not overwrite staff-recorded financial
    transactions. If any ledger rows already exist, their derived snapshot wins.
    """
    rows = _ledger_rows(
        db,
        workspace_id=appointment.workspace_id,
        appointment_id=appointment.id,
        for_update=False,
    )
    if rows:
        sync_appointment_payment_snapshot(appointment, list(rows))
        return

    if getattr(appointment, "billing_context", "standard") == "package_prepaid":
        sync_appointment_payment_snapshot(appointment, [])
        return

    amount = int(appointment.amount_paid_minor or 0)
    status = appointment.payment_status
    if amount <= 0 or status not in {"paid", "partial", "refunded"}:
        return

    explicit_refund = int(refund_amount_minor or 0)
    if explicit_refund < 0:
        raise PaymentOperationError("Imported refund amount cannot be negative.")
    refund_amount = amount if status == "refunded" and explicit_refund == 0 else explicit_refund
    if refund_amount > amount:
        raise PaymentOperationError("Imported refund amount cannot exceed the direct payment amount.")

    method = appointment.payment_method if appointment.payment_method in PAYMENT_METHODS else "unknown"
    now = datetime.now(UTC)
    payment = PaymentTransaction(
        workspace_id=appointment.workspace_id,
        appointment_id=appointment.id,
        origin_appointment_id=appointment.id,
        patient_id=appointment.patient_id,
        created_by_user_id=None,
        reference_transaction_id=None,
        transaction_type="payment",
        amount_minor=amount,
        currency=appointment.currency,
        payment_method=method,
        source="integration",
        external_reference=payment_external_reference,
        reason=None,
        idempotency_key=f"import-payment:{source_key}"[:128],
        created_at=now,
    )
    db.add(payment)
    db.flush()
    _add_single_appointment_allocation(
        db,
        transaction=payment,
        appointment_id=appointment.id,
        amount_minor=amount,
    )
    rows.append(AppointmentLedgerEntry(transaction=payment, allocated_amount_minor=amount))

    if refund_amount > 0:
        refund = PaymentTransaction(
            workspace_id=appointment.workspace_id,
            appointment_id=appointment.id,
            origin_appointment_id=appointment.id,
            patient_id=appointment.patient_id,
            created_by_user_id=None,
            reference_transaction_id=payment.id,
            transaction_type="refund",
            amount_minor=refund_amount,
            currency=appointment.currency,
            payment_method=method,
            source="integration",
            external_reference=None,
            reason=refund_reason or "Imported appointment refund",
            idempotency_key=f"import-refund:{source_key}"[:128],
            created_at=refunded_at or now,
        )
        db.add(refund)
        db.flush()
        _add_single_appointment_allocation(
            db,
            transaction=refund,
            appointment_id=appointment.id,
            amount_minor=refund_amount,
        )
        rows.append(AppointmentLedgerEntry(transaction=refund, allocated_amount_minor=refund_amount))
    sync_appointment_payment_snapshot(appointment, list(rows))

