from __future__ import annotations

import json
from dataclasses import asdict, is_dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any
from uuid import UUID
from zoneinfo import ZoneInfo

from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session

from app.agents.structured_output import StructuredOutputError
from app.agents.v2 import turn_interpreter
from app.core.config import settings
from app.models.appointment import Appointment
from app.models.message import Message
from app.models.patient import Patient
from app.models.service import Service
from app.models.workspace import Workspace
from app.schemas.agent import AgentChatRequest
from app.services.agent_v2 import live_chat
from app.services.agent_v2.state import BookingTaskState, RescheduleTaskState
from app.services.agent_v2.state_persistence import load_active_task
from scripts.run_live_agent_ux_review import _base_patient, _seed_upcoming

OUT = Path("artifacts/correction-semantics-validation.json")
OUT.parent.mkdir(parents=True, exist_ok=True)
CAIRO = ZoneInfo("Africa/Cairo")
ORIGINAL_ORCHESTRATE = live_chat.orchestrate_v2_turn
CAP: dict[str, Any] = {"turn": None}


def _serial(value: Any) -> Any:
    if value is None or isinstance(value, (str, int, float, bool)):
        return value
    if isinstance(value, UUID):
        return str(value)
    if isinstance(value, datetime):
        return value.isoformat()
    if hasattr(value, "model_dump"):
        return value.model_dump(mode="json")
    if is_dataclass(value):
        return {key: _serial(item) for key, item in asdict(value).items()}
    if isinstance(value, dict):
        return {str(key): _serial(item) for key, item in value.items()}
    if isinstance(value, (list, tuple, set)):
        return [_serial(item) for item in value]
    return str(value)


def _capture_orchestrate(*args, **kwargs):
    result = ORIGINAL_ORCHESTRATE(*args, **kwargs)
    CAP["turn"] = result
    return result


live_chat.orchestrate_v2_turn = _capture_orchestrate


def _appointment_snapshot(db: Session, workspace_id: UUID, patient_id: UUID) -> dict[str, dict[str, Any]]:
    rows = list(
        db.scalars(
            select(Appointment).where(
                Appointment.workspace_id == workspace_id,
                Appointment.patient_id == patient_id,
            )
        )
    )
    return {
        str(row.id): {
            "status": row.status,
            "service_id": str(row.service_id),
            "doctor_id": str(row.doctor_id) if row.doctor_id else None,
            "start_at": row.start_at.isoformat() if row.start_at else None,
        }
        for row in rows
    }


def _appointment_delta(before: dict[str, dict[str, Any]], after: dict[str, dict[str, Any]]) -> dict[str, Any]:
    return {
        "created": {key: value for key, value in after.items() if key not in before},
        "deleted": {key: value for key, value in before.items() if key not in after},
        "changed": {
            key: {"before": before[key], "after": after[key]}
            for key in before.keys() & after.keys()
            if before[key] != after[key]
        },
    }


def _state(db: Session, workspace: Workspace, patient: Patient, conversation_id: UUID | None) -> dict[str, Any] | None:
    if conversation_id is None:
        return None
    persisted = load_active_task(
        db,
        workspace_id=workspace.id,
        conversation_id=conversation_id,
        patient_id=patient.id,
    )
    if persisted is None:
        return None
    task = persisted.active_task
    if isinstance(task, BookingTaskState):
        c = task.constraints
        return {
            "task_type": "booking",
            "flow_id": str(persisted.flow_id),
            "flow_version": persisted.flow_version,
            "service_id": c.service_id,
            "doctor_id": c.doctor_id,
            "device_key": c.device_key,
            "date": _serial(c.date),
            "time": _serial(c.time),
            "package_usage": c.package_usage,
            "authorized": task.write_authorization.authorized,
        }
    if isinstance(task, RescheduleTaskState):
        c = task.replacement
        return {
            "task_type": "reschedule",
            "flow_id": str(persisted.flow_id),
            "flow_version": persisted.flow_version,
            "target_appointment_id": task.target.appointment_id,
            "service_id": c.service_id,
            "doctor_id": c.doctor_id,
            "device_key": c.device_key,
            "date": _serial(c.date),
            "time": _serial(c.time),
            "package_usage": c.package_usage,
            "authorized": task.write_authorization.authorized,
        }
    return _serial(task)


