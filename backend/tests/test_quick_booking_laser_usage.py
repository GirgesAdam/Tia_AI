from __future__ import annotations

from datetime import UTC, datetime, timedelta
from pathlib import Path
from uuid import uuid4

import pytest

from app.schemas.booking import AppointmentLaserUsageUpdate, QuickAppointmentCreate
from app.services.booking import _candidate_start_times


def _root() -> Path:
    return Path(__file__).resolve().parents[2]


def test_back_to_back_candidate_includes_exact_previous_end_between_grid_boundaries() -> None:
    start = datetime(2026, 9, 22, 10, 0, tzinfo=UTC)
    end = datetime(2026, 9, 22, 12, 0, tzinfo=UTC)
    previous_end = start + timedelta(minutes=37)
    candidates = _candidate_start_times(
        interval_start=start,
        interval_end=end,
        interval_minutes=15,
        release_times=[previous_end],
    )
    assert previous_end in candidates
    assert start + timedelta(minutes=45) in candidates


def test_quick_booking_and_laser_usage_schemas_validate_staff_input() -> None:
    payload = QuickAppointmentCreate(
        patient_id=uuid4(),
        branch_id=uuid4(),
        doctor_id=uuid4(),
        service_id=uuid4(),
        start_at=datetime(2026, 9, 22, 17, 43, tzinfo=UTC),
        laser_device_key="prime_lase",
    )
    assert payload.start_at.minute == 43
    assert AppointmentLaserUsageUpdate(pulses_used=2350).pulses_used == 2350
    with pytest.raises(ValueError):
        AppointmentLaserUsageUpdate(pulses_used=-1)


def test_quick_booking_backend_is_an_audited_override() -> None:
    root = _root()
    route = (root / "backend/app/api/routes/booking.py").read_text(encoding="utf-8")
    model = (root / "backend/app/models/appointment.py").read_text(encoding="utf-8")
    migration = (root / "backend/alembic/versions/0079_quick_booking_laser_usage.py").read_text(encoding="utf-8")
    assert '@router.post(\n    "/appointments/quick"' in route
    assert "is_quick_booking=True" in route
    assert "doctor_assignment_known=True" in route
    assert 'action="appointment.quick_created"' in route
    assert "NOT is_quick_booking" in model
    assert "NOT is_quick_booking" in migration


def test_quick_popup_closes_after_success_and_allows_minute_precision() -> None:
    root = _root()
    form = (root / "frontend/src/app/(dashboard)/appointments/manual-appointment-form.tsx").read_text(encoding="utf-8")
    dialog = (root / "frontend/src/app/(dashboard)/appointments/quick-appointment-dialog.tsx").read_text(encoding="utf-8")
    actions = (root / "frontend/src/app/(dashboard)/appointments/actions.ts").read_text(encoding="utf-8")
    assert "router.replace(successHref)" in form
    assert 'schedulingMode={column === "quick" ? "quick" : "standard"}' in dialog
    assert 'type="time"' in form
    assert 'step="60"' in form
    assert '"/booking/appointments/quick"' in actions


def test_laser_pulses_are_tracking_only_on_appointment_detail() -> None:
    root = _root()
    detail = (root / "frontend/src/app/(dashboard)/appointments/[appointmentId]/page.tsx").read_text(encoding="utf-8")
    actions = (root / "frontend/src/app/(dashboard)/appointments/[appointmentId]/actions.ts").read_text(encoding="utf-8")
    route = (root / "backend/app/api/routes/booking.py").read_text(encoding="utf-8")
    assert "عدد الـ Pulses المستخدمة" in detail
    assert "لا يغيّر سعر الجلسة أو مدتها" in detail
    assert "/laser-usage" in actions
    assert "appointment.laser_usage_updated" in route
