from types import SimpleNamespace

from app.services import agent_chat


HYDRA_SERVICE = "service-hydra"
LASER_SERVICE = "service-laser"


def _policy():
    return SimpleNamespace(capabilities={"appointment_cancellation"})


def _hints(**updates):
    values = {
        "appointment_id": None,
        "service_id": None,
        "service_candidate_ids": [],
        "doctor_id": None,
        "doctor_candidate_ids": [],
        "requested_date": None,
        "requested_start_time": None,
    }
    values.update(updates)
    return SimpleNamespace(**values)


def _decision(**updates):
    return SimpleNamespace(entity_hints=_hints(**updates))


def _catalog(*, duplicate_hydra=False):
    rows = [
        {
            "id": "appt-hydra",
            "appointment_id": "appt-hydra",
            "service_id": HYDRA_SERVICE,
            "service_name": "هيدرافيشل",
            "doctor_id": "doctor-hala",
            "start_local": "2026-09-12T10:00:00+03:00",
        },
        {
            "id": "appt-laser",
            "appointment_id": "appt-laser",
            "service_id": LASER_SERVICE,
            "service_name": "ليزر إزالة الشعر - إبط",
            "doctor_id": "doctor-ahmed",
            "start_local": "2026-09-13T11:00:00+03:00",
        },
    ]
    if duplicate_hydra:
        rows.append(
            {
                "id": "appt-hydra-2",
                "appointment_id": "appt-hydra-2",
                "service_id": HYDRA_SERVICE,
                "service_name": "هيدرافيشل",
                "doctor_id": "doctor-hala",
                "start_local": "2026-09-14T10:00:00+03:00",
            }
        )
    return {"appointments": rows}


def _capture(monkeypatch):
    calls = []

    def fake_invoke(**kwargs):
        calls.append(kwargs)
        return {"ok": True}

    monkeypatch.setattr(agent_chat, "_invoke_authorized_tool", fake_invoke)
    return calls


def test_cancellation_without_canonical_target_never_writes(monkeypatch):
    calls = _capture(monkeypatch)
    assert agent_chat._verified_cancellation_action(
        tool_context=object(), policy=_policy(), decision=_decision(), clinic_catalog=_catalog()
    ) is None
    assert calls == []


def test_unknown_explicit_appointment_id_never_writes(monkeypatch):
    calls = _capture(monkeypatch)
    assert agent_chat._verified_cancellation_action(
        tool_context=object(),
        policy=_policy(),
        decision=_decision(appointment_id="not-current"),
        clinic_catalog=_catalog(),
    ) is None
    assert calls == []


def test_exact_semantic_appointment_id_executes_once(monkeypatch):
    calls = _capture(monkeypatch)
    result = agent_chat._verified_cancellation_action(
        tool_context=object(),
        policy=_policy(),
        decision=_decision(appointment_id="appt-hydra"),
        clinic_catalog=_catalog(),
    )
    assert result is not None
    assert calls[0]["arguments"]["appointment_id"] == "appt-hydra"
    assert len(calls) == 1


def test_unique_canonical_service_resolves_without_text_matching(monkeypatch):
    calls = _capture(monkeypatch)
    result = agent_chat._verified_cancellation_action(
        tool_context=object(),
        policy=_policy(),
        decision=_decision(service_id=HYDRA_SERVICE),
        clinic_catalog=_catalog(),
    )
    assert result is not None
    assert "هيدرافيشل" in result[0]
    assert calls[0]["arguments"]["appointment_id"] == "appt-hydra"
    assert len(calls) == 1


def test_same_service_multiple_appointments_stays_ambiguous(monkeypatch):
    calls = _capture(monkeypatch)
    result = agent_chat._verified_cancellation_action(
        tool_context=object(),
        policy=_policy(),
        decision=_decision(service_id=HYDRA_SERVICE),
        clinic_catalog=_catalog(duplicate_hydra=True),
    )
    assert result is None
    assert calls == []


def test_structured_date_can_narrow_same_service_to_one(monkeypatch):
    calls = _capture(monkeypatch)
    result = agent_chat._verified_cancellation_action(
        tool_context=object(),
        policy=_policy(),
        decision=_decision(service_id=HYDRA_SERVICE, requested_date="2026-09-14"),
        clinic_catalog=_catalog(duplicate_hydra=True),
    )
    assert result is not None
    assert calls[0]["arguments"]["appointment_id"] == "appt-hydra-2"
    assert len(calls) == 1
