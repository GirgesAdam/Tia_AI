from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def replace(path: str, old: str, new: str) -> None:
    target = ROOT / path
    text = target.read_text(encoding="utf-8")
    if old not in text:
        raise RuntimeError(f"Expected patch fragment not found in {path}: {old[:160]!r}")
    target.write_text(text.replace(old, new, 1), encoding="utf-8")


# 1) Let the semantic interpreter return a canonical existing appointment ID.
replace(
    "backend/app/agents/turn_models.py",
    '''    doctor_candidate_ids: list[str] = Field(\n        default_factory=list,\n        description="All plausible doctor UUIDs when no single doctor is selected.",\n    )\n    requested_date: str | None = Field(\n''',
    '''    doctor_candidate_ids: list[str] = Field(\n        default_factory=list,\n        description="All plausible doctor UUIDs when no single doctor is selected.",\n    )\n    appointment_id: str | None = Field(\n        default=None,\n        description=(\n            "Canonical ID of the EXISTING appointment being acted on, selected only from the "\n            "supplied current-patient appointment catalog. In a reschedule flow this identifies "\n            "the old appointment; replacement date/time/service belong in the other fields."\n        ),\n    )\n    requested_date: str | None = Field(\n''',
)

replace(
    "backend/app/agents/turn_models.py",
    '''    "appointment_reference",\n]\n''',
    '''    "appointment_reference",\n    "appointment_id",\n]\n''',
)

# 2) Validate appointment IDs against the current patient's supplied appointment rows.
replace(
    "backend/app/agents/clinic_grounding.py",
    '''    doctor_ids = _catalog_ids(catalog, "doctors")\n\n    raw_service_id = getattr(entity_hints, "service_id", None)\n''',
    '''    doctor_ids = _catalog_ids(catalog, "doctors")\n    appointment_ids = _catalog_ids(catalog, "appointments")\n\n    raw_service_id = getattr(entity_hints, "service_id", None)\n''',
)
replace(
    "backend/app/agents/clinic_grounding.py",
    '''    doctor_candidate_ids = _valid_ids(\n        getattr(entity_hints, "doctor_candidate_ids", []), doctor_ids\n    )\n\n    doctor_row = _catalog_row_by_id(catalog, "doctors", doctor_id)\n''',
    '''    doctor_candidate_ids = _valid_ids(\n        getattr(entity_hints, "doctor_candidate_ids", []), doctor_ids\n    )\n    appointment_id = _valid_id(\n        getattr(entity_hints, "appointment_id", None), appointment_ids\n    )\n\n    doctor_row = _catalog_row_by_id(catalog, "doctors", doctor_id)\n''',
)
replace(
    "backend/app/agents/clinic_grounding.py",
    '''            "doctor_id": doctor_id,\n            "doctor_candidate_ids": doctor_candidate_ids,\n        }\n    )\n''',
    '''            "doctor_id": doctor_id,\n            "doctor_candidate_ids": doctor_candidate_ids,\n            "appointment_id": appointment_id,\n        }\n    )\n''',
)

# 3) Tell the existing single LLM interpreter how to ground an existing appointment.
replace(
    "backend/app/agents/turn_interpreter.py",
    '''        "GROUNDING: resolve service and doctor only against the supplied PostgreSQL clinic catalog. "\n''',
    '''        "GROUNDING: resolve service, doctor, and any existing appointment only against the supplied "\n        "canonical clinic catalog. "\n''',
)
replace(
    "backend/app/agents/turn_interpreter.py",
    '''        "When both a doctor and service are mentioned, respect their canonical compatibility relationships. "\n        "Emit a canonical ID only when one record is clearly intended; otherwise emit all plausible candidate "\n''',
    '''        "When both a doctor and service are mentioned, respect their canonical compatibility relationships. "\n        "When current-patient appointments are supplied and a reschedule turn clearly identifies one existing "\n        "appointment from its displayed date/time/service/doctor, set appointment_id to that exact catalog ID; "\n        "appointment_reference may still describe it in customer-facing terms. Never use the replacement target "\n        "date/time/service to choose the existing appointment. "\n        "Emit a canonical ID only when one record is clearly intended; otherwise emit all plausible candidate "\n''',
)
replace(
    "backend/app/agents/turn_interpreter.py",
    '''            "reschedule flow, appointment_reference identifies the existing appointment being changed, while "\n            "requested_date and requested_start_time are the replacement target.\\n\\n"\n''',
    '''            "reschedule flow, appointment_id is the canonical existing appointment when one supplied appointment "\n            "is clearly identified; appointment_reference is its customer-facing description, while requested_date "\n            "and requested_start_time are the replacement target.\\n\\n"\n''',
)

