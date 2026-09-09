from datetime import UTC, datetime, timedelta
from types import SimpleNamespace
from uuid import uuid4

import pytest

from app.services import staff_appointment_edits as edits
from app.services.booking import SlotCandidate


class _Db:
    def __init__(self) -> None:
        self.flush_count = 0

    def flush(self) -> None:
        self.flush_count += 1


def _appointment(*, service_id, package_backed: bool = True):
    start = datetime.now(UTC) + timedelta(days=2)
    return SimpleNamespace(
        id=uuid4(),
        workspace_id=uuid4(),
        status="confirmed",
        branch_id=uuid4(),
        doctor_id=uuid4(),
        service_id=service_id,
        start_at=start,
        end_at=start + timedelta(minutes=30),
        busy_start_at=start,
        busy_end_at=start + timedelta(minutes=30),
        duration_minutes=30,
        price_minor=100_000,
        currency="EGP",
        laser_device_key="candela_gentle" if package_backed else None,
        laser_device_name="Candela Gentle" if package_backed else None,
        patient_package_id=uuid4() if package_backed else None,
        billing_context="package_prepaid" if package_backed else "standard",
        package_external_id="PKG-1" if package_backed else None,
    )


def test_staff_service_change_releases_old_package_and_reprices(monkeypatch) -> None:
    old_service_id = uuid4()
    new_service_id = uuid4()
    appointment = _appointment(service_id=old_service_id, package_backed=True)
    workspace = SimpleNamespace(id=appointment.workspace_id)
    db = _Db()
    new_slot = SlotCandidate(
        branch_id=appointment.branch_id,
        doctor_id=appointment.doctor_id,
        service_id=new_service_id,
        start_at=appointment.start_at,
        end_at=appointment.start_at + timedelta(minutes=60),
        busy_start_at=appointment.start_at,
        busy_end_at=appointment.start_at + timedelta(minutes=60),
        duration_minutes=60,
        price_minor=250_000,
        currency="EGP",
        laser_device_key=None,
        laser_device_name=None,
    )
    released: list[str] = []
    refreshed: list[set] = []

    monkeypatch.setattr(edits, "_locked_appointment", lambda *args, **kwargs: appointment)
    monkeypatch.setattr(
        edits,
        "_validated_slot_for_existing_appointment",
        lambda *args, **kwargs: new_slot,
    )
    monkeypatch.setattr(
        edits,
        "release_package_usage",
        lambda *args, **kwargs: released.append(kwargs["reason"]),
    )
    monkeypatch.setattr(
        edits,
        "refresh_appointment_payment_snapshots",
        lambda *args, **kwargs: refreshed.append(kwargs["appointment_ids"]),
    )
    monkeypatch.setattr(edits, "record_activity_event", lambda *args, **kwargs: None)

    result = edits.change_appointment_service(
        db,
        workspace=workspace,
        appointment_id=appointment.id,
        service_id=new_service_id,
        laser_device_key=None,
        changed_by_user_id=uuid4(),
    )

    assert result is appointment
    assert appointment.service_id == new_service_id
    assert appointment.duration_minutes == 60
    assert appointment.price_minor == 250_000
    assert appointment.patient_package_id is None
    assert appointment.billing_context == "standard"
    assert appointment.package_external_id is None
    assert released == ["staff_service_changed"]
    assert refreshed == [{appointment.id}]


def test_staff_device_change_releases_incompatible_device_package(monkeypatch) -> None:
    service_id = uuid4()
    appointment = _appointment(service_id=service_id, package_backed=True)
    workspace = SimpleNamespace(id=appointment.workspace_id)
    db = _Db()
    db.scalar = lambda _stmt: SimpleNamespace(laser_device_key="candela_gentle")
    new_slot = SlotCandidate(
        branch_id=appointment.branch_id,
        doctor_id=appointment.doctor_id,
        service_id=service_id,
        start_at=appointment.start_at,
        end_at=appointment.end_at,
        busy_start_at=appointment.busy_start_at,
        busy_end_at=appointment.busy_end_at,
        duration_minutes=appointment.duration_minutes,
        price_minor=120_000,
        currency="EGP",
        laser_device_key="prime_lase",
        laser_device_name="Prime Lase",
    )
    released: list[str] = []

    monkeypatch.setattr(edits, "_locked_appointment", lambda *args, **kwargs: appointment)
    monkeypatch.setattr(
        edits,
        "_validated_slot_for_existing_appointment",
        lambda *args, **kwargs: new_slot,
    )
    monkeypatch.setattr(
        edits,
        "release_package_usage",
        lambda *args, **kwargs: released.append(kwargs["reason"]),
    )
    monkeypatch.setattr(
        edits,
        "refresh_appointment_payment_snapshots",
        lambda *args, **kwargs: None,
    )
    monkeypatch.setattr(edits, "record_activity_event", lambda *args, **kwargs: None)

    edits.change_appointment_service(
        db,
        workspace=workspace,
        appointment_id=appointment.id,
        service_id=service_id,
        laser_device_key="prime_lase",
        changed_by_user_id=uuid4(),
    )

    assert appointment.patient_package_id is None
    assert appointment.billing_context == "standard"
    assert appointment.package_external_id is None
    assert appointment.laser_device_key == "prime_lase"
    assert released == ["staff_laser_device_changed"]


def test_completed_appointment_service_cannot_be_rewritten(monkeypatch) -> None:
    service_id = uuid4()
    appointment = _appointment(service_id=service_id, package_backed=False)
    appointment.status = "completed"
    monkeypatch.setattr(edits, "_locked_appointment", lambda *args, **kwargs: appointment)

    with pytest.raises(edits.StaffAppointmentEditError, match="pending, confirmed"):
        edits.change_appointment_service(
            _Db(),
            workspace=SimpleNamespace(id=appointment.workspace_id),
            appointment_id=appointment.id,
            service_id=uuid4(),
            laser_device_key=None,
            changed_by_user_id=uuid4(),
        )
