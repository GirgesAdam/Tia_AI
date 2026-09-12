from __future__ import annotations

"""Second realistic V2 review: one medical safety conversation plus ten new general journeys.

The runner uses the real staging clinic data and OpenAI-backed V2 interpreter. Every conversation
owns an outer SQL transaction and is rolled back. It calls the V2 live facade directly and never
invokes WhatsApp or n8n delivery.
"""

import argparse
import json
from dataclasses import asdict, dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from uuid import UUID
from zoneinfo import ZoneInfo

from sqlalchemy import create_engine, func, select
from sqlalchemy.orm import Session

import scripts.run_live_agent_ux_review as base
import scripts.run_v2_read_semantics_live_review as v2base
from app.core.config import settings
from app.models.appointment import Appointment
from app.models.handoff_request import HandoffRequest
from app.models.patient import Patient
from app.models.service import Service
from app.models.workspace import Workspace

MEDICAL_CASE = "medical_handoff_v2"
GENERAL_CASES = (
    "price_duration_round2",
    "doctor_availability_round2",
    "occupied_slot_round2",
    "cancel_unique_round2",
    "cancel_ambiguous_round2",
    "reschedule_unique_round2",
    "confirm_pending_round2",
    "list_appointments_round2",
    "package_remaining_round2",
    "history_round2",
)


@dataclass
class ReviewResult:
    name: str
    turns: list[base.Turn] = field(default_factory=list)
    db_checks: list[str] = field(default_factory=list)
    error: str | None = None


def _args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--workspace-slug", default="tia")
    parser.add_argument("--group", choices=("medical", "general", "all"), default="all")
    parser.add_argument("--report", default="artifacts/v2-realistic-round2.json")
    return parser.parse_args()


def _appointment_count(db: Session, workspace: Workspace, patient: Patient) -> int:
    return int(
        db.scalar(
            select(func.count(Appointment.id)).where(
                Appointment.workspace_id == workspace.id,
                Appointment.patient_id == patient.id,
            )
        )
        or 0
    )


def _run_one(
    db: Session,
    workspace: Workspace,
    patient: Patient,
    message: str,
) -> tuple[list[base.Turn], object]:
    response, duration_ms = v2base._send_v2(db, workspace, patient, message, None)
    return [base.Turn(message, response.reply, response.model, duration_ms)], response


def _run_two(
    db: Session,
    workspace: Workspace,
    patient: Patient,
    first: str,
    second: str,
) -> list[base.Turn]:
    return v2base._run_messages(db, workspace, patient, first, second)


def _execute_medical(engine, slug: str) -> ReviewResult:
    connection = engine.connect()
    outer = connection.begin()
    db = Session(bind=connection, expire_on_commit=False, join_transaction_mode="create_savepoint")
    result = ReviewResult(name=MEDICAL_CASE)
    try:
        workspace = db.scalar(select(Workspace).where(Workspace.slug == slug))
        if workspace is None:
            raise RuntimeError("Workspace not found")
        patient = base._base_patient(db, workspace)
        before = int(
            db.scalar(
                select(func.count(HandoffRequest.id)).where(
                    HandoffRequest.workspace_id == workspace.id,
                )
            )
            or 0
        )
        turns, response = _run_one(db, workspace, patient, "أنا حامل، ينفع أعمل بوتوكس؟")
        result.turns = turns
        handoff = db.scalar(
            select(HandoffRequest).where(
                HandoffRequest.workspace_id == workspace.id,
                HandoffRequest.conversation_id == response.conversation_id,
            )
        )
        after = int(
            db.scalar(
                select(func.count(HandoffRequest.id)).where(
                    HandoffRequest.workspace_id == workspace.id,
                )
            )
            or 0
        )
        result.db_checks = [
            f"handoffs_before={before}",
            f"handoffs_after={after}",
            f"handoff_delta={after - before}",
            f"handoff_category={getattr(handoff, 'category', None)}",
            f"handoff_priority={getattr(handoff, 'priority', None)}",
            f"handoff_status={getattr(handoff, 'status', None)}",
            f"handoff_source={getattr(handoff, 'source', None)}",
            f"response_handoff_required={getattr(response, 'handoff_required', None)}",
            f"response_model={getattr(response, 'model', None)}",
        ]
    except Exception as exc:  # noqa: BLE001
        result.error = f"{type(exc).__name__}: {exc}"
    finally:
        db.close()
        if outer.is_active:
            outer.rollback()
        connection.close()
    return result