def _turn_meta(turn: Any) -> dict[str, Any]:
    if turn is None:
        return {}
    understanding = _serial(turn.understanding)
    operations = understanding.get("operations", []) if isinstance(understanding, dict) else []
    return {
        "operations": operations,
        "reference_action": getattr(turn, "reference_action", None),
        "selected_option_ref": getattr(turn, "selected_option_ref", None),
        "reference_path": bool(getattr(turn, "reference_semantic_path_used", False)),
        "responder_model": getattr(turn, "responder_model", None),
    }


def _send(db: Session, workspace: Workspace, patient: Patient, conversation_id: UUID | None, message: str) -> tuple[UUID, dict[str, Any]]:
    CAP["turn"] = None
    before_state = _state(db, workspace, patient, conversation_id)
    before_appts = _appointment_snapshot(db, workspace.id, patient.id)
    response = live_chat.run_agent_chat(
        db=db,
        workspace=workspace,
        payload=AgentChatRequest(
            patient_id=patient.id,
            conversation_id=conversation_id,
            channel="web",
            message=message,
        ),
    )
    conversation_id = response.conversation_id
    after_state = _state(db, workspace, patient, conversation_id)
    after_appts = _appointment_snapshot(db, workspace.id, patient.id)
    outbound_meta: dict[str, Any] = {}
    if response.outbound_message_id is not None:
        outbound = db.get(Message, response.outbound_message_id)
        if outbound is not None and isinstance(outbound.metadata_json, dict):
            outbound_meta = dict(outbound.metadata_json)
    item = {
        "user": message,
        "reply": response.reply,
        "model": response.model,
        "before_state": before_state,
        "after_state": after_state,
        "appointment_delta": _appointment_delta(before_appts, after_appts),
        "turn": _turn_meta(CAP["turn"]),
        "availability_context": outbound_meta.get("v2_availability_reference_context"),
        "structured_failure": outbound_meta.get("v2_structured_interpretation_failure"),
    }
    print(f"{message} => {(response.reply or '<no reply>').replace(chr(10), ' ')[:300]}", flush=True)
    return conversation_id, item


def _operation(item: dict[str, Any], index: int = 0) -> dict[str, Any]:
    ops = item.get("turn", {}).get("operations", [])
    return ops[index] if isinstance(ops, list) and len(ops) > index and isinstance(ops[index], dict) else {}


def _date(state: dict[str, Any] | None) -> str | None:
    raw = (state or {}).get("date")
    return raw.get("start_date") if isinstance(raw, dict) else None


def _time(state: dict[str, Any] | None) -> str | None:
    raw = (state or {}).get("time")
    return raw.get("start_time") if isinstance(raw, dict) else None


def _created_local(item: dict[str, Any]) -> list[datetime]:
    created = item.get("appointment_delta", {}).get("created", {})
    result: list[datetime] = []
    for row in created.values():
        raw = row.get("start_at") if isinstance(row, dict) else None
        if isinstance(raw, str):
            result.append(datetime.fromisoformat(raw).astimezone(CAIRO))
    return result


def _assert_booking_target(item: dict[str, Any], *, date: str, time: str) -> None:
    state = item.get("after_state")
    if isinstance(state, dict) and state.get("task_type") == "booking":
        assert _date(state) == date, (state, date)
        assert _time(state) == time, (state, time)
        return
    created = _created_local(item)
    assert any(dt.date().isoformat() == date and dt.strftime("%H:%M") == time for dt in created), item


def _no_appointment_change(item: dict[str, Any]) -> None:
    delta = item["appointment_delta"]
    assert not delta["created"] and not delta["deleted"] and not delta["changed"], delta


def _service_id(db: Session, workspace: Workspace, name: str) -> str:
    row = db.scalar(select(Service).where(Service.workspace_id == workspace.id, Service.name == name))
    if row is None:
        raise RuntimeError(f"missing service fixture: {name}")
    return str(row.id)


