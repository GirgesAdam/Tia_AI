from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]


def test_fresh_existing_appointment_service_edit_uses_reschedule_semantics() -> None:
    interpreter = (ROOT / "backend/app/agents/turn_interpreter.py").read_text(encoding="utf-8")
    agent_chat = (ROOT / "backend/app/services/agent_chat.py").read_text(encoding="utf-8")
    assert "EXISTING APPOINTMENT EDITS" in interpreter
    assert "treat it as appointment_reschedule even when the requested date/time stays" in interpreter
    assert "clinic_catalog = _with_current_patient_appointments(" in agent_chat
    assert '"laser_device_key": appointment.laser_device_key' in agent_chat


def test_doctor_calendar_is_bounded_and_workspace_scoped() -> None:
    route = (ROOT / "backend/app/api/routes/doctor_calendar.py").read_text(encoding="utf-8")
    assert "Doctor calendar ranges cannot exceed 42 days" in route
    assert "Appointment.workspace_id == access.workspace.id" in route
    assert "Appointment.status.notin_" in route


def test_service_editor_handles_conflicts_inline() -> None:
    actions = (ROOT / "frontend/src/app/(dashboard)/appointments/[appointmentId]/actions.ts").read_text(encoding="utf-8")
    editor = (ROOT / "frontend/src/app/(dashboard)/appointments/[appointmentId]/service-editor.tsx").read_text(encoding="utf-8")
    assert "AppointmentServiceChangeState" in actions
    assert "catch (error)" in actions
    assert "useActionState" in editor
    assert "state.error" in editor
