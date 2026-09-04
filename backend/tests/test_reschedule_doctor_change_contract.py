from pathlib import Path


def test_grounded_reschedule_propagates_requested_doctor() -> None:
    backend = Path(__file__).resolve().parent.parent
    tools = (backend / "app/agents/tools/clinic_tools.py").read_text(encoding="utf-8")
    chat = (backend / "app/services/agent_chat.py").read_text(encoding="utf-8")

    assert "doctor_id: str = \"\"" in tools
    assert "doctor_id=doctor_id or current.doctor_id" in tools
    assert "reschedule_arguments[\"doctor_id\"] = doctor_id" in chat
