from __future__ import annotations

from types import SimpleNamespace
from uuid import uuid4

import pytest

import app.services.payments as payment_service
import app.services.pulse_billing as pulse_service
from app.services.pulse_billing import PulseBillingError


class FakeDb:
    def __init__(self, scalar_result=None):
        self.scalar_result = scalar_result
        self.added = []
        self.flush_count = 0

    def scalar(self, _statement):
        return self.scalar_result

    def add(self, value):
        self.added.append(value)

    def flush(self):
        self.flush_count += 1


def _appointment(*, pulses_used: int = 1200, billing_context: str = "standard"):
    return SimpleNamespace(
        id=uuid4(),
        workspace_id=uuid4(),
        patient_id=uuid4(),
        status="confirmed",
        billing_context=billing_context,
        patient_package_id=None,
        laser_device_key="candela_gentle",
        laser_pulses_used=pulses_used,
        currency="EGP",
        price_minor=100_000,
    )


def _stub_checkout_side_effects(monkeypatch, *, consumed: int) -> None:
    monkeypatch.setattr(
        pulse_service,
        "get_appointment_pulse_settlement",
        lambda *args, **kwargs: None,
    )
    monkeypatch.setattr(
        pulse_service,
        "_appointment_net_paid_minor",
        lambda *args, **kwargs: 0,
    )
    monkeypatch.setattr(
        pulse_service,
        "_reverse_existing_appointment_usages",
        lambda *args, **kwargs: None,
    )
    monkeypatch.setattr(
        pulse_service,
        "_consume_from_available_packs",
        lambda *args, **kwargs: consumed,
    )
    monkeypatch.setattr(
        pulse_service,
        "refresh_appointment_payment_snapshots",
        lambda *args, **kwargs: None,
    )
    monkeypatch.setattr(
        pulse_service,
        "record_activity_event",
        lambda *args, **kwargs: None,
    )


def test_checkout_uses_existing_balance_and_removes_base_service_charge(monkeypatch) -> None:
    appointment = _appointment(pulses_used=1200)
    db = FakeDb(appointment)
    _stub_checkout_side_effects(monkeypatch, consumed=1200)

    settlement = pulse_service.checkout_appointment_pulses(
        db,
        workspace_id=appointment.workspace_id,
        appointment_id=appointment.id,
        mode="use_balance",
        offer_id=None,
        changed_by_user_id=None,
        idempotency_key="checkout-balance",
    )

    assert appointment.billing_context == "pulse_prepaid"
    assert settlement.pulses_used == 1200
    assert settlement.pulses_from_balance == 1200
    assert settlement.deficit_pulses == 0
    assert settlement.resolution == "balance"


def test_checkout_consumes_old_balance_then_only_deficit_from_new_pack(monkeypatch) -> None:
    appointment = _appointment(pulses_used=1200)
    db = FakeDb(appointment)
    _stub_checkout_side_effects(monkeypatch, consumed=700)

    offer = SimpleNamespace(
        id=uuid4(),
        device_key="candela_gentle",
        pulses_count=1000,
        price_minor=250_000,
    )
    pack = SimpleNamespace(id=uuid4())
    purchase_args = {}
    monkeypatch.setattr(
        pulse_service,
        "_get_active_offer",
        lambda *args, **kwargs: offer,
    )

    def fake_purchase(*args, **kwargs):
        purchase_args.update(kwargs)
        return pack

    monkeypatch.setattr(pulse_service, "purchase_pulse_pack_offer", fake_purchase)

    settlement = pulse_service.checkout_appointment_pulses(
        db,
        workspace_id=appointment.workspace_id,
        appointment_id=appointment.id,
        mode="purchase_pack",
        offer_id=offer.id,
        changed_by_user_id=None,
        idempotency_key="checkout-pack",
    )

    usages = [row for row in db.added if row.__class__.__name__ == "PulseUsage"]
    assert len(usages) == 1
    assert usages[0].patient_pulse_pack_id == pack.id
    assert usages[0].pulses_used == 500
    assert settlement.pulses_from_balance == 1200
    assert settlement.deficit_pulses == 500
    assert settlement.resolution == "new_pack"
    assert settlement.resolution_pulse_pack_id == pack.id
    assert purchase_args["amount_paid_minor"] == 0
    assert purchase_args["origin_appointment_id"] == appointment.id


def test_checkout_overage_uses_selected_device_price(monkeypatch) -> None:
    appointment = _appointment(pulses_used=1200)
    db = FakeDb(appointment)
    _stub_checkout_side_effects(monkeypatch, consumed=700)
    captured = {}

    def fake_price(*args, **kwargs):
        captured.update(kwargs)
        return 300, "EGP"

    monkeypatch.setattr(pulse_service, "_device_overage_price", fake_price)

    settlement = pulse_service.checkout_appointment_pulses(
        db,
        workspace_id=appointment.workspace_id,
        appointment_id=appointment.id,
        mode="overage",
        offer_id=None,
        changed_by_user_id=None,
        idempotency_key="checkout-overage",
    )

    assert captured["device_key"] == "candela_gentle"
    assert settlement.deficit_pulses == 500
    assert settlement.overage_unit_price_minor == 300
    assert settlement.overage_charge_minor == 150_000
    assert settlement.resolution == "overage"


