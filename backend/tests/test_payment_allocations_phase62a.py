from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace
from uuid import uuid4

import pytest

from app.integrations.clinic.base import PaymentAllocationRecord, PaymentReadRequest, PaymentRecord
from app.integrations.clinic.prototype_external import PrototypeExternalClinicAdapter
from app.services.payments import PaymentOperationError, _payment_totals, validate_allocation_total


def _root() -> Path:
    return Path(__file__).resolve().parents[2]


def _allocated_row(*, kind: str, transaction_amount: int, allocated_amount: int, reference=None):
    return SimpleNamespace(
        id=uuid4(),
        transaction_type=kind,
        amount_minor=transaction_amount,
        allocated_amount_minor=allocated_amount,
        payment_method="card",
        reference_transaction_id=reference,
    )


def test_appointment_totals_use_allocation_amount_not_full_patient_transaction() -> None:
    appointment = SimpleNamespace(price_minor=100_000)
    payment = _allocated_row(kind="payment", transaction_amount=150_000, allocated_amount=100_000)
    totals = _payment_totals(appointment=appointment, rows=[payment])
    assert totals.gross_paid_minor == 100_000
    assert totals.net_paid_minor == 100_000
    assert totals.balance_minor == 0
    assert totals.payment_status == "paid"


def test_allocation_validation_allows_unallocated_and_partial_but_never_overallocates() -> None:
    validate_allocation_total(transaction_amount_minor=150_000, allocation_amounts=[])
    validate_allocation_total(transaction_amount_minor=150_000, allocation_amounts=[100_000])
    validate_allocation_total(transaction_amount_minor=150_000, allocation_amounts=[100_000, 50_000])
    with pytest.raises(PaymentOperationError, match="cannot exceed"):
        validate_allocation_total(transaction_amount_minor=150_000, allocation_amounts=[100_000, 50_001])


def test_canonical_payment_contract_represents_unallocated_and_multi_visit_facts() -> None:
    unallocated = PaymentRecord(
        transaction_id="receipt-1",
        patient_id="patient-1",
        appointment_id=None,
        transaction_type="payment",
        amount_minor=150_000,
        currency="EGP",
        payment_method="cash",
        source="integration",
        created_at=SimpleNamespace(),
    )
    assert unallocated.appointment_id is None
    assert unallocated.allocations == ()

    allocated = PaymentRecord(
        transaction_id="receipt-2",
        patient_id="patient-1",
        appointment_id=None,
        transaction_type="payment",
        amount_minor=150_000,
        currency="EGP",
        payment_method="card",
        source="integration",
        created_at=SimpleNamespace(),
        allocations=(
            PaymentAllocationRecord(appointment_id="visit-a", amount_minor=100_000),
            PaymentAllocationRecord(appointment_id="visit-b", amount_minor=50_000),
        ),
    )
    assert sum(item.amount_minor for item in allocated.allocations) == allocated.amount_minor



def test_external_prototype_can_emit_patient_level_unallocated_payment_without_guessing_visit() -> None:
    adapter = PrototypeExternalClinicAdapter(
        workspace_timezone="Africa/Cairo",
        external_clinic_id="clinic-1",
        config={
            "prototype_dataset": {
                "Clinic Timezone": "Africa/Cairo",
                "Payments Sheet": [
                    {
                        "Payment Ref": "receipt-unallocated",
                        "Client Ref": "external-patient-1",
                        "Transaction Kind": "CHARGE",
                        "Amount": "1500.00",
                        "Currency": "EGP",
                        "Method": "Cash",
                        "Created ISO": "2026-08-26T10:00:00+03:00",
                    }
                ],
            }
        },
        resolve_patient_external_id=lambda patient_id: (
            "external-patient-1" if patient_id == "tia-patient-1" else None
        ),
    )
    result = adapter.get_patient_payments(PaymentReadRequest(patient_id="tia-patient-1"))
    assert len(result.transactions) == 1
    payment = result.transactions[0]
    assert payment.appointment_id is None
    assert payment.allocations == ()
    assert payment.amount_minor == 150_000

def test_phase62a_model_and_migration_make_appointment_link_optional_and_backfill_allocations() -> None:
    root = _root()
    model = (root / "backend/app/models/payment_transaction.py").read_text(encoding="utf-8")
    migration = (root / "backend/alembic/versions/0031_payment_allocations.py").read_text(encoding="utf-8")
    readiness = (root / "backend/app/services/operational_readiness.py").read_text(encoding="utf-8")

    assert 'class PaymentAllocation' in model
    assert '__tablename__ = "payment_allocations"' in model
    assert 'appointment_id: Mapped[UUID | None]' in model
    assert 'origin_appointment_id: Mapped[UUID | None]' in model
    assert 'revision: str = "0031_payment_allocations"' in migration
    assert 'down_revision: str | Sequence[str] | None = "0030_external_system_contract"' in migration
    assert 'INSERT INTO payment_allocations' in migration
    assert 'nullable=True' in migration
    assert 'Never guess' in migration
    assert 'EXPECTED_MIGRATION_HEAD = "0054_cancel_recovery"' in readiness


def test_appointment_money_reads_and_reschedule_use_allocation_rows() -> None:
    root = _root()
    payments = (root / "backend/app/services/payments.py").read_text(encoding="utf-8")
    analytics = (root / "backend/app/services/analytics.py").read_text(encoding="utf-8")

    assert 'select(PaymentTransaction, PaymentAllocation.amount_minor)' in payments
    assert 'PaymentAllocation.appointment_id == appointment_id' in payments
    assert 'update(PaymentAllocation)' in payments
    assert 'PaymentAllocation.amount_minor' in analytics
    assert 'group_by(PaymentAllocation.appointment_id)' in analytics


def test_phase62a_does_not_add_llm_or_lexical_financial_routing() -> None:
    source = (_root() / "backend/app/services/payments.py").read_text(encoding="utf-8").lower()
    assert "llm" not in source
    assert "generative" not in source
    assert "re.compile" not in source
    assert "re.search" not in source
