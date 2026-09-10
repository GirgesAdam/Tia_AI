from types import SimpleNamespace

from app.services import agent_chat


def _policy():
    return SimpleNamespace(capabilities={"appointment_cancellation"})


def _decision(appointment_id):
    return SimpleNamespace(entity_hints=SimpleNamespace(appointment_id=appointment_id))


def _catalog():
    return {
        "appointments": [
            {
                "id": "appt-hydra",
                "appointment_id": "appt-hydra",
                "service_name": "هيدرافيشل",
                "start_local": "2026-09-12T10:00:00+03:00",
            },
            {
                "id": "appt-laser",
                "appointment_id": "appt-laser",
                "service_name": "ليزر إزالة الشعر - إبط",
                "start_local": "2026-09-13T11:00:00+03:00",
            },
        ]
    }


def test_verified_cancellation_requires_exact_current_patient_appointment(monkeypatch):
    calls = []

    def fake_invoke(**kwargs):
        calls.append(kwargs)
        return {"ok": True}

    monkeypatch.setattr(agent_chat, "_invoke_authorized_tool", fake_invoke)

    assert agent_chat._verified_cancellation_action(
        tool_context=object(),
        policy=_policy(),
        decision=_decision(None),
        clinic_catalog=_catalog(),
    ) is None
    assert agent_chat._verified_cancellation_action(
        tool_context=object(),
        policy=_policy(),
        decision=_decision("not-a-current-appointment"),
        clinic_catalog=_catalog(),
    ) is None
    assert calls == []


def test_verified_cancellation_executes_only_semantically_selected_id(monkeypatch):
    calls = []

    def fake_invoke(**kwargs):
        calls.append(kwargs)
        return {"ok": True}

    monkeypatch.setattr(agent_chat, "_invoke_authorized_tool", fake_invoke)

    result = agent_chat._verified_cancellation_action(
        tool_context=object(),
        policy=_policy(),
        decision=_decision("appt-hydra"),
        clinic_catalog=_catalog(),
    )

    assert result is not None
    assert "هيدرافيشل" in result[0]
    assert result[1] == "deterministic:verified-appointment-cancellation"
    assert len(calls) == 1
    assert calls[0]["tool_name"] == "cancel_appointment"
    assert calls[0]["arguments"]["appointment_id"] == "appt-hydra"
