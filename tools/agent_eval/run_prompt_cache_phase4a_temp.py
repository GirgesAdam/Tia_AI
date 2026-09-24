from __future__ import annotations

import argparse
import json
from datetime import UTC, datetime, timedelta
from zoneinfo import ZoneInfo

from app.agents import model_provider
from app.core.config import settings
from app.integrations.clinic.base import AvailabilityRequest, ClinicCapability
from app.integrations.clinic.registry import get_clinic_adapter
from app.models.patient import Patient
from app.models.pulse_billing import PatientPulsePack
from app.models.workspace import Workspace
from app.services.pulse_billing import list_patient_pulse_balances
from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session

from tools.agent_eval.harness import assert_demo_only, send_turn
from tools.agent_eval.run_batch_01 import (
    booking_context,
    branch_name,
    classify_issue,
    created_appointments,
    default_evaluation,
    doctor_name,
    local_slot,
    quiet_patient,
    run_case,
    run_messages,
    state_snapshot,
)
from tools.agent_eval.run_pulse_domain import (
    _appointment_ids,
    _appointment_pulse_artifacts,
    _created_appointments,
    _device_balance,
)


def _interpreter_metrics(turns) -> dict:
    all_calls = [call for turn in turns for call in turn.llm_calls]
    calls = [
        call
        for call in all_calls
        if call.get("operation") == "v2-turn-interpreter"
    ]
    return {
        "input": sum(int(c.get("input_tokens_actual") or 0) for c in calls),
        "write": sum(int(c.get("cache_write_tokens_actual") or 0) for c in calls),
        "read": sum(int(c.get("cached_tokens_actual") or 0) for c in calls),
        "uncached": sum(int(c.get("uncached_input_tokens_actual") or 0) for c in calls),
        "latency_ms": sum(int(c.get("latency_ms") or 0) for c in calls),
        "interpreter_calls": len(calls),
        "llm_calls": len(all_calls),
        "per_call": [
            {
                "input": c.get("input_tokens_actual"),
                "write": c.get("cache_write_tokens_actual"),
                "read": c.get("cached_tokens_actual"),
                "uncached": c.get("uncached_input_tokens_actual"),
                "latency_ms": c.get("latency_ms"),
            }
            for c in calls
        ],
    }


def _case_full_booking_available(db: Session, workspace: Workspace):
    patient = quiet_patient(db, workspace)
    catalog, service, doctor, branch_id, _, available = booking_context(db, workspace)
    date_text, time_text = local_slot(available, available.slots[0])
    before = state_snapshot(db, workspace, patient)
    turns = run_messages(
        db,
        workspace,
        patient,
        "full_booking_available",
        [
            f"عايزه احجز {service['name']}",
            f"في {branch_name(catalog, branch_id)}",
            f"مع دكتورة {doctor_name(doctor)}",
            f"يوم {date_text} الساعة {time_text}",
            "تمام احجزي",
        ],
    )
    after = state_snapshot(db, workspace, patient)
    created = created_appointments(before, after)
    ok = (
        len(created) == 1
        and created[0]["service_id"] == str(service["id"])
        and created[0]["doctor_id"] == str(doctor["id"])
        and created[0]["branch_id"] == branch_id
    )
    issues = classify_issue(
        ok,
        severity="P1",
        title="Full booking final state incorrect",
        detail=f"Expected one grounded appointment, got {len(created)}.",
    )
    return (
        "full_booking_available",
        "booking",
        "Canonical five-turn full booking using a currently bookable service.",
        turns,
        before,
        after,
        {
            "created_appointments": created,
            "exactly_one_correct_booking": ok,
            "service_name": service["name"],
        },
        default_evaluation(action_ok=ok, db_ok=ok),
        issues,
    )


def run_full_booking(engine) -> int:
    row = run_case(engine, "tia", _case_full_booking_available)
    payload = {
        "scenario": row.id,
        "issues": row.issues,
        "verification": row.db_verification,
        **_interpreter_metrics(row.turns),
    }
    print("GATE_C=" + json.dumps(payload, ensure_ascii=False, sort_keys=True), flush=True)
    return 0 if not row.issues else 2


def _candela_patient(db: Session, workspace: Workspace) -> Patient:
    ids = list(
        db.scalars(
            select(PatientPulsePack.patient_id)
            .where(
                PatientPulsePack.workspace_id == workspace.id,
                PatientPulsePack.device_key == "candela_gentle",
                PatientPulsePack.status == "active",
            )
            .distinct()
            .limit(100)
        )
    )
    for patient_id in ids:
        patient = db.scalar(
            select(Patient).where(
                Patient.workspace_id == workspace.id,
                Patient.id == patient_id,
                Patient.status != "blocked",
            )
        )
        if patient is None:
            continue
        balances = list_patient_pulse_balances(
            db,
            workspace_id=workspace.id,
            patient_id=patient.id,
        )
        if any(
            row.device_key == "candela_gentle" and row.pulses_remaining > 0
            for row in balances
        ):
            return patient
    raise RuntimeError("No Demo patient with active Candela Pulse balance.")


