from pathlib import Path
from types import SimpleNamespace

import pytest
from pydantic import ValidationError

from app.schemas.clinic import DoctorServiceAssignment
from app.services.booking import service_duration_minutes


def test_duration_is_service_owned_not_doctor_owned() -> None:
    service = SimpleNamespace(duration_minutes=60)
    assert service_duration_minutes(service) == 60


def test_doctor_service_write_rejects_custom_duration_override() -> None:
    with pytest.raises(ValidationError):
        DoctorServiceAssignment(custom_duration_minutes=45)


def test_doctor_service_write_still_accepts_null_duration_for_old_clients() -> None:
    payload = DoctorServiceAssignment(custom_duration_minutes=None, custom_price_minor=150000)
    assert payload.custom_duration_minutes is None
    assert payload.custom_price_minor == 150000


def test_realistic_fixture_clears_legacy_doctor_duration_overrides() -> None:
    source = (
        Path(__file__).resolve().parents[1]
        / "scripts"
        / "seed_realistic_aesthetic_clinic.py"
    ).read_text(encoding="utf-8")
    assert '"custom_duration_minutes": None' in source
    assert '"laser-hair-removal": {"duration": 40' not in source


def test_realistic_fixture_full_body_is_one_hour_and_underarm_is_15_minutes() -> None:
    source = (
        Path(__file__).resolve().parents[1]
        / "scripts"
        / "seed_realistic_aesthetic_clinic.py"
    ).read_text(encoding="utf-8")
    full_body = source.index('"key": "laser-hair-full-body-women"')
    underarm = source.index('"key": "laser-hair-underarm"')
    assert '"duration": 60' in source[full_body : full_body + 700]
    assert '"duration": 15' in source[underarm : underarm + 700]
