from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Callable
from uuid import UUID, uuid4
from zoneinfo import ZoneInfo

from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session

from app.agents.v2 import turn_interpreter
from app.core.config import settings
from app.models.appointment import Appointment
from app.models.branch import Branch
from app.models.clinic_inventory import ClinicLaserDevice, ServiceDevicePrice
from app.models.message import Message
from app.models.patient import Patient
from app.models.service import Service
from app.models.workspace import Workspace
from app.schemas.agent import AgentChatRequest
from app.services.agent_v2 import live_chat
from app.services.agent_v2.state import BookingTaskState, RescheduleTaskState
from app.services.agent_v2.state_persistence import load_active_task
from scripts.run_live_agent_ux_review import _base_patient, _seed_upcoming

OUT = Path("artifacts/correction-real-e2e.json")
OUT.parent.mkdir(parents=True, exist_ok=True)
CAIRO = ZoneInfo("Africa/Cairo")
ORIGINAL_ORCHESTRATE = live_chat.orchestrate_v2_turn
CAP: dict[str, Any] = {"turn": None}


def capture_orchestrate(*args, **kwargs):
    result = ORIGINAL_ORCHESTRATE(*args, **kwargs)
    CAP["turn"] = result
    return result


live_chat.orchestrate_v2_turn = capture_orchestrate


def state_snapshot(db: Session, ws: Workspace, patient: Patient, cid: UUID | None) -> dict[str, Any] | None:
    if cid is None:
        return None
    persisted = load_active_task(
        db,
        workspace_id=ws.id,
        conversation_id=cid,
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
            "service_id": c.service_id,
            "doctor_id": c.doctor_id,
            "device_key": c.device_key,
            "date": c.date.model_dump(mode="json") if c.date else None,
            "time": c.time.model_dump(mode="json") if c.time else None,
        }
    if isinstance(task, RescheduleTaskState):
        c = task.replacement
        return {
            "task_type": "reschedule",
            "flow_id": str(persisted.flow_id),
            "target_appointment_id": task.target.appointment_id,
            "service_id": c.service_id,
            "doctor_id": c.doctor_id,
            "device_key": c.device_key,
            "date": c.date.model_dump(mode="json") if c.date else None,
            "time": c.time.model_dump(mode="json") if c.time else None,
        }
    return {"task_type": task.task_type}


def appointment_snapshot(db: Session, ws: Workspace, patient: Patient) -> dict[str, tuple]:
    rows = db.scalars(
        select(Appointment).where(
            Appointment.workspace_id == ws.id,
            Appointment.patient_id == patient.id,
        )
    ).all()
    return {
        str(row.id): (
            row.status,
            str(row.service_id),
            str(row.doctor_id) if row.doctor_id else None,
            row.start_at.isoformat() if row.start_at else None,
        )
        for row in rows
    }


def operation_dict() -> dict[str, Any]:
    turn = CAP.get("turn")
    if turn is None:
        return {}
    raw = turn.understanding.model_dump(mode="json")
    ops = raw.get("operations") or []
    return ops[0] if ops else {}


def send(db: Session, ws: Workspace, patient: Patient, cid: UUID | None, text: str):
    CAP["turn"] = None
    before = appointment_snapshot(db, ws, patient)
    response = live_chat.run_agent_chat(
        db=db,
        workspace=ws,
        payload=AgentChatRequest(
            patient_id=patient.id,
            conversation_id=cid,
            channel="web",
            message=text,
        ),
    )
    after = appointment_snapshot(db, ws, patient)
    turn = CAP.get("turn")
    metadata: dict[str, Any] = {}
    if response.outbound_message_id:
        msg = db.get(Message, response.outbound_message_id)
        metadata = dict(msg.metadata_json or {}) if msg else {}
    item = {
        "user": text,
        "reply": response.reply,
        "model": response.model,
        "operation": operation_dict(),
        "reference_action": getattr(turn, "reference_action", None) if turn else None,
        "selected_option_ref": getattr(turn, "selected_option_ref", None) if turn else None,
        "state": state_snapshot(db, ws, patient, response.conversation_id),
        "appointment_changed": before != after,
        "availability_context": metadata.get("v2_availability_reference_context"),
    }
    print(f"USER: {text}", flush=True)
    print(f"AI: {(response.reply or '<none>').replace(chr(10), ' ')[:500]}", flush=True)
    print(f"STATE: {json.dumps(item['state'], ensure_ascii=False)}", flush=True)
    return response.conversation_id, item


def date_of(state: dict[str, Any] | None) -> str | None:
    raw = (state or {}).get("date")
    return raw.get("start_date") if isinstance(raw, dict) else None


def time_of(state: dict[str, Any] | None) -> str | None:
    raw = (state or {}).get("time")
    return raw.get("start_time") if isinstance(raw, dict) else None