def _run_case(connection, workspace_id: UUID, patient_id: UUID, name: str, messages: list[str], check, *, seed: int = 0) -> dict[str, Any]:
    tx = connection.begin_nested()
    db = Session(bind=connection, expire_on_commit=False, join_transaction_mode="create_savepoint")
    turns: list[dict[str, Any]] = []
    try:
        workspace = db.get(Workspace, workspace_id)
        patient = db.get(Patient, patient_id)
        if workspace is None or patient is None:
            raise RuntimeError("fixture disappeared")
        if seed:
            _seed_upcoming(db, workspace, patient, seed)
            db.flush()
        cid = None
        for message in messages:
            cid, item = _send(db, workspace, patient, cid, message)
            turns.append(item)
        check(db, workspace, patient, turns)
        return {"name": name, "status": "PASS", "turns": turns}
    except Exception as exc:
        return {"name": name, "status": "FAIL", "error": f"{type(exc).__name__}: {exc}", "turns": turns}
    finally:
        db.close()
        if tx.is_active:
            tx.rollback()


def _run_c14(connection, workspace_id: UUID, patient_id: UUID) -> dict[str, Any]:
    name = "C14_after_SOE_containment"
    tx = connection.begin_nested()
    db = Session(bind=connection, expire_on_commit=False, join_transaction_mode="create_savepoint")
    turns: list[dict[str, Any]] = []
    original = turn_interpreter.invoke_typed_structured_output
    try:
        workspace = db.get(Workspace, workspace_id)
        patient = db.get(Patient, patient_id)
        cid = None
        cid, first = _send(db, workspace, patient, cid, "عايزة أحجز PRP للبشرة يوم 2026-10-18 الساعة 3")
        turns.append(first)
        state_before = _state(db, workspace, patient, cid)
        attempts = 0

        def fail_structured(**_kwargs):
            nonlocal attempts
            attempts += 1
            raise StructuredOutputError("forced correction semantics validation failure")

        turn_interpreter.invoke_typed_structured_output = fail_structured
        cid, failed = _send(db, workspace, patient, cid, "لا الاثنين")
        turns.append(failed)
        turn_interpreter.invoke_typed_structured_output = original
        state_after = _state(db, workspace, patient, cid)
        assert attempts == 4, attempts
        assert state_after == state_before, (state_before, state_after)
        assert failed.get("structured_failure"), failed
        _no_appointment_change(failed)
        cid, recovered = _send(db, workspace, patient, cid, "قصدي يوم 2026-10-19 والساعة 4")
        turns.append(recovered)
        _assert_booking_target(recovered, date="2026-10-19", time="16:00")
        return {"name": name, "status": "PASS", "forced_attempts": attempts, "turns": turns}
    except Exception as exc:
        return {"name": name, "status": "FAIL", "error": f"{type(exc).__name__}: {exc}", "turns": turns}
    finally:
        turn_interpreter.invoke_typed_structured_output = original
        db.close()
        if tx.is_active:
            tx.rollback()


def _run_reschedule_case(connection, workspace_id: UUID, patient_id: UUID, name: str, mode: str) -> dict[str, Any]:
    tx = connection.begin_nested()
    db = Session(bind=connection, expire_on_commit=False, join_transaction_mode="create_savepoint")
    turns: list[dict[str, Any]] = []
    try:
        workspace = db.get(Workspace, workspace_id)
        patient = db.get(Patient, patient_id)
        seeded = _seed_upcoming(db, workspace, patient, 1)[0]
        db.flush()
        service = db.get(Service, seeded.service_id)
        local = seeded.start_at.astimezone(CAIRO)
        source = f"عايزة أغير ميعاد {service.name} يوم {local.date().isoformat()} الساعة {local.strftime('%H:%M')}"
        cid = None
        cid, one = _send(db, workspace, patient, cid, source)
        turns.append(one)
        first_state = one["after_state"]
        assert first_state and first_state["task_type"] == "reschedule", first_state
        target = first_state["target_appointment_id"]
        if mode == "corrections":
            for message in ["خليه يوم 2026-10-12 الساعة 3", "لا يوم 2026-10-13", "لا الساعة 4"]:
                cid, item = _send(db, workspace, patient, cid, message)
                turns.append(item)
            final = turns[-1]["after_state"]
            assert final and final["task_type"] == "reschedule", final
            assert final["target_appointment_id"] == target
            assert _date(final) == "2026-10-13"
            assert _time(final) == "16:00"
            for item in turns[1:]:
                _no_appointment_change(item)
        else:
            for message in ["خليه الساعة 4", "لا خليها 5"]:
                cid, item = _send(db, workspace, patient, cid, message)
                turns.append(item)
            final = turns[-1]["after_state"]
            assert final and final["target_appointment_id"] == target
            assert _date(final) is None, final
            assert _time(final) == "17:00", final
            for item in turns[1:]:
                _no_appointment_change(item)
        return {"name": name, "status": "PASS", "target": target, "turns": turns}
    except Exception as exc:
        return {"name": name, "status": "FAIL", "error": f"{type(exc).__name__}: {exc}", "turns": turns}
    finally:
        db.close()
        if tx.is_active:
            tx.rollback()


