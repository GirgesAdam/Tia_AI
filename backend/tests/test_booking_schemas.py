from datetime import UTC, datetime
from uuid import uuid4

import pytest
from pydantic import ValidationError

from app.schemas.booking import AppointmentCreate, AppointmentReschedule
from app.services.booking import ceil_to_interval


def test_appointment_create_requires_timezone_aware_start() -> None:
    with pytest.raises(ValidationError):
        AppointmentCreate(
            patient_id=uuid4(),
            branch_id=uuid4(),
            doctor_id=uuid4(),
            service_id=uuid4(),
            start_at=datetime(2026, 8, 20, 18, 0),
        )


def test_appointment_create_accepts_timezone_aware_start() -> None:
    payload = AppointmentCreate(
        patient_id=uuid4(),
        branch_id=uuid4(),
        doctor_id=uuid4(),
        service_id=uuid4(),
        start_at=datetime(2026, 8, 20, 18, 0, tzinfo=UTC),
    )
    assert payload.start_at.utcoffset() is not None


def test_reschedule_requires_timezone_aware_start() -> None:
    with pytest.raises(ValidationError):
        AppointmentReschedule(start_at=datetime(2026, 8, 20, 18, 0))


def test_ceil_to_interval_uses_slot_grid() -> None:
    value = datetime(2026, 8, 20, 10, 7, tzinfo=UTC)
    rounded = ceil_to_interval(value, 15)
    assert rounded == datetime(2026, 8, 20, 10, 15, tzinfo=UTC)
