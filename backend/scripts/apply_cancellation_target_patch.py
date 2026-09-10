from __future__ import annotations

from pathlib import Path


AGENT_PATH = Path("app/services/agent_chat.py")
INTERPRETER_PATH = Path("app/agents/turn_interpreter.py")
TEST_PATH = Path("tests/test_verified_cancellation_execution.py")


NEW_HELPER = '''def _verified_cancellation_action(
    *,
    tool_context: AgentToolContext,
    policy: CapabilityPolicyDecision,
    decision: SemanticCapabilityDecision,
    clinic_catalog: dict[str, object],
) -> tuple[str, str] | None:
    """Cancel one verified current-patient appointment selected by semantic entities.

    The semantic layer owns meaning. Python only intersects canonical IDs/date/time
    fields with the verified current-patient appointment set, and writes only when the
    intersection contains exactly one appointment. Customer wording is never parsed here.
    """
    if "appointment_cancellation" not in {str(item) for item in policy.capabilities}:
        return None
    rows = clinic_catalog.get("appointments")
    if not isinstance(rows, list):
        return None
    candidates = [row for row in rows if isinstance(row, dict)]
    hints = decision.entity_hints
    appointment_id = str(hints.appointment_id or "").strip()

    if appointment_id:
        candidates = [
            row
            for row in candidates
            if str(row.get("appointment_id") or row.get("id") or "") == appointment_id
        ]
    else:
        filters_applied = 0
        service_ids: list[str] = []
        if hints.service_id:
            service_ids = [str(hints.service_id)]
        elif hints.service_candidate_ids:
            service_ids = [str(value) for value in hints.service_candidate_ids]
        if service_ids:
            candidates = [
                row for row in candidates if str(row.get("service_id") or "") in service_ids
            ]
            filters_applied += 1

        doctor_ids: list[str] = []
        if hints.doctor_id:
            doctor_ids = [str(hints.doctor_id)]
        elif hints.doctor_candidate_ids:
            doctor_ids = [str(value) for value in hints.doctor_candidate_ids]
        if doctor_ids:
            candidates = [
                row for row in candidates if str(row.get("doctor_id") or "") in doctor_ids
            ]
            filters_applied += 1

        requested_date = str(hints.requested_date or "").strip()
        if requested_date:
            candidates = [
                row
                for row in candidates
                if str(row.get("start_local") or "")[:10] == requested_date
            ]
            filters_applied += 1

        requested_time = str(hints.requested_start_time or "").strip()
        if requested_time:
            normalized_time = requested_time
            if len(normalized_time) == 4 and normalized_time[1] == ":":
                normalized_time = "0" + normalized_time
            matched: list[dict[str, object]] = []
            for row in candidates:
                try:
                    row_time = datetime.fromisoformat(
                        str(row.get("start_local") or "")
                    ).strftime("%H:%M")
                except ValueError:
                    continue
                if row_time == normalized_time:
                    matched.append(row)
            candidates = matched
            filters_applied += 1

        if filters_applied == 0:
            return None

    if len(candidates) != 1:
        return None
    selected = candidates[0]
    appointment_id = str(selected.get("appointment_id") or selected.get("id") or "").strip()
    if not appointment_id:
        return None

    result = _invoke_authorized_tool(
        tool_context=tool_context,
        policy=policy,
        tool_name="cancel_appointment",
        arguments={
            "appointment_id": appointment_id,
            "reason": "Customer explicitly requested cancellation.",
        },
    )
    if not result or result.get("ok") is not True:
        return None

    service_name = str(selected.get("service_name") or "الموعد").strip()
    start_label = ""
    raw_start = selected.get("start_local")
    if raw_start:
        try:
            start_at = datetime.fromisoformat(str(raw_start))
            start_label = f" يوم {start_at.strftime('%d/%m/%Y')} الساعة {start_at.strftime('%H:%M')}"
        except ValueError:
            start_label = ""
    return (
        f"تمام، ألغيت موعد {service_name}{start_label}.",
        "deterministic:verified-appointment-cancellation",
    )


'''


TEST_CONTENT = '''from types import SimpleNamespace

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
'''


def main() -> None:
    text = AGENT_PATH.read_text(encoding="utf-8")
    start = text.index("def _verified_cancellation_action(")
    end = text.index("def _flow_type_from_capabilities", start)
    AGENT_PATH.write_text(text[:start] + NEW_HELPER + text[end:], encoding="utf-8")

    interpreter = INTERPRETER_PATH.read_text(encoding="utf-8")
    old = (
        '        "When current-patient appointments are supplied and a reschedule turn clearly identifies one existing "\n'
        '        "appointment from its displayed date/time/service/doctor, set appointment_id to that exact catalog ID; "\n'
    )
    new = (
        '        "When current-patient appointments are supplied and a reschedule or cancellation turn clearly identifies one existing "\n'
        '        "appointment from its displayed date/time/service/doctor, set appointment_id to that exact catalog ID; "\n'
    )
    if old not in interpreter:
        raise RuntimeError("Grounding wording anchor not found")
    INTERPRETER_PATH.write_text(interpreter.replace(old, new, 1), encoding="utf-8")
    TEST_PATH.write_text(TEST_CONTENT, encoding="utf-8")


if __name__ == "__main__":
    main()
