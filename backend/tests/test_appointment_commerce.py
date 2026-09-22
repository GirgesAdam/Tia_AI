from types import SimpleNamespace
from uuid import uuid4

import pytest

from app.services import appointment_commerce as commerce
from app.services import payments as payment_service


class _Db:
    def scalar(self, _stmt):
        return None


def _appointment(*, status: str = "confirmed"):
    return SimpleNamespace(
        id=uuid4(),
        workspace_id=uuid4(),
        patient_id=uuid4(),
        service_id=uuid4(),
        patient_package_id=None,
        laser_device_key="candela_gentle",
        price_minor=100000,
        status=status,
    )


def test_package_purchase_from_completed_appointment_consumes_first_session(
    monkeypatch,
) -> None:
    appointment = _appointment(status="completed")
    offer = SimpleNamespace(
        id=uuid4(),
        service_id=appointment.service_id,
        device_key=appointment.laser_device_key,
        price_minor=480000,
    )
    package = SimpleNamespace(id=uuid4())
    calls: list[str] = []

    monkeypatch.setattr(
        commerce, "_locked_appointment", lambda *args, **kwargs: appointment
    )
    monkeypatch.setattr(
        commerce, "get_active_package_offer", lambda *args, **kwargs: offer
    )
    monkeypatch.setattr(
        commerce,
        "get_appointment_payment_summary",
        lambda *args, **kwargs: SimpleNamespace(net_paid_minor=0, price_minor=100000),
    )
    purchase_kwargs: dict[str, object] = {}

    def _purchase(*args, **kwargs):
        purchase_kwargs.update(kwargs)
        return package

    monkeypatch.setattr(commerce, "purchase_package_offer", _purchase)
    monkeypatch.setattr(
        commerce,
        "reserve_package_usage",
        lambda *args, **kwargs: calls.append("reserved"),
    )
    monkeypatch.setattr(
        commerce,
        "consume_package_usage",
        lambda *args, **kwargs: calls.append("consumed"),
    )
    monkeypatch.setattr(
        commerce, "refresh_appointment_payment_snapshots", lambda *args, **kwargs: None
    )
    monkeypatch.setattr(
        commerce, "record_activity_event", lambda *args, **kwargs: None
    )

    result = commerce.purchase_package_for_appointment(
        _Db(),
        workspace_id=appointment.workspace_id,
        appointment_id=appointment.id,
        offer_id=offer.id,
        created_by_user_id=uuid4(),
        idempotency_key="appointment-package-test",
    )

    assert result is package
    assert calls == ["reserved", "consumed"]
    assert purchase_kwargs["amount_paid_minor"] == 0
    assert purchase_kwargs["payment_method"] == "unknown"
    assert purchase_kwargs["origin_appointment_id"] == appointment.id


def test_package_conversion_rejects_existing_appointment_payment(
    monkeypatch,
) -> None:
    appointment = _appointment()
    offer = SimpleNamespace(
        id=uuid4(),
        service_id=appointment.service_id,
        device_key=appointment.laser_device_key,
        price_minor=480000,
    )
    monkeypatch.setattr(
        commerce, "_locked_appointment", lambda *args, **kwargs: appointment
    )
    monkeypatch.setattr(
        commerce, "get_active_package_offer", lambda *args, **kwargs: offer
    )
    monkeypatch.setattr(
        commerce,
        "get_appointment_payment_summary",
        lambda *args, **kwargs: SimpleNamespace(net_paid_minor=100000, price_minor=100000),
    )

    with pytest.raises(
        commerce.AppointmentCommerceError, match="payment already applied to this service"
    ):
        commerce.purchase_package_for_appointment(
            _Db(),
            workspace_id=appointment.workspace_id,
            appointment_id=appointment.id,
            offer_id=offer.id,
            created_by_user_id=uuid4(),
            idempotency_key=None,
        )


