from datetime import UTC, datetime
from types import SimpleNamespace
from uuid import uuid4

import pytest

import app.services.package_offers as offers_module
import app.services.patient_packages as packages_module
from app.models.service_package_offer import PACKAGE_SESSION_COUNTS
from app.services.patient_packages import (
    PackageOperationError,
    package_read,
    validate_package_for_booking,
)


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


def test_only_three_six_and_nine_session_offers_are_supported() -> None:
    assert PACKAGE_SESSION_COUNTS == (3, 6, 9)


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
    fake_db = SimpleNamespace(
        scalar=lambda *args, **kwargs: SimpleNamespace(name="Underarm Laser", is_active=True)
    )

    offers_module.purchase_package_offer(
        fake_db,
        workspace_id=workspace_id,
        patient_id=patient_id,
        offer_id=offer.id,
        amount_paid_minor=0,
        payment_method="unknown",
        created_by_user_id=None,
        actor_type="ai",
    )

    assert captured["amount_paid_minor"] == 0
    assert captured["payment_method"] == "unknown"
    assert captured["sessions_purchased"] == 9
    assert captured["laser_device_key"] == "prime_lase"
    assert captured["standalone_session_price_minor_at_purchase"] == 25000
    assert captured["name"] == "Underarm Laser · Prime Lase · 9 sessions"


def test_package_read_exposes_payment_balance_without_affecting_sessions(monkeypatch) -> None:
    now = datetime(2026, 9, 10, tzinfo=UTC)
    package = SimpleNamespace(
        id=uuid4(),
        workspace_id=uuid4(),
        patient_id=uuid4(),
        service_id=uuid4(),
        purchase_transaction_id=uuid4(),
        package_offer_id=uuid4(),
        external_id=None,
        name="Underarm Laser · Candela Gentle · 6 sessions",
        sessions_purchased=6,
        opening_sessions_remaining=None,
        sale_price_minor=120000,
        standalone_session_price_minor_at_purchase=25000,
        laser_device_key="candela_gentle",
        laser_device_name="Candela Gentle",
        currency="EGP",
        purchased_at=now,
        expires_at=None,
        status="active",
        source="staff",
        created_at=now,
        updated_at=now,
    )
    monkeypatch.setattr(packages_module, "_usage_totals", lambda *args, **kwargs: (1, 2))
    monkeypatch.setattr(
        packages_module,
        "_package_financial_rows",
        lambda *args, **kwargs: (
            [SimpleNamespace(amount_minor=30000), SimpleNamespace(amount_minor=20000)],
            [],
        ),
    )

    result = package_read(object(), package)

    assert result.sessions_reserved == 1
    assert result.sessions_consumed == 2
    assert result.sessions_remaining == 3
    assert result.amount_paid_minor == 50000
    assert result.amount_refunded_minor == 0
    assert result.balance_due_minor == 70000
