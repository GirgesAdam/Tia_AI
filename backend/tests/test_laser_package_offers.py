from datetime import UTC, datetime
from types import SimpleNamespace
from uuid import uuid4

import pytest

import app.services.package_offers as offers_module
import app.services.patient_packages as packages_module
from app.services.patient_packages import PackageOperationError, validate_package_for_booking


def _package(*, device_key: str | None = "candela_gentle") -> SimpleNamespace:
    return SimpleNamespace(
        id=uuid4(),
        workspace_id=uuid4(),
        patient_id=uuid4(),
        service_id=uuid4(),
        laser_device_key=device_key,
        status="active",
        expires_at=None,
        purchased_at=datetime(2026, 9, 1, tzinfo=UTC),
        sessions_purchased=6,
    )


def test_device_specific_package_requires_matching_laser_device(monkeypatch) -> None:
    package = _package(device_key="candela_gentle")
    monkeypatch.setattr(packages_module, "_locked_package", lambda *args, **kwargs: package)
    monkeypatch.setattr(packages_module, "_usage_totals", lambda *args, **kwargs: (0, 1))

    with pytest.raises(PackageOperationError, match="different laser device"):
        validate_package_for_booking(
            object(),
            workspace_id=package.workspace_id,
            package_id=package.id,
            patient_id=package.patient_id,
            service_id=package.service_id,
            appointment_start_at=datetime(2026, 9, 12, tzinfo=UTC),
            laser_device_key="prime_lase",
        )

    assert (
        validate_package_for_booking(
            object(),
            workspace_id=package.workspace_id,
            package_id=package.id,
            patient_id=package.patient_id,
            service_id=package.service_id,
            appointment_start_at=datetime(2026, 9, 12, tzinfo=UTC),
            laser_device_key="candela_gentle",
        )
        is package
    )


def test_legacy_service_package_without_device_remains_compatible(monkeypatch) -> None:
    package = _package(device_key=None)
    monkeypatch.setattr(packages_module, "_locked_package", lambda *args, **kwargs: package)
    monkeypatch.setattr(packages_module, "_usage_totals", lambda *args, **kwargs: (0, 0))

    assert (
        validate_package_for_booking(
            object(),
            workspace_id=package.workspace_id,
            package_id=package.id,
            patient_id=package.patient_id,
            service_id=package.service_id,
            appointment_start_at=datetime(2026, 9, 12, tzinfo=UTC),
            laser_device_key="prime_lase",
        )
        is package
    )


def test_package_entitlement_does_not_depend_on_amount_paid(monkeypatch) -> None:
    package = _package()
    # No payment fields are needed by entitlement validation at all.
    monkeypatch.setattr(packages_module, "_locked_package", lambda *args, **kwargs: package)
    monkeypatch.setattr(packages_module, "_usage_totals", lambda *args, **kwargs: (1, 2))

    result = validate_package_for_booking(
        object(),
        workspace_id=package.workspace_id,
        package_id=package.id,
        patient_id=package.patient_id,
        service_id=package.service_id,
        appointment_start_at=datetime(2026, 9, 12, tzinfo=UTC),
        laser_device_key="candela_gentle",
    )
    assert result is package


def test_purchase_offer_allows_zero_initial_payment(monkeypatch) -> None:
    workspace_id = uuid4()
    patient_id = uuid4()
    offer = SimpleNamespace(
        id=uuid4(),
        workspace_id=workspace_id,
        service_id=uuid4(),
        sessions_count=9,
        price_minor=180000,
        device_key="prime_lase",
        device_name="Prime Lase",
    )
    monkeypatch.setattr(
        offers_module,
        "get_active_package_offer",
        lambda *args, **kwargs: offer,
    )
    monkeypatch.setattr(
        offers_module,
        "configured_device_price",
        lambda *args, **kwargs: SimpleNamespace(price_minor=25000),
    )
    captured = {}

    def fake_create_patient_package(*args, **kwargs):
        captured.update(kwargs)
        return SimpleNamespace(id=uuid4())

    monkeypatch.setattr(offers_module, "create_patient_package", fake_create_patient_package)

    offers_module.purchase_package_offer(
        object(),
        workspace_id=workspace_id,
        patient_id=patient_id,
        offer_id=offer.id,
        amount_paid_minor=0,
        payment_method="unknown",
        created_by_user_id=None,
        actor_type="staff",
    )

    assert captured["amount_paid_minor"] == 0
    assert captured["payment_method"] == "unknown"
    assert captured["sessions_purchased"] == 9
    assert captured["laser_device_key"] == "prime_lase"
    assert captured["standalone_session_price_minor_at_purchase"] == 25000