def _candela_underarm_slot(db: Session, workspace: Workspace):
    from app.agents.clinic_grounding import build_clinic_catalog
    from tools.agent_eval.harness import active_branch_id, service_by_slug

    catalog = build_clinic_catalog(db, workspace)
    branch_id = active_branch_id(catalog)
    db_service = service_by_slug(db, workspace, "laser-hair-removal-underarm")
    service = next(
        row
        for row in catalog.get("services", [])
        if isinstance(row, dict)
        and str(row.get("id")) == str(db_service.id)
    )
    doctors = [
        row
        for row in catalog.get("doctors", [])
        if isinstance(row, dict)
        and str(service["id"]) in {str(v) for v in (row.get("service_ids") or [])}
    ]
    adapter = get_clinic_adapter(db=db, workspace=workspace)
    adapter.require_capability(ClinicCapability.AVAILABILITY_READ)
    today = datetime.now(UTC).date()
    for doctor in doctors:
        scheduled = {
            str(v)
            for v in (
                doctor.get("scheduled_branch_ids")
                or doctor.get("branch_ids")
                or []
            )
            if v
        }
        if scheduled and branch_id not in scheduled:
            continue
        for offset in range(1, 36):
            day = today + timedelta(days=offset)
            available = adapter.get_availability(
                AvailabilityRequest(
                    branch_id=branch_id,
                    service_id=str(service["id"]),
                    booking_date=day,
                    doctor_id=str(doctor["id"]),
                    laser_device_key="candela_gentle",
                )
            )
            if available.slots:
                return service, doctor, available, available.slots[0]
    raise RuntimeError("No bookable Candela underarm slot in Demo window.")


def run_pulse_smoke(engine) -> int:
    connection = engine.connect()
    outer = connection.begin()
    db = Session(
        bind=connection,
        expire_on_commit=False,
        join_transaction_mode="create_savepoint",
    )
    try:
        workspace = db.scalar(select(Workspace).where(Workspace.slug == "tia"))
        if workspace is None:
            raise RuntimeError("Demo workspace not found.")
        assert_demo_only(workspace)
        patient = _candela_patient(db, workspace)
        service, doctor, available, slot = _candela_underarm_slot(db, workspace)
        local = slot.start_at.astimezone(ZoneInfo(available.timezone))
        before_ids = _appointment_ids(db, workspace, patient)
        before_balance = _device_balance(
            db,
            workspace,
            patient,
            device_key="candela_gentle",
        )

        response1, turn1 = send_turn(
            db,
            workspace,
            patient,
            "phase4a_pulse_smoke",
            1,
            "عندي Pulses وعايزة أحجز ليزر الإبط على كانديلا",
            None,
        )
        _, turn2 = send_turn(
            db,
            workspace,
            patient,
            "phase4a_pulse_smoke",
            2,
            (
                f"يوم {local.date().isoformat()} الساعة {local.strftime('%H:%M')} "
                f"مع دكتورة {doctor_name(doctor)}"
            ),
            response1.conversation_id,
        )

        created = _created_appointments(
            db,
            workspace,
            patient,
            before_ids=before_ids,
        )
        appointment = created[0] if len(created) == 1 else None
        after_balance = _device_balance(
            db,
            workspace,
            patient,
            device_key="candela_gentle",
        )
        artifacts = _appointment_pulse_artifacts(db, workspace, appointment)
        ok = (
            appointment is not None
            and appointment.laser_device_key == "candela_gentle"
            and appointment.billing_context == "standard"
            and before_balance == after_balance
            and artifacts == {"usages": 0, "settlements": 0}
        )
        turns = [turn1, turn2]
        payload = {
            "ok": ok,
            "appointment_created": appointment is not None,
            "device": (
                appointment.laser_device_key if appointment is not None else None
            ),
            "billing_context": (
                appointment.billing_context if appointment is not None else None
            ),
            "balance_before": before_balance,
            "balance_after": after_balance,
            "pulse_artifacts": artifacts,
            **_interpreter_metrics(turns),
        }
        print(
            "PULSE_SMOKE="
            + json.dumps(payload, ensure_ascii=False, sort_keys=True),
            flush=True,
        )
        return 0 if ok else 2
    finally:
        db.close()
        if outer.is_active:
            outer.rollback()
        connection.close()


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "gate",
        choices=("full-booking", "full-booking-implicit", "pulse-smoke"),
    )
    ns = parser.parse_args()
    engine = create_engine(settings.database_url, pool_pre_ping=True)
    if ns.gate == "full-booking":
        return run_full_booking(engine)
    if ns.gate == "full-booking-implicit":
        model_provider._cached_openai_model.cache_clear()
        model_provider._supports_explicit_prompt_cache = lambda _model: False
        return run_full_booking(engine)
    return run_pulse_smoke(engine)


if __name__ == "__main__":
    raise SystemExit(main())