def test_additional_service_package_is_added_unpaid_and_consumed_when_visit_completed(
    monkeypatch,
) -> None:
    appointment = _appointment(status="completed")
    line = SimpleNamespace(
        id=uuid4(),
        service_id=uuid4(),
        laser_device_key="candela_gentle",
        patient_package_id=None,
        unit_price_minor=100000,
    )
    offer = SimpleNamespace(
        id=uuid4(),
        service_id=line.service_id,
        device_key=line.laser_device_key,
        price_minor=350000,
    )
    package = SimpleNamespace(id=uuid4())
    calls: list[str] = []
    purchase_kwargs: dict[str, object] = {}

    class _LineDb:
        def scalar(self, _stmt):
            return line

    monkeypatch.setattr(
        commerce, "_locked_appointment", lambda *args, **kwargs: appointment
    )
    monkeypatch.setattr(
        commerce,
        "get_appointment_payment_summary",
        lambda *args, **kwargs: SimpleNamespace(net_paid_minor=0, price_minor=100000),
    )
    monkeypatch.setattr(
        commerce, "get_active_package_offer", lambda *args, **kwargs: offer
    )

    def _purchase(*args, **kwargs):
        purchase_kwargs.update(kwargs)
        return package

    monkeypatch.setattr(commerce, "purchase_package_offer", _purchase)
    monkeypatch.setattr(
        commerce,
        "reserve_additional_service_package_usage",
        lambda *args, **kwargs: calls.append("reserved"),
    )
    monkeypatch.setattr(
        commerce,
        "consume_visit_package_usages",
        lambda *args, **kwargs: calls.append("consumed"),
    )
    monkeypatch.setattr(
        commerce, "refresh_appointment_payment_snapshots", lambda *args, **kwargs: None
    )
    monkeypatch.setattr(
        commerce, "record_activity_event", lambda *args, **kwargs: None
    )

    result = commerce.purchase_package_for_additional_service(
        _LineDb(),
        workspace_id=appointment.workspace_id,
        appointment_id=appointment.id,
        line_id=line.id,
        offer_id=offer.id,
        created_by_user_id=uuid4(),
        idempotency_key="extra-package-test",
    )

    assert result is package
    assert calls == ["reserved", "consumed"]
    assert purchase_kwargs["amount_paid_minor"] == 0
    assert purchase_kwargs["payment_method"] == "unknown"
    assert purchase_kwargs["origin_appointment_id"] == appointment.id




def test_primary_package_conversion_allows_payments_that_only_cover_other_visit_items(
    monkeypatch,
) -> None:
    appointment = _appointment()
    appointment.price_minor = 100000
    offer = SimpleNamespace(
        id=uuid4(),
        service_id=appointment.service_id,
        device_key=appointment.laser_device_key,
        price_minor=480000,
    )
    package = SimpleNamespace(id=uuid4())
    monkeypatch.setattr(
        commerce, "_locked_appointment", lambda *args, **kwargs: appointment
    )
    monkeypatch.setattr(
        commerce, "get_active_package_offer", lambda *args, **kwargs: offer
    )
    monkeypatch.setattr(
        commerce,
        "get_appointment_payment_summary",
        lambda *args, **kwargs: SimpleNamespace(
            net_paid_minor=50000,
            price_minor=150000,
        ),
    )
    monkeypatch.setattr(
        commerce, "purchase_package_offer", lambda *args, **kwargs: package
    )
    monkeypatch.setattr(
        commerce, "reserve_package_usage", lambda *args, **kwargs: None
    )
    monkeypatch.setattr(
        commerce, "refresh_appointment_payment_snapshots", lambda *args, **kwargs: None
    )
    monkeypatch.setattr(
        commerce, "record_activity_event", lambda *args, **kwargs: None
    )

    result = commerce.purchase_package_for_appointment(
        _Db(),
        workspace_id=appointment.workspace_id,
        appointment_id=appointment.id,
        offer_id=offer.id,
        created_by_user_id=uuid4(),
        idempotency_key="primary-package-other-charge-paid",
    )

    assert result is package


