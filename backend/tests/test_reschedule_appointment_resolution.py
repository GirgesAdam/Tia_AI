from types import SimpleNamespace
from uuid import uuid4

from app.agents.clinic_grounding import validate_grounded_entity_ids
from app.agents.turn_models import empty_entity_hints
from app.services import agent_chat


def test_grounding_accepts_only_current_patient_appointment_ids() -> None:
    hints = empty_entity_hints().model_copy(update={"appointment_id": "APT-2"})
    catalog = {
        "services": [],
        "branches": [],
        "doctors": [],
        "appointments": [{"id": "APT-1"}, {"id": "APT-2"}],
    }
    grounded = validate_grounded_entity_ids(hints, catalog)
    assert grounded.appointment_id == "APT-2"

    invalid = validate_grounded_entity_ids(
        hints.model_copy(update={"appointment_id": "OTHER-PATIENT-APT"}),
        catalog,
    )
    assert invalid.appointment_id is None


def test_active_reschedule_catalog_exposes_verified_upcoming_appointment(monkeypatch) -> None:
    patient_id = uuid4()
    record = SimpleNamespace(
        appointment_id="APT-10",
        service_id="SERVICE-OLD",
        service_name="Old service",
        doctor_id="DOCTOR-1",
        doctor_name="Doctor One",
        status="confirmed",
        timezone="Africa/Cairo",
        start_at=agent_chat.datetime.fromisoformat("2026-09-10T13:00:00+00:00"),
        end_at=agent_chat.datetime.fromisoformat("2026-09-10T13:15:00+00:00"),
    )
    adapter = SimpleNamespace(
        get_patient_appointments=lambda request: SimpleNamespace(appointments=(record,))
    )
    monkeypatch.setattr(agent_chat, "get_clinic_adapter", lambda **_: adapter)

    catalog = agent_chat._with_current_patient_appointments(
        db=SimpleNamespace(),
        workspace=SimpleNamespace(timezone="Africa/Cairo"),
        patient=SimpleNamespace(id=patient_id),
        clinic_catalog={"services": []},
    )

    assert catalog["appointments"] == [
        {
            "id": "APT-10",
            "appointment_id": "APT-10",
            "service_id": "SERVICE-OLD",
            "service_name": "Old service",
            "doctor_id": "DOCTOR-1",
            "doctor_name": "Doctor One",
            "status": "confirmed",
            "start_local": "2026-09-10T16:00:00+03:00",
            "end_local": "2026-09-10T16:15:00+03:00",
        }
    ]