def test_checkout_rejects_switch_after_standard_payment(monkeypatch) -> None:
    appointment = _appointment()
    db = FakeDb(appointment)
    monkeypatch.setattr(
        pulse_service,
        "get_appointment_pulse_settlement",
        lambda *args, **kwargs: None,
    )
    monkeypatch.setattr(
        pulse_service,
        "_appointment_net_paid_minor",
        lambda *args, **kwargs: 10_000,
    )

    with pytest.raises(PulseBillingError, match="already has recorded payment"):
        pulse_service.checkout_appointment_pulses(
            db,
            workspace_id=appointment.workspace_id,
            appointment_id=appointment.id,
            mode="overage",
            offer_id=None,
            changed_by_user_id=None,
            idempotency_key="checkout-paid",
        )

    assert appointment.billing_context == "standard"


def test_checkout_rejects_pack_for_other_device(monkeypatch) -> None:
    appointment = _appointment(pulses_used=1200)
    db = FakeDb(appointment)
    _stub_checkout_side_effects(monkeypatch, consumed=0)
    offer = SimpleNamespace(
        id=uuid4(),
        device_key="prime_lase",
        pulses_count=2000,
        price_minor=250_000,
    )
    monkeypatch.setattr(
        pulse_service,
        "_get_active_offer",
        lambda *args, **kwargs: offer,
    )

    with pytest.raises(PulseBillingError, match="different laser device"):
        pulse_service.checkout_appointment_pulses(
            db,
            workspace_id=appointment.workspace_id,
            appointment_id=appointment.id,
            mode="purchase_pack",
            offer_id=offer.id,
            changed_by_user_id=None,
            idempotency_key="checkout-wrong-device",
        )


def test_record_payment_allocates_visit_pulse_pack_before_general_balance(monkeypatch) -> None:
    appointment = _appointment(pulses_used=0, billing_context="pulse_prepaid")
    pack = SimpleNamespace(
        id=uuid4(),
        sale_price_minor=250_000,
        purchase_transaction_id=None,
    )
    db = FakeDb()

    monkeypatch.setattr(
        payment_service,
        "require_tia_workspace_domain_write",
        lambda *args, **kwargs: None,
    )
    monkeypatch.setattr(
        payment_service,
        "_locked_appointment",
        lambda *args, **kwargs: appointment,
    )
    monkeypatch.setattr(
        payment_service,
        "_ledger_rows",
        lambda *args, **kwargs: [],
    )
    monkeypatch.setattr(
        payment_service,
        "_appointment_charge_breakdown",
        lambda *args, **kwargs: (100_000, 0, 0, 0, 250_000, 0, 250_000),
    )
    monkeypatch.setattr(
        payment_service,
        "_visit_packages",
        lambda *args, **kwargs: [],
    )
    monkeypatch.setattr(
        payment_service,
        "_visit_pulse_packs",
        lambda *args, **kwargs: [pack],
    )
    monkeypatch.setattr(
        payment_service,
        "_pulse_pack_net_paid_minor",
        lambda *args, **kwargs: 0,
    )
    monkeypatch.setattr(
        payment_service,
        "_add_single_appointment_allocation",
        lambda *args, **kwargs: None,
    )
    monkeypatch.setattr(
        payment_service,
        "sync_appointment_payment_snapshot",
        lambda *args, **kwargs: None,
    )
    monkeypatch.setattr(
        payment_service,
        "record_activity_event",
        lambda *args, **kwargs: None,
    )

    transaction = payment_service.record_payment(
        db,
        workspace_id=appointment.workspace_id,
        appointment_id=appointment.id,
        amount_minor=250_000,
        payment_method="cash",
        created_by_user_id=None,
        source="staff",
    )

    assert transaction.patient_pulse_pack_id == pack.id
    assert transaction.patient_package_id is None
    assert transaction.amount_minor == 250_000
    assert transaction.reason == "Pulse pack payment from appointment checkout"


def test_device_pricing_migration_contract() -> None:
    from pathlib import Path

    root = Path(__file__).resolve().parents[1]
    migration = (
        root / "alembic/versions/0083_pulse_device_pricing_checkout.py"
    ).read_text(encoding="utf-8")
    model = (root / "app/models/pulse_billing.py").read_text(encoding="utf-8")

    assert 'revision: str = "0083_pulse_device_pricing"' in migration
    assert 'down_revision: str | Sequence[str] | None = "0082_pulse_wallet_billing"' in migration
    assert "uq_pulse_billing_settings_workspace_device" in migration
    assert "device_key" in migration
    assert "uq_pulse_billing_settings_workspace_device" in model