def prepare_fixture(db: Session, ws: Workspace) -> dict[str, Service]:
    branch = db.scalar(
        select(Branch).where(Branch.workspace_id == ws.id, Branch.code == "new-cairo")
    )
    if branch is None:
        raise RuntimeError("new-cairo branch not seeded")
    ws.primary_branch_id = branch.id

    wanted = ["PRP للبشرة", "ميزوثيرابي للشعر", "ليزر إزالة الشعر - إبط", "هيدرافيشل"]
    services = {
        row.name: row
        for row in db.scalars(
            select(Service).where(Service.workspace_id == ws.id, Service.name.in_(wanted))
        ).all()
    }
    if set(services) != set(wanted):
        raise RuntimeError(f"missing services: {set(wanted) - set(services)}")

    laser = services["ليزر إزالة الشعر - إبط"]
    laser.requires_laser_device = True
    for key, name, price in (
        ("candela_gentle", "Candela Gentle", 65000),
        ("prime_lase", "Prime Lase", 55000),
    ):
        device = db.scalar(
            select(ClinicLaserDevice).where(
                ClinicLaserDevice.workspace_id == ws.id,
                ClinicLaserDevice.device_key == key,
            )
        )
        if device is None:
            db.add(
                ClinicLaserDevice(
                    id=uuid4(),
                    workspace_id=ws.id,
                    device_key=key,
                    name=name,
                    is_active=True,
                )
            )
        price_row = db.scalar(
            select(ServiceDevicePrice).where(
                ServiceDevicePrice.workspace_id == ws.id,
                ServiceDevicePrice.service_id == laser.id,
                ServiceDevicePrice.device_key == key,
            )
        )
        if price_row is None:
            db.add(
                ServiceDevicePrice(
                    id=uuid4(),
                    workspace_id=ws.id,
                    service_id=laser.id,
                    device_key=key,
                    device_name=name,
                    price_minor=price,
                    duration_minutes=15,
                    currency="EGP",
                    is_active=True,
                )
            )
    db.commit()
    return services


def run_case(
    connection,
    ws_id: UUID,
    patient_id: UUID,
    name: str,
    messages: list[str],
    check: Callable[[list[dict[str, Any]]], None],
    *,
    seed_upcoming: bool = False,
) -> dict[str, Any]:
    nested = connection.begin_nested()
    db = Session(bind=connection, expire_on_commit=False, join_transaction_mode="create_savepoint")
    turns: list[dict[str, Any]] = []
    try:
        ws = db.get(Workspace, ws_id)
        patient = db.get(Patient, patient_id)
        if seed_upcoming:
            _seed_upcoming(db, ws, patient, 1)
            db.flush()
        cid = None
        for message in messages:
            cid, item = send(db, ws, patient, cid, message)
            turns.append(item)
        check(turns)
        return {"name": name, "status": "PASS", "turns": turns}
    except Exception as exc:
        return {
            "name": name,
            "status": "FAIL",
            "error": f"{type(exc).__name__}: {exc}",
            "turns": turns,
        }
    finally:
        db.close()
        if nested.is_active:
            nested.rollback()


def run_missing_date_reschedule(connection, ws_id: UUID, patient_id: UUID) -> dict[str, Any]:
    nested = connection.begin_nested()
    db = Session(bind=connection, expire_on_commit=False, join_transaction_mode="create_savepoint")
    turns: list[dict[str, Any]] = []
    try:
        ws = db.get(Workspace, ws_id)
        patient = db.get(Patient, patient_id)
        seeded = _seed_upcoming(db, ws, patient, 1)[0]
        db.flush()
        service = db.get(Service, seeded.service_id)
        local = seeded.start_at.astimezone(CAIRO)
        cid = None
        start = (
            f"عايزة أغير ميعاد {service.name} يوم {local.date().isoformat()} "
            f"الساعة {local.strftime('%H:%M')}"
        )
        for text in (start, "خليه الساعة 4", "لا خليها 5"):
            cid, item = send(db, ws, patient, cid, text)
            turns.append(item)
        first = turns[0]["state"]
        final = turns[-1]["state"]
        assert first and first["task_type"] == "reschedule"
        assert final and final["task_type"] == "reschedule"
        assert final["target_appointment_id"] == first["target_appointment_id"]
        assert date_of(final) is None
        assert time_of(final) == "17:00"
        assert not turns[-1]["appointment_changed"]
        return {"name": "missing_date_reschedule", "status": "PASS", "turns": turns}
    except Exception as exc:
        return {
            "name": "missing_date_reschedule",
            "status": "FAIL",
            "error": f"{type(exc).__name__}: {exc}",
            "turns": turns,
        }
    finally:
        db.close()
        if nested.is_active:
            nested.rollback()


