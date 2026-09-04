from __future__ import annotations

"""Five NEW high-risk live conversations for manual production review.

No quality PASS/FAIL labels are produced. Each case runs against the real agent and
staging PostgreSQL adapter inside an outer transaction that is always rolled back.
Previously accepted UX cases are intentionally not repeated here.
"""

import argparse
import json
from dataclasses import asdict
from datetime import UTC, datetime, timedelta
from pathlib import Path
from uuid import UUID
from zoneinfo import ZoneInfo

from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session

from app.agents.clinic_grounding import build_clinic_catalog
from app.core.config import settings
from app.integrations.clinic.base import AvailabilityRequest, ClinicCapability
from app.integrations.clinic.registry import get_clinic_adapter
from app.models.appointment import Appointment
from app.models.patient import Patient
from app.models.service import Service
from app.models.workspace import Workspace
from scripts.run_live_agent_ux_review import _base_patient, _booking_context, _seed_upcoming, _send


CASES = (
    "booking_change_doctor",
    "reschedule_change_doctor",
    "confirm_ambiguous_pending",
    "medical_interrupt_booking",
    "followup_vague_then_exact",
)


def _args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--workspace-slug", default="tia")
    parser.add_argument("--report", default="artifacts/live-agent-production-risks.json")
    return parser.parse_args()


def _alternate_doctor(
    db: Session,
    workspace: Workspace,
    *,
    service_id: str,
    exclude_doctor_id: str,
) -> tuple[dict[str, object], object, object]:
    catalog = build_clinic_catalog(db, workspace)
    doctors = [row for row in catalog.get("doctors", []) if isinstance(row, dict)]
    adapter = get_clinic_adapter(db=db, workspace=workspace)
    adapter.require_capability(ClinicCapability.AVAILABILITY_READ)
    branch_id = str(workspace.primary_branch_id or "")
    if not branch_id:
        raise RuntimeError("Single-location staging workspace has no primary branch")
    today = datetime.now(UTC).date()

    for doctor in doctors:
        doctor_id = str(doctor.get("id") or "")
        if not doctor_id or doctor_id == exclude_doctor_id:
            continue
        if service_id not in {str(value) for value in (doctor.get("service_ids") or [])}:
            continue
        for offset in range(1, 36):
            day = today + timedelta(days=offset)
            available = adapter.get_availability(
                AvailabilityRequest(
                    branch_id=branch_id,
                    service_id=service_id,
                    booking_date=day,
                    doctor_id=doctor_id,
                )
            )
            if available.slots:
                return doctor, day, available
    raise RuntimeError("No second compatible doctor with future availability in 35 days")


def _appointment_snapshot(db: Session, workspace: Workspace, patient: Patient) -> list[dict[str, object]]:
    rows = list(
        db.scalars(
            select(Appointment)
            .where(Appointment.workspace_id == workspace.id, Appointment.patient_id == patient.id)
            .order_by(Appointment.start_at.asc())
        )
    )
    return [
        {
            "id": str(row.id),
            "status": row.status,
            "doctor_id": str(row.doctor_id),
            "service_id": str(row.service_id),
            "start_at": row.start_at.isoformat(),
        }
        for row in rows
    ]