# 4) During an active reschedule only, attach verified upcoming appointments from the clinic adapter.
replace(
    "backend/app/services/agent_chat.py",
    '''from app.core.config import settings\nfrom app.models.agent_action import AgentAction\n''',
    '''from app.core.config import settings\nfrom app.integrations.clinic.base import AppointmentReadRequest\nfrom app.integrations.clinic.registry import get_clinic_adapter\nfrom app.models.agent_action import AgentAction\n''',
)
replace(
    "backend/app/services/agent_chat.py",
    '''def _workspace_clock(workspace: Workspace) -> tuple[str, datetime]:\n    timezone_name = (workspace.timezone or "Africa/Cairo").strip()\n    try:\n        tz = ZoneInfo(timezone_name)\n    except ZoneInfoNotFoundError:\n        timezone_name = "Africa/Cairo"\n        tz = ZoneInfo(timezone_name)\n    return timezone_name, datetime.now(tz)\n\ndef _uuid_from_metadata(value: object) -> UUID | None:\n''',
    '''def _workspace_clock(workspace: Workspace) -> tuple[str, datetime]:\n    timezone_name = (workspace.timezone or "Africa/Cairo").strip()\n    try:\n        tz = ZoneInfo(timezone_name)\n    except ZoneInfoNotFoundError:\n        timezone_name = "Africa/Cairo"\n        tz = ZoneInfo(timezone_name)\n    return timezone_name, datetime.now(tz)\n\n\ndef _with_current_patient_appointments(\n    *,\n    db: Session,\n    workspace: Workspace,\n    patient: Patient,\n    clinic_catalog: dict[str, object],\n) -> dict[str, object]:\n    """Add verified upcoming appointment choices without polluting the workspace catalog cache.\n\n    This is used only while a reschedule workflow is already active. The existing semantic model\n    can then resolve a natural customer reference to a canonical appointment ID in the same call;\n    Python still validates that ID against this current-patient list before any tool receives it.\n    """\n    adapter = get_clinic_adapter(db=db, workspace=workspace)\n    result = adapter.get_patient_appointments(\n        AppointmentReadRequest(\n            patient_id=str(patient.id),\n            include_past=False,\n            limit=10,\n        )\n    )\n    catalog = dict(clinic_catalog)\n    appointments: list[dict[str, object]] = []\n    for appointment in result.appointments:\n        if appointment.status not in {"pending", "confirmed"}:\n            continue\n        timezone_name = appointment.timezone or workspace.timezone or "Africa/Cairo"\n        try:\n            clinic_tz = ZoneInfo(timezone_name)\n        except ZoneInfoNotFoundError:\n            clinic_tz = ZoneInfo("Africa/Cairo")\n        appointments.append(\n            {\n                "id": str(appointment.appointment_id),\n                "appointment_id": str(appointment.appointment_id),\n                "service_id": str(appointment.service_id),\n                "service_name": appointment.service_name,\n                "doctor_id": str(appointment.doctor_id),\n                "doctor_name": appointment.doctor_name,\n                "status": appointment.status,\n                "start_local": appointment.start_at.astimezone(clinic_tz).isoformat(),\n                "end_local": appointment.end_at.astimezone(clinic_tz).isoformat(),\n            }\n        )\n    catalog["appointments"] = appointments\n    return catalog\n\n\ndef _uuid_from_metadata(value: object) -> UUID | None:\n''',
)
replace(
    "backend/app/services/agent_chat.py",
    '''    clinic_catalog = build_clinic_catalog(db, workspace)\n    logger.info(\n''',
    '''    clinic_catalog = build_clinic_catalog(db, workspace)\n    if flow is not None and flow.is_active and flow.flow_type == "appointment_reschedule":\n        clinic_catalog = _with_current_patient_appointments(\n            db=db,\n            workspace=workspace,\n            patient=patient,\n            clinic_catalog=clinic_catalog,\n        )\n    logger.info(\n''',
)

# 5) Focused regression tests only for the newly fixed link.
test_path = ROOT / "backend/tests/test_reschedule_appointment_resolution.py"
test_path.write_text(
    '''from types import SimpleNamespace\nfrom uuid import uuid4\n\nfrom app.agents.clinic_grounding import validate_grounded_entity_ids\nfrom app.agents.turn_models import empty_entity_hints\nfrom app.services import agent_chat\n\n\ndef test_grounding_accepts_only_current_patient_appointment_ids() -> None:\n    hints = empty_entity_hints().model_copy(update={"appointment_id": "APT-2"})\n    catalog = {\n        "services": [],\n        "branches": [],\n        "doctors": [],\n        "appointments": [{"id": "APT-1"}, {"id": "APT-2"}],\n    }\n    grounded = validate_grounded_entity_ids(hints, catalog)\n    assert grounded.appointment_id == "APT-2"\n\n    invalid = validate_grounded_entity_ids(\n        hints.model_copy(update={"appointment_id": "OTHER-PATIENT-APT"}),\n        catalog,\n    )\n    assert invalid.appointment_id is None\n\n\ndef test_active_reschedule_catalog_exposes_verified_upcoming_appointment(monkeypatch) -> None:\n    patient_id = uuid4()\n    record = SimpleNamespace(\n        appointment_id="APT-10",\n        service_id="SERVICE-OLD",\n        service_name="Old service",\n        doctor_id="DOCTOR-1",\n        doctor_name="Doctor One",\n        status="confirmed",\n        timezone="Africa/Cairo",\n        start_at=agent_chat.datetime.fromisoformat("2026-09-10T13:00:00+00:00"),\n        end_at=agent_chat.datetime.fromisoformat("2026-09-10T13:15:00+00:00"),\n    )\n    adapter = SimpleNamespace(\n        get_patient_appointments=lambda request: SimpleNamespace(appointments=(record,))\n    )\n    monkeypatch.setattr(agent_chat, "get_clinic_adapter", lambda **_: adapter)\n\n    catalog = agent_chat._with_current_patient_appointments(\n        db=SimpleNamespace(),\n        workspace=SimpleNamespace(timezone="Africa/Cairo"),\n        patient=SimpleNamespace(id=patient_id),\n        clinic_catalog={"services": []},\n    )\n\n    assert catalog["appointments"] == [\n        {\n            "id": "APT-10",\n            "appointment_id": "APT-10",\n            "service_id": "SERVICE-OLD",\n            "service_name": "Old service",\n            "doctor_id": "DOCTOR-1",\n            "doctor_name": "Doctor One",\n            "status": "confirmed",\n            "start_local": "2026-09-10T16:00:00+03:00",\n            "end_local": "2026-09-10T16:15:00+03:00",\n        }\n    ]\n''',
    encoding="utf-8",
)