def main() -> None:
    engine = create_engine(settings.database_url, pool_pre_ping=True)
    bootstrap = Session(engine)
    ws = bootstrap.scalar(select(Workspace).where(Workspace.slug == "tia"))
    if ws is None:
        raise RuntimeError("tia workspace missing")
    services = prepare_fixture(bootstrap, ws)
    patient = _base_patient(bootstrap, ws)
    ws_id, patient_id = ws.id, patient.id
    service_ids = {name: str(service.id) for name, service in services.items()}
    bootstrap.close()

    connection = engine.connect()
    outer = connection.begin()
    results: list[dict[str, Any]] = []
    try:
        def check_clear(turns):
            before = turns[0]["state"]
            after = turns[-1]["state"]
            op = turns[-1]["operation"]
            assert before and before["doctor_id"]
            assert after and after["doctor_id"] is None
            assert after["service_id"] == before["service_id"]
            assert date_of(after) == date_of(before)
            assert "doctor" in op.get("cleared_active_task_fields", [])
            assert not turns[-1]["appointment_changed"]

        results.append(
            run_case(
                connection,
                ws_id,
                patient_id,
                "clear_doctor",
                [
                    "عايزة أحجز هيدرافيشل يوم 2026-10-13 مع مريم حسن",
                    "مش فارق الدكتور",
                ],
                check_clear,
            )
        )

        def check_another(turns):
            before = turns[0]["state"]
            after = turns[-1]["state"]
            assert before and before["doctor_id"]
            assert after and after["doctor_id"] != before["doctor_id"]
            assert not turns[-1]["appointment_changed"]

        results.append(
            run_case(
                connection,
                ws_id,
                patient_id,
                "another_doctor",
                [
                    "عايزة أحجز هيدرافيشل يوم 2026-10-13 مع مريم حسن",
                    "لا مع دكتور تاني",
                ],
                check_another,
            )
        )

        def check_ambiguity(turns):
            final = turns[-1]
            assert final["reference_action"] == "clarify", final
            assert final["selected_option_ref"] is None
            before_ctx = turns[-2]["availability_context"] or {}
            after_ctx = final["availability_context"] or {}
            assert after_ctx.get("last_selected_option_ref") == before_ctx.get(
                "last_selected_option_ref"
            )
            assert not final["appointment_changed"]

        results.append(
            run_case(
                connection,
                ws_id,
                patient_id,
                "ordinal_clock_ambiguity",
                [
                    "وريني مواعيد ليزر إزالة الشعر - إبط يوم 2026-10-13",
                    "الأول",
                    "لا 4",
                ],
                check_ambiguity,
            )
        )

        def check_fresh(turns):
            final = turns[-1]
            op = final["operation"]
            state = final["state"]
            assert op.get("fresh_task") is True, op
            assert op.get("active_task_relationship") == "replace", op
            assert op.get("fresh_task_explicit_fields") == ["service"], op
            assert state and state["service_id"] == service_ids["ليزر إزالة الشعر - إبط"]
            assert date_of(state) is None
            assert time_of(state) is None
            assert not final["appointment_changed"]

        results.append(
            run_case(
                connection,
                ws_id,
                patient_id,
                "fresh_task_replacement",
                [
                    "عايزة أحجز PRP للبشرة يوم 2026-10-17",
                    "خلاص سيب PRP، عايزة أحجز ليزر إزالة الشعر - إبط بدلها",
                ],
                check_fresh,
            )
        )

        def check_same_task(turns):
            final = turns[-1]
            op = final["operation"]
            state = final["state"]
            assert op.get("fresh_task") is False, op
            assert op.get("active_task_relationship") == "continue", op
            if state:
                assert state["service_id"] == service_ids["ميزوثيرابي للشعر"]
                assert date_of(state) == "2026-10-17"
                assert time_of(state) == "17:00"
            else:
                assert final["appointment_changed"], final

        results.append(
            run_case(
                connection,
                ws_id,
                patient_id,
                "same_task_service_control",
                [
                    "عايزة أحجز PRP للبشرة يوم 2026-10-17 الساعة 5 مع هالة مصطفى",
                    "لا قصدي ميزوثيرابي للشعر",
                ],
                check_same_task,
            )
        )

        results.append(run_missing_date_reschedule(connection, ws_id, patient_id))

        def check_side_question(turns):
            before = turns[0]["state"]
            side = turns[1]["state"]
            final = turns[-1]
            assert before and side
            assert before["service_id"] == side["service_id"]
            assert date_of(before) == date_of(side)
            if final["state"]:
                assert date_of(final["state"]) == "2026-10-17"
                assert time_of(final["state"]) == "17:00"
            else:
                assert final["appointment_changed"]

        results.append(
            run_case(
                connection,
                ws_id,
                patient_id,
                "after_side_question",
                [
                    "عايزة أحجز PRP للبشرة يوم 2026-10-17 الساعة 3",
                    "السعر كام؟",
                    "لا خليها 5",
                ],
                check_side_question,
            )
        )

        failed = [item for item in results if item["status"] != "PASS"]
        OUT.write_text(
            json.dumps(
                {
                    "head": "correction semantics branch",
                    "generated_at": datetime.now(UTC).isoformat(),
                    "pass_count": len(results) - len(failed),
                    "fail_count": len(failed),
                    "results": results,
                },
                ensure_ascii=False,
                indent=2,
            ),
            encoding="utf-8",
        )
        print(
            "SUMMARY",
            json.dumps(
                {
                    "pass": len(results) - len(failed),
                    "fail": len(failed),
                    "failed": [item["name"] for item in failed],
                },
                ensure_ascii=False,
            ),
            flush=True,
        )
        if failed:
            raise SystemExit(1)
    finally:
        if outer.is_active:
            outer.rollback()
        connection.close()
        engine.dispose()


if __name__ == "__main__":
    main()
