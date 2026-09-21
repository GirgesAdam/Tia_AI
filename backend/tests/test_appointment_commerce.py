from types import SimpleNamespace
from uuid import uuid4

import pytest

from app.services import appointment_commerce as commerce


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
        lambda *args, **kwargs: SimpleNamespace(net_paid_minor=0),
    )
    monkeypatch.setattr(
        commerce, "purchase_package_offer", lambda *args, **kwargs: package
    )
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
        payment_method="cash",
        external_reference=None,
        created_by_user_id=uuid4(),
        idempotency_key="appointment-package-test",
    )

    assert result is package
    assert calls == ["reserved", "consumed"]


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
        lambda *args, **kwargs: SimpleNamespace(net_paid_minor=100000),
    )

    with pytest.raises(
        commerce.AppointmentCommerceError, match="existing appointment payment"
    ):
        commerce.purchase_package_for_appointment(
            _Db(),
            workspace_id=appointment.workspace_id,
            appointment_id=appointment.id,
            offer_id=offer.id,
            payment_method="cash",
            external_reference=None,
            created_by_user_id=uuid4(),
            idempotency_key=None,
        )