def test_additional_service_package_allows_original_appointment_to_be_paid(
    monkeypatch,
) -> None:
    appointment = _appointment()
    line = SimpleNamespace(
        id=uuid4(),
        service_id=uuid4(),
        laser_device_key="candela_gentle",
        patient_package_id=None,
        unit_price_minor=100000,
    )
    offer = SimpleNamespace(
        id=uuid4(),
        service_id=line.service_id,
        device_key=line.laser_device_key,
        price_minor=350000,
    )
    package = SimpleNamespace(id=uuid4())

    class _LineDb:
        def scalar(self, _stmt):
            return line

    monkeypatch.setattr(
        commerce, "_locked_appointment", lambda *args, **kwargs: appointment
    )
    monkeypatch.setattr(
        commerce,
        "get_appointment_payment_summary",
        lambda *args, **kwargs: SimpleNamespace(
            net_paid_minor=100000,
            price_minor=200000,
        ),
    )
    monkeypatch.setattr(
        commerce, "get_active_package_offer", lambda *args, **kwargs: offer
    )
    monkeypatch.setattr(
        commerce, "purchase_package_offer", lambda *args, **kwargs: package
    )
    monkeypatch.setattr(
        commerce,
        "reserve_additional_service_package_usage",
        lambda *args, **kwargs: None,
    )
    monkeypatch.setattr(
        commerce, "refresh_appointment_payment_snapshots", lambda *args, **kwargs: None
    )
    monkeypatch.setattr(
        commerce, "record_activity_event", lambda *args, **kwargs: None
    )

    result = commerce.purchase_package_for_additional_service(
        _LineDb(),
        workspace_id=appointment.workspace_id,
        appointment_id=appointment.id,
        line_id=line.id,
        offer_id=offer.id,
        created_by_user_id=uuid4(),
        idempotency_key="extra-package-primary-paid",
    )

    assert result is package


def test_additional_service_package_rejects_when_that_line_was_already_paid(
    monkeypatch,
) -> None:
    appointment = _appointment()
    line = SimpleNamespace(
        id=uuid4(),
        service_id=uuid4(),
        laser_device_key="candela_gentle",
        patient_package_id=None,
        unit_price_minor=100000,
    )
    offer = SimpleNamespace(
        id=uuid4(),
        service_id=line.service_id,
        device_key=line.laser_device_key,
        price_minor=350000,
    )

    class _LineDb:
        def scalar(self, _stmt):
            return line

    monkeypatch.setattr(
        commerce, "_locked_appointment", lambda *args, **kwargs: appointment
    )
    monkeypatch.setattr(
        commerce,
        "get_appointment_payment_summary",
        lambda *args, **kwargs: SimpleNamespace(
            net_paid_minor=150000,
            price_minor=200000,
        ),
    )
    monkeypatch.setattr(
        commerce, "get_active_package_offer", lambda *args, **kwargs: offer
    )

    with pytest.raises(
        commerce.AppointmentCommerceError,
        match="payment already applied to this additional service",
    ):
        commerce.purchase_package_for_additional_service(
            _LineDb(),
            workspace_id=appointment.workspace_id,
            appointment_id=appointment.id,
            line_id=line.id,
            offer_id=offer.id,
            created_by_user_id=uuid4(),
            idempotency_key=None,
        )


class _ChargeDb:
    def __init__(self, values):
        self.values = iter(values)

    def scalar(self, _stmt):
        return next(self.values)


def test_package_bought_from_visit_replaces_session_price_and_becomes_due() -> None:
    appointment = SimpleNamespace(
        id=uuid4(),
        price_minor=100000,
        billing_context="package_prepaid",
    )
    breakdown = payment_service._appointment_charge_breakdown(
        _ChargeDb([0, 0, 480000]),
        workspace_id=uuid4(),
        appointment=appointment,
    )

    assert breakdown == (100000, 0, 0, 480000, 480000)


def test_additional_service_package_replaces_extra_service_price_but_keeps_primary_due() -> None:
    appointment = SimpleNamespace(
        id=uuid4(),
        price_minor=100000,
        billing_context="standard",
    )
    breakdown = payment_service._appointment_charge_breakdown(
        _ChargeDb([0, 0, 350000]),
        workspace_id=uuid4(),
        appointment=appointment,
    )

    assert breakdown == (100000, 0, 0, 350000, 450000)