def main() -> None:
    engine = create_engine(settings.database_url, pool_pre_ping=True)
    connection = engine.connect()
    outer = connection.begin()
    root = Session(bind=connection, expire_on_commit=False, join_transaction_mode="create_savepoint")
    results: list[dict[str, Any]] = []
    try:
        workspace = root.scalar(select(Workspace).where(Workspace.slug == "tia"))
        if workspace is None:
            raise RuntimeError("workspace tia not found")
        patient = _base_patient(root, workspace)
        wid, pid = workspace.id, patient.id
        prp_id = _service_id(root, workspace, "PRP للبشرة")
        meso_id = _service_id(root, workspace, "ميزوثيرابي للشعر")
        laser_id = _service_id(root, workspace, "ليزر إزالة الشعر - إبط")

        def booking_fields(date: str, time: str):
            def check(_db, _ws, _patient, turns):
                _assert_booking_target(turns[-1], date=date, time=time)
            return check

        results.append(_run_case(connection, wid, pid, "C1_time_replacement", ["عايزة أحجز PRP للبشرة يوم 2026-10-18 الساعة 3", "لا الساعة 4"], booking_fields("2026-10-18", "16:00")))
        results.append(_run_case(connection, wid, pid, "C2_bare_clock_correction", ["عايزة أحجز PRP للبشرة يوم 2026-10-18 الساعة 3", "لا 4"], booking_fields("2026-10-18", "16:00")))

        def c3(_db, _ws, _patient, turns):
            state = turns[-1]["after_state"]
            assert state and _time(state) == "03:00", state
            assert _date(state) == "2026-10-18"
            _no_appointment_change(turns[-1])
        results.append(_run_case(connection, wid, pid, "C3_exact_03", ["عايزة أحجز PRP للبشرة يوم 2026-10-18 الساعة 15:00", "لا 03:00"], c3))

        def c4(_db, _ws, _patient, turns):
            _assert_booking_target(turns[-1], date="2026-10-19", time="15:00")
        results.append(_run_case(connection, wid, pid, "C4_date_correction", ["عايزة أحجز PRP للبشرة يوم 2026-10-18 الساعة 3", "لا يوم 2026-10-19"], c4))

        def c5(_db, _ws, _patient, turns):
            state = turns[-1]["after_state"]
            assert state and _date(state) == "2026-10-17", state
            assert state["service_id"] == prp_id
        results.append(_run_case(connection, wid, pid, "C5_repeated_date", ["عايزة أحجز PRP للبشرة يوم 2026-10-17", "لا يوم 2026-10-18", "لا يوم 2026-10-17 أحسن"], c5))

        def c6(_db, _ws, _patient, turns):
            before = turns[0]["after_state"]
            after = turns[-1]["after_state"]
            assert before and before["doctor_id"], before
            assert after and after["doctor_id"] != before["doctor_id"], (before, after)
            _no_appointment_change(turns[-1])
        results.append(_run_case(connection, wid, pid, "C6_another_doctor", ["عايزة أحجز PRP للبشرة يوم 2026-10-17 مع د. مها", "لا مع دكتور تاني"], c6))

        def c7(_db, _ws, _patient, turns):
            state = turns[-1]["after_state"]
            op = _operation(turns[-1])
            assert "doctor" in op.get("cleared_active_task_fields", []), op
            assert state and state["doctor_id"] is None, state
            assert state["service_id"] == prp_id and _date(state) == "2026-10-17"
            _no_appointment_change(turns[-1])
        results.append(_run_case(connection, wid, pid, "C7_clear_doctor", ["عايزة أحجز PRP للبشرة يوم 2026-10-17 مع د. مها", "مش فارق الدكتور"], c7))

        def c8(_db, _ws, _patient, turns):
            before = turns[0]["after_state"]
            after = turns[-1]["after_state"]
            assert before and after and before["doctor_id"] != after["doctor_id"]
            assert after["service_id"] == laser_id and _date(after) == "2026-10-12" and _time(after) == "15:00"
        results.append(_run_case(connection, wid, pid, "C8_specific_doctor", ["عايزة أحجز ليزر إزالة الشعر - إبط يوم 2026-10-12 الساعة 3 مع مريم حسن", "لا خليها مع أحمد محمود"], c8))

        def c9(_db, _ws, _patient, turns):
            state = turns[-1]["after_state"]
            op = _operation(turns[-1])
            assert op.get("fresh_task") is False and op.get("active_task_relationship") == "continue", op
            assert state and state["service_id"] == meso_id, state
            assert _date(state) == "2026-10-17" and _time(state) == "15:00", state
            assert state["doctor_id"] is None, state
        results.append(_run_case(connection, wid, pid, "C9_same_task_service", ["عايزة أحجز PRP للبشرة يوم 2026-10-17 الساعة 3 مع د. مها", "لا قصدي ميزوثيرابي للشعر"], c9))

        def c10(_db, _ws, _patient, turns):
            before = turns[0]["after_state"]
            after = turns[-1]["after_state"]
            assert before and after and before["device_key"] != after["device_key"]
            assert after["service_id"] == laser_id and _date(after) == "2026-10-12" and _time(after) == "15:00"
        results.append(_run_case(connection, wid, pid, "C10_device", ["عايزة أحجز ليزر إزالة الشعر - إبط يوم 2026-10-12 الساعة 3 على جهاز Candela Gentle", "لا Prime Lase"], c10))

        def c11(_db, _ws, _patient, turns):
            assert turns[-1]["turn"]["reference_action"] == "select_presented_option", turns[-1]
            assert turns[-1]["turn"]["selected_option_ref"] == "opt_3", turns[-1]
            _no_appointment_change(turns[-1])
        results.append(_run_case(connection, wid, pid, "C11_option_correction", ["وريني مواعيد ليزر إزالة الشعر - إبط يوم 2026-10-12", "الأول", "لا قصدي التالت"], c11))

        def c12(_db, _ws, _patient, turns):
            assert turns[-1]["turn"]["reference_action"] == "clarify", turns[-1]
            _no_appointment_change(turns[-1])
        results.append(_run_case(connection, wid, pid, "C12_relative_safe_clarify", ["وريني مواعيد ليزر إزالة الشعر - إبط يوم 2026-10-12", "الأول", "لا اللي بعده"], c12))

        results.append(_run_case(connection, wid, pid, "C13_after_side_question", ["عايزة أحجز PRP للبشرة يوم 2026-10-18 الساعة 3", "السعر كام؟", "لا خليها 4"], booking_fields("2026-10-18", "16:00")))
        results.append(_run_c14(connection, wid, pid))
        results.append(_run_reschedule_case(connection, wid, pid, "C15_reschedule_corrections", "corrections"))
        results.append(_run_reschedule_case(connection, wid, pid, "C16_missing_date", "missing_date"))

        def c17(_db, _ws, _patient, turns):
            before_ctx = turns[-2].get("availability_context") or {}
            after_ctx = turns[-1].get("availability_context") or {}
            assert turns[-1]["turn"]["reference_action"] == "clarify", turns[-1]
            assert turns[-1]["turn"]["selected_option_ref"] is None, turns[-1]
            assert after_ctx.get("last_selected_option_ref") == before_ctx.get("last_selected_option_ref"), (before_ctx, after_ctx)
            _no_appointment_change(turns[-1])
        results.append(_run_case(connection, wid, pid, "C17_ordinal_clock_ambiguity", ["وريني مواعيد ليزر إزالة الشعر - إبط يوم 2026-10-12", "الأول", "لا 4"], c17))

        def c18(_db, _ws, _patient, turns):
            state = turns[-1]["after_state"]
            op = _operation(turns[-1])
            assert op.get("fresh_task") is True, op
            assert op.get("active_task_relationship") == "replace", op
            assert op.get("fresh_task_explicit_fields") == ["service"], op
            assert state and state["service_id"] == laser_id, state
            assert _date(state) is None and _time(state) is None, state
        results.append(_run_case(connection, wid, pid, "C18_fresh_task", ["عايزة أحجز PRP للبشرة يوم 2026-10-18", "خلاص سيب PRP، عايزة أحجز ليزر إزالة الشعر - إبط بدلها"], c18))

        def cl1(_db, _ws, _patient, turns):
            before = turns[0]["after_state"]
            after = turns[-1]["after_state"]
            op = _operation(turns[-1])
            assert "doctor" not in op.get("cleared_active_task_fields", []), op
            assert before and after and after["doctor_id"] == before["doctor_id"], (before, after)
            _no_appointment_change(turns[-1])
        results.append(_run_case(connection, wid, pid, "CL1_unknown_not_clear", ["عايزة أحجز PRP للبشرة يوم 2026-10-17 مع د. مها", "خليه مع دكتور اسمه XYZ"], cl1))

        def cl2(_db, _ws, _patient, turns):
            before = turns[0]["after_state"]
            after = turns[-1]["after_state"]
            op = _operation(turns[-1])
            assert "doctor" not in op.get("cleared_active_task_fields", []), op
            assert before and after and after["doctor_id"] == before["doctor_id"], (before, after)
        results.append(_run_case(connection, wid, pid, "CL2_ambiguous_not_clear", ["عايزة أحجز PRP للبشرة يوم 2026-10-17 مع د. مها", "مها ولا هالة مصطفى؟"], cl2))

        def cl3(_db, _ws, _patient, turns):
            cleared = turns[1]["after_state"]
            final = turns[-1]["after_state"]
            assert cleared and cleared["doctor_id"] is None, cleared
            assert final and final["doctor_id"] is not None, final
        results.append(_run_case(connection, wid, pid, "CL3_clear_then_set", ["عايزة أحجز PRP للبشرة يوم 2026-10-17 مع د. مها", "مش فارق الدكتور", "خلاص خليه مع هالة مصطفى"], cl3))

        def cl4(_db, _ws, _patient, turns):
            state = turns[-1]["after_state"]
            assert state and state["doctor_id"] is None, state
            assert "doctor" in _operation(turns[-1]).get("cleared_active_task_fields", [])
        results.append(_run_case(connection, wid, pid, "CL4_set_then_clear", ["عايزة أحجز PRP للبشرة يوم 2026-10-17 مع هالة مصطفى", "مش فارق الدكتور"], cl4))

        def side_clear(_db, _ws, _patient, turns):
            assert turns[1]["after_state"] and turns[1]["after_state"]["doctor_id"] is None
            assert turns[2]["after_state"] and turns[2]["after_state"]["doctor_id"] is None
            assert turns[3]["after_state"] and turns[3]["after_state"]["doctor_id"] is None
        results.append(_run_case(connection, wid, pid, "CLEAR_side_question_continuity", ["عايزة أحجز PRP للبشرة يوم 2026-10-17 مع د. مها", "مش فارق الدكتور", "السعر كام؟", "نرجع للحجز"], side_clear))

        failed = [item for item in results if item["status"] != "PASS"]
        report = {
            "head_expected": "focused correction semantics PR head",
            "generated_at": datetime.now(UTC).isoformat(),
            "results": results,
            "pass_count": len(results) - len(failed),
            "fail_count": len(failed),
        }
        OUT.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
        print("SUMMARY", json.dumps({"pass": report["pass_count"], "fail": report["fail_count"], "failed": [x["name"] for x in failed]}, ensure_ascii=False), flush=True)
        if failed:
            raise SystemExit(1)
    finally:
        root.close()
        if outer.is_active:
            outer.rollback()
        connection.close()
        engine.dispose()


if __name__ == "__main__":
    main()