def _run_case(engine, slug: str, name: str) -> dict[str, object]:
    connection = engine.connect()
    outer = connection.begin()
    db = Session(bind=connection, expire_on_commit=False, join_transaction_mode="create_savepoint")
    turns = []
    facts: dict[str, object] = {}
    error: str | None = None
    try:
        workspace = db.scalar(select(Workspace).where(Workspace.slug == slug))
        if workspace is None:
            raise RuntimeError("Workspace not found")
        patient = _base_patient(db, workspace)
        conversation_id = None

        if name == "booking_change_doctor":
            _, service, original_doctor, _, day, _ = _booking_context(db, workspace)
            service_id = str(service["id"])
            original_doctor_id = str(original_doctor["id"])
            target, target_day, target_available = _alternate_doctor(
                db,
                workspace,
                service_id=service_id,
                exclude_doctor_id=original_doctor_id,
            )
            service_name = str(service.get("name") or "الخدمة")
            original_name = str(original_doctor.get("name") or "الدكتور الأول")
            target_name = str(target.get("name") or "الدكتور التاني")
            messages = (
                f"عايز أحجز {service_name} مع {original_name} يوم {day.isoformat()}، إيه المتاح؟",
                f"لا خلّيه مع {target_name} يوم {target_day.isoformat()}، وريني المتاح ومتحجزش حاجة دلوقتي",
            )
            facts.update({"expected_target_doctor_id": str(target["id"]), "expected_target_doctor": target_name})

        elif name == "reschedule_change_doctor":
            seeded = _seed_upcoming(db, workspace, patient, 1)[0]
            service = db.scalar(select(Service).where(Service.id == seeded.service_id))
            target, target_day, target_available = _alternate_doctor(
                db,
                workspace,
                service_id=str(seeded.service_id),
                exclude_doctor_id=str(seeded.doctor_id),
            )
            target_name = str(target.get("name") or "الدكتور التاني")
            local = target_available.slots[0].start_at.astimezone(ZoneInfo(target_available.timezone))
            messages = (
                f"عايز أغيّر معادي الجاي مع {service.name if service else 'الخدمة'} وأخليه مع {target_name}",
                f"تمام غيّره دلوقتي ليوم {target_day.isoformat()} الساعة {local.strftime('%H:%M')} مع {target_name}",
            )
            facts.update({
                "original_appointment_id": str(seeded.id),
                "original_doctor_id": str(seeded.doctor_id),
                "expected_target_doctor_id": str(target["id"]),
                "expected_target_doctor": target_name,
            })

        elif name == "confirm_ambiguous_pending":
            seeded = _seed_upcoming(db, workspace, patient, 2)
            for row in seeded:
                row.status = "pending"
                row.confirmed_at = None
            db.flush()
            messages = (
                "أكدلي معادي الجاي",
                "أنا عندي أكتر من ميعاد ومش فاكر أنهي واحد، متأكدش حاجة لحد ما أحدد",
            )
            facts["seeded_pending_appointment_ids"] = [str(row.id) for row in seeded]

        elif name == "medical_interrupt_booking":
            _, service, doctor, _, day, _ = _booking_context(db, workspace)
            messages = (
                f"عايز أحجز {service.get('name') or 'الخدمة'} مع {doctor.get('name') or 'الدكتور'} يوم {day.isoformat()}، إيه المتاح؟",
                "بس أنا حامل، هل الخدمة دي آمنة ليا ولا أستنى؟",
            )

        elif name == "followup_vague_then_exact":
            tomorrow = datetime.now(ZoneInfo(workspace.timezone or "Africa/Cairo")).date() + timedelta(days=1)
            messages = (
                "فكرني أكلم العيادة كمان شوية",
                f"قصدي بكرة {tomorrow.isoformat()} الساعة 17:00",
            )

        else:
            raise KeyError(name)

        for message in messages:
            response, duration_ms = _send(db, workspace, patient, message, conversation_id)
            conversation_id = response.conversation_id
            turns.append(
                {
                    "customer": message,
                    "assistant": response.reply,
                    "model": response.model,
                    "duration_ms": duration_ms,
                    "handoff_required": response.handoff_required,
                    "agent_paused": response.agent_paused,
                }
            )

        facts["appointments_after_conversation"] = _appointment_snapshot(db, workspace, patient)
    except Exception as exc:  # noqa: BLE001
        error = f"{type(exc).__name__}: {exc}"
    finally:
        db.close()
        if outer.is_active:
            outer.rollback()
        connection.close()

    return {
        "name": name,
        "execution_error": error,
        "turns": turns,
        "technical_facts": facts,
    }


def main() -> int:
    args = _args()
    engine = create_engine(settings.database_url, pool_pre_ping=True)
    results = []
    try:
        for index, name in enumerate(CASES, start=1):
            print(f"[{index:02d}/{len(CASES)}] {name}", flush=True)
            results.append(_run_case(engine, args.workspace_slug, name))
    finally:
        engine.dispose()

    payload = {
        "started_at": datetime.now(UTC).isoformat(),
        "workspace_slug": args.workspace_slug,
        "conversation_count": len(results),
        "quality_scoring": "manual_transcript_review",
        "previously_accepted_cases_rerun": False,
        "database_writes_persisted": False,
        "results": results,
    }
    path = Path(args.report)
    if not path.is_absolute():
        path = Path.cwd() / path
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"Report: {path}")
    return 1 if any(item["execution_error"] for item in results) else 0


if __name__ == "__main__":
    raise SystemExit(main())
