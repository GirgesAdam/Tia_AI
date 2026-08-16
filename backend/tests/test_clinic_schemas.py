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
