from datetime import time

import pytest
from pydantic import ValidationError

from app.schemas.clinic import ServiceCreate, WorkingHourInterval


def test_service_rejects_float_style_negative_price() -> None:
    with pytest.raises(ValidationError):
        ServiceCreate(name="Laser", slug="laser", duration_minutes=30, price_minor=-1)


def test_working_hours_require_end_after_start() -> None:
    with pytest.raises(ValidationError):
        WorkingHourInterval(weekday=0, start_time=time(18, 0), end_time=time(17, 0))


def test_working_hours_reject_overlap() -> None:
    from app.schemas.clinic import WorkingHoursReplace

    with pytest.raises(ValidationError):
        WorkingHoursReplace(
            intervals=[
                WorkingHourInterval(weekday=0, start_time=time(10, 0), end_time=time(14, 0)),
                WorkingHourInterval(weekday=0, start_time=time(13, 0), end_time=time(18, 0)),
            ]
        )



def test_service_keeps_legacy_category_and_derives_operational_category() -> None:
    service = ServiceCreate(
        name="Hydrafacial",
        slug="hydrafacial",
        category="Facial",
        duration_minutes=45,
        price_minor=180_000,
    )
    assert service.category == "Facial"
    assert service.operational_category == "dermatology"


def test_laser_device_service_is_always_operationally_laser() -> None:
    service = ServiceCreate(
        name="Full Body",
        slug="full-body",
        category="Laser Hair Removal",
        operational_category="dermatology",
        duration_minutes=60,
        price_minor=0,
        requires_laser_device=True,
    )
    assert service.category == "Laser Hair Removal"
    assert service.operational_category == "laser"