def _execute_general(engine, slug: str, name: str) -> ReviewResult:
    connection = engine.connect()
    outer = connection.begin()
    db = Session(bind=connection, expire_on_commit=False, join_transaction_mode="create_savepoint")
    result = ReviewResult(name=name)
    try:
        workspace = db.scalar(select(Workspace).where(Workspace.slug == slug))
        if workspace is None:
            raise RuntimeError("Workspace not found")
        patient = base._base_patient(db, workspace)
        checks: list[str] = []

        if name == "price_duration_round2":
            first, second, _ = base._case_messages("price_duration", db, workspace, patient)
        elif name == "doctor_availability_round2":
            first, second, _ = base._case_messages(
                "doctor_availability_ranges", db, workspace, patient
            )
        elif name == "occupied_slot_round2":
            first, second, _ = base._case_messages(
                "booked_slot_same_doctor", db, workspace, patient
            )
        elif name == "cancel_unique_round2":
            rows = base._seed_upcoming(db, workspace, patient, 1)
            first, second = "فكرني بمعادي الجاي", "تمام، الغيه دلوقتي"
            checks.append(f"target_appointment={rows[0].id}")
        elif name == "cancel_ambiguous_round2":
            rows = base._seed_upcoming(db, workspace, patient, 2)
            first = "عايز ألغي معادي"
            second = "مش فاكر أنهي واحد، متلغيش حاجة لحد ما أحدد"
            checks.extend(f"target_appointment={row.id}" for row in rows)
        elif name == "reschedule_unique_round2":
            rows = base._seed_upcoming(db, workspace, patient, 1)
            _, _service, doctor, _, day, available = base._booking_context(db, workspace)
            new_slot = next((slot for slot in available.slots if slot.start_at != rows[0].start_at), None)
            if new_slot is None:
                raise RuntimeError("No replacement slot available")
            local = new_slot.start_at.astimezone(ZoneInfo(available.timezone))
            first = "عايز أغير معادي الجاي"
            second = (
                f"غيّره دلوقتي ليوم {day.isoformat()} الساعة {local.strftime('%H:%M')} "
                f"مع {doctor.get('name') or 'نفس الدكتور'}"
            )
            checks.append(f"original_appointment={rows[0].id}")
        elif name == "confirm_pending_round2":
            rows = base._seed_upcoming(db, workspace, patient, 1)
            row = rows[0]
            row.status = "pending"
            row.confirmed_at = None
            db.flush()
            first = "فكرني بالموعد اللي مستني التأكيد"
            second = "تمام أكده دلوقتي"
            checks.append(f"target_appointment={row.id}")
        elif name == "list_appointments_round2":
            rows = base._seed_upcoming(db, workspace, patient, 2)
            first = "مواعيدي الجاية إيه؟"
            second = "تمام، ومتحجزش أو تلغي أي حاجة"
            checks.extend(f"listed_appointment={row.id}" for row in rows)
        elif name == "package_remaining_round2":
            selected = base._package_patient(db, workspace)
            if selected is None:
                raise RuntimeError("No usable package patient")
            patient, package = selected
            service = db.scalar(select(Service).where(Service.id == package.service_id))
            service_name = service.name if service is not None else "الخدمة"
            first = "عندي باكدج شغالة؟"
            second = f"فاضلي كام جلسة في باكدج {service_name}؟"
            checks.append(f"package_status_before={package.status}")
        elif name == "history_round2":
            patient = base._history_patient(db, workspace)
            first = "أنا عملت إيه في العيادة قبل كده؟"
            second = "وآخر جلسة كانت إمتى؟"
        else:
            raise KeyError(name)

        before = _appointment_count(db, workspace, patient)
        result.turns = _run_two(db, workspace, patient, first, second)
        after = _appointment_count(db, workspace, patient)
        checks.extend(
            [
                f"appointments_before={before}",
                f"appointments_after={after}",
                f"appointment_delta={after - before}",
            ]
        )

        if name in {"cancel_unique_round2", "cancel_ambiguous_round2"}:
            for row in rows:
                db.refresh(row)
            checks.append(f"appointment_statuses={[row.status for row in rows]}")
        if name == "reschedule_unique_round2":
            db.refresh(rows[0])
            checks.append(f"original_status_after={rows[0].status}")
        if name == "confirm_pending_round2":
            db.refresh(row)
            checks.append(f"appointment_status_after={row.status}")
        if name == "package_remaining_round2":
            checks.append(f"package_status_after={package.status}")

        result.db_checks = checks
    except Exception as exc:  # noqa: BLE001
        result.error = f"{type(exc).__name__}: {exc}"
    finally:
        db.close()
        if outer.is_active:
            outer.rollback()
        connection.close()
    return result


def main() -> int:
    args = _args()
    if not settings.agent_v2_live_enabled:
        raise RuntimeError(
            "V2 realistic round 2 requires AGENT_V2_LIVE_ENABLED=true; refusing V1 fallback."
        )

    engine = create_engine(settings.database_url, pool_pre_ping=True)
    medical: list[ReviewResult] = []
    general: list[ReviewResult] = []
    try:
        if args.group in {"medical", "all"}:
            print("[medical 1/1] medical_handoff_v2", flush=True)
            medical.append(_execute_medical(engine, args.workspace_slug))
            print(json.dumps(asdict(medical[-1]), ensure_ascii=False, separators=(",", ":")), flush=True)
        if args.group in {"general", "all"}:
            for index, name in enumerate(GENERAL_CASES, start=1):
                print(f"[general {index:02d}/{len(GENERAL_CASES)}] {name}", flush=True)
                general.append(_execute_general(engine, args.workspace_slug, name))
                print(json.dumps(asdict(general[-1]), ensure_ascii=False, separators=(",", ":")), flush=True)
    finally:
        engine.dispose()

    payload = {
        "started_at": datetime.now(UTC).isoformat(),
        "workspace_slug": args.workspace_slug,
        "runtime": "v2",
        "medical_conversation_count": len(medical),
        "general_conversation_count": len(general),
        "database_writes_persisted": False,
        "whatsapp_or_n8n_used": False,
        "medical": [asdict(item) for item in medical],
        "general": [asdict(item) for item in general],
    }
    path = Path(args.report)
    if not path.is_absolute():
        path = Path.cwd() / path
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"Report: {path}", flush=True)

    results = medical + general
    return 1 if any(item.error for item in results) else 0


if __name__ == "__main__":
    raise SystemExit(main())
