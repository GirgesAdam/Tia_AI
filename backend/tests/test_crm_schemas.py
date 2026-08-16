import pytest
from pydantic import ValidationError

from app.schemas.crm import MessageCreate, PatientCreate, normalize_phone


def test_phone_normalization_accepts_common_formatting() -> None:
    display, normalized = normalize_phone("+20 100-123-4567")
    assert display == "+20 100-123-4567"
    assert normalized == "+201001234567"


def test_patient_rejects_invalid_phone() -> None:
    with pytest.raises(ValidationError):
        PatientCreate(first_name="Adam", phone="abc")


def test_patient_message_must_be_inbound() -> None:
    with pytest.raises(ValidationError):
        MessageCreate(
            sender_type="patient",
            direction="outbound",
            content="Hello",
        )


def test_text_message_requires_content() -> None:
    with pytest.raises(ValidationError):
        MessageCreate(sender_type="staff", direction="outbound", content="   ")
