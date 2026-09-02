from __future__ import annotations

"""Focused SINGLE-BRANCH conversational regression test for booking.

This runner intentionally contains only five short conversations (2-3 turns each).\nThe customer never selects or mentions a branch; workspace.primary_branch_id is implicit.
It reuses the current run_agent_e2e_matrix helpers, including its availability
oracle, so the focused test follows the same fixture/source-of-truth setup as the
main matrix.

Coverage:
1) Underarm exact booking -> direct write, 15-minute duration.
2) Full-body exact booking -> direct write, 60-minute duration.
3) Booking options -> no write before selection, one write after selection.
4) Availability-only question -> never writes an appointment.
5) Booking options -> side pricing question -> resume and select -> one write.

All writes are rolled back by default.
"""

import argparse
import json
import sys
import traceback
from dataclasses import asdict, dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from time import perf_counter
from typing import Any
from uuid import UUID

from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session

from app.agents.clinic_grounding import build_clinic_catalog
from app.core.config import settings
from app.models.appointment import Appointment
from app.models.workspace import Workspace

# Reuse the existing matrix helpers so this focused runner automatically follows
# the same fixture lookup and availability source as the current local matrix.
from run_agent_e2e_matrix import (  # noqa: E402
    _appointments_for,
    _catalog_row,
    _find_future_slot,
    _fixture_patients,
    _format_local_slot,
    _send,
)


@dataclass
class TurnResult:
    turn: int
    message: str
    reply: str
    duration_ms: int
    new_appointment_ids: list[str] = field(default_factory=list)


@dataclass
class CaseResult:
    name: str
    status: str
    duration_ms: int
    turns: list[TurnResult] = field(default_factory=list)
    details: dict[str, Any] = field(default_factory=dict)
    error: str | None = None


@dataclass
class FocusReport:
    started_at: str
    workspace_id: str
    workspace_slug: str
    rollback: bool
    results: list[CaseResult] = field(default_factory=list)

    def counts(self) -> dict[str, int]:
        counts = {"PASS": 0, "FAIL": 0}
        for row in self.results:
            counts[row.status] = counts.get(row.status, 0) + 1
        return counts


def _new_rows(
    db: Session,
    workspace: Workspace,
    patient,
    before_ids: set[UUID],
) -> list[Appointment]:
    return [
        row
        for row in _appointments_for(db, workspace, patient)
        if row.id not in before_ids
    ]


def _send_turn(
    *,
    db: Session,
    workspace: Workspace,
    patient,
    message: str,
    conversation_id: UUID | None,
    before_ids: set[UUID],
    turn_number: int,
):
    response, duration_ms = _send(
        db,
        workspace,
        patient,
        message,
        conversation_id,
    )
    created = _new_rows(db, workspace, patient, before_ids)
    return response, TurnResult(
        turn=turn_number,
        message=message,
        reply=response.reply,
        duration_ms=duration_ms,
        new_appointment_ids=[str(row.id) for row in created],
    )


def _record(report: FocusReport, result: CaseResult) -> None:
    report.results.append(result)
    print(f"[{result.status}] {result.name} ({result.duration_ms} ms)")
    if result.error:
        print(f"       {result.error}")



def _primary_branch_row(workspace: Workspace, catalog: dict[str, Any]) -> dict[str, Any]:
    branches = list(catalog.get("branches") or [])
    if workspace.primary_branch_id is not None:
        for row in branches:
            if str(row.get("id")) == str(workspace.primary_branch_id):
                return row
        raise RuntimeError(
            f"workspace.primary_branch_id={workspace.primary_branch_id} was not found in the active catalog."
        )
    if len(branches) == 1:
        return branches[0]
    raise RuntimeError(
        "Single-branch focus test requires workspace.primary_branch_id "
        "or exactly one active catalog branch."
    )


def _doctor_name(row: dict[str, Any]) -> str:
    return str(
        row.get("name")
        or row.get("display_name")
        or row.get("full_name")
        or ""
    ).strip()


def _find_doctor_and_slot(
    db: Session,
    workspace: Workspace,
    catalog: dict[str, Any],
    *,
    branch_id: UUID,
    service_id: UUID,
):
    errors: list[str] = []
    for doctor in catalog.get("doctors") or []:
        doctor_id = doctor.get("id")
        name = _doctor_name(doctor)
        if not doctor_id or not name:
            continue
        try:
            booking_date, timezone_name, slot = _find_future_slot(
                db,
                workspace,
                branch_id=branch_id,
                service_id=service_id,
                doctor_id=UUID(str(doctor_id)),
            )
            return doctor, booking_date, timezone_name, slot
        except Exception as exc:  # noqa: BLE001
            errors.append(f"{name}: {exc}")
    raise RuntimeError(
        "Could not find a doctor with an available slot for the service "
        f"in the primary branch. Tried: {errors[:6]}"
    )


def _run_underarm_exact(
    *,
    db: Session,
    workspace: Workspace,
    catalog: dict[str, Any],
    patient,
) -> CaseResult:
    started = perf_counter()
    turns: list[TurnResult] = []
    try:
        underarm = _catalog_row(catalog, "services", "ليزر إزالة الشعر - إبط")
        primary_branch = _primary_branch_row(workspace, catalog)
        doctor, booking_date, timezone_name, slot = _find_doctor_and_slot(
            db,
            workspace,
            catalog,
            branch_id=UUID(str(primary_branch["id"])),
            service_id=UUID(str(underarm["id"])),
        )
        doctor_name = _doctor_name(doctor)
        date_text, time_text = _format_local_slot(slot, timezone_name)

        before_ids = {row.id for row in _appointments_for(db, workspace, patient)}

        first, turn1 = _send_turn(
            db=db,
            workspace=workspace,
            patient=patient,
            message=(
                f"عايز احجز ليزر ابط مع {doctor_name} "
                f"يوم {date_text} الساعة {time_text}"
            ),
            conversation_id=None,
            before_ids=before_ids,
            turn_number=1,
        )
        turns.append(turn1)

        created_after_first = _new_rows(db, workspace, patient, before_ids)

        _, turn2 = _send_turn(
            db=db,
            workspace=workspace,
            patient=patient,
            message="تمام، وسعر الجلسة كام؟",
            conversation_id=first.conversation_id,
            before_ids=before_ids,
            turn_number=2,
        )
        turns.append(turn2)

        created_final = _new_rows(db, workspace, patient, before_ids)
        newest = created_final[-1] if created_final else None

        ok = (
            len(created_after_first) == 1
            and len(created_final) == 1
            and newest is not None
            and newest.service_id == UUID(str(underarm["id"]))
            and newest.duration_minutes == 15
        )
        return CaseResult(
            name="underarm_exact_direct_write",
            status="PASS" if ok else "FAIL",
            duration_ms=int((perf_counter() - started) * 1000),
            turns=turns,
            details={
                "requested_date": date_text,
                "requested_time": time_text,
                "created_after_turn1": len(created_after_first),
                "created_final": len(created_final),
                "created_appointment_id": str(newest.id) if newest else None,
                "duration_minutes": newest.duration_minutes if newest else None,
            },
            error=None if ok else (
                "Expected the exact booking request to create exactly one "
                "15-minute underarm appointment on turn 1, with no extra write on turn 2."
            ),
        )
    except Exception as exc:  # noqa: BLE001
        return CaseResult(
            name="underarm_exact_direct_write",
            status="FAIL",
            duration_ms=int((perf_counter() - started) * 1000),
            turns=turns,
            error=f"{type(exc).__name__}: {exc}",
        )


def _run_full_body_exact(
    *,
    db: Session,
    workspace: Workspace,
    catalog: dict[str, Any],
    patient,
) -> CaseResult:
    started = perf_counter()
    turns: list[TurnResult] = []
    try:
        service = _catalog_row(
            catalog,
            "services",
            "ليزر إزالة الشعر - جسم كامل سيدات",
        )
        primary_branch = _primary_branch_row(workspace, catalog)
        doctor, booking_date, timezone_name, slot = _find_doctor_and_slot(
            db,
            workspace,
            catalog,
            branch_id=UUID(str(primary_branch["id"])),
            service_id=UUID(str(service["id"])),
        )
        doctor_name = _doctor_name(doctor)
        date_text, time_text = _format_local_slot(slot, timezone_name)

        before_ids = {row.id for row in _appointments_for(db, workspace, patient)}

        first, turn1 = _send_turn(
            db=db,
            workspace=workspace,
            patient=patient,
            message=(
                f"عايز احجز ليزر جسم كامل سيدات مع {doctor_name} "
                f"يوم {date_text} الساعة {time_text}"
            ),
            conversation_id=None,
            before_ids=before_ids,
            turn_number=1,
        )
        turns.append(turn1)

        created_after_first = _new_rows(db, workspace, patient, before_ids)

        _, turn2 = _send_turn(
            db=db,
            workspace=workspace,
            patient=patient,
            message="تمام شكرا",
            conversation_id=first.conversation_id,
            before_ids=before_ids,
            turn_number=2,
        )
        turns.append(turn2)

        created_final = _new_rows(db, workspace, patient, before_ids)
        newest = created_final[-1] if created_final else None

        ok = (
            len(created_after_first) == 1
            and len(created_final) == 1
            and newest is not None
            and newest.service_id == UUID(str(service["id"]))
            and newest.duration_minutes == 60
        )
        return CaseResult(
            name="full_body_exact_direct_write",
            status="PASS" if ok else "FAIL",
            duration_ms=int((perf_counter() - started) * 1000),
            turns=turns,
            details={
                "requested_date": date_text,
                "requested_time": time_text,
                "created_after_turn1": len(created_after_first),
                "created_final": len(created_final),
                "created_appointment_id": str(newest.id) if newest else None,
                "duration_minutes": newest.duration_minutes if newest else None,
            },
            error=None if ok else (
                "Expected the exact booking request to create exactly one "
                "60-minute full-body appointment on turn 1."
            ),
        )
    except Exception as exc:  # noqa: BLE001
        return CaseResult(
            name="full_body_exact_direct_write",
            status="FAIL",
            duration_ms=int((perf_counter() - started) * 1000),
            turns=turns,
            error=f"{type(exc).__name__}: {exc}",
        )


def _run_options_then_select(
    *,
    db: Session,
    workspace: Workspace,
    catalog: dict[str, Any],
    patient,
) -> CaseResult:
    started = perf_counter()
    turns: list[TurnResult] = []
    try:
        service = _catalog_row(catalog, "services", "ليزر إزالة الشعر - إبط")
        primary_branch = _primary_branch_row(workspace, catalog)
        doctor, booking_date, _, _ = _find_doctor_and_slot(
            db,
            workspace,
            catalog,
            branch_id=UUID(str(primary_branch["id"])),
            service_id=UUID(str(service["id"])),
        )
        doctor_name = _doctor_name(doctor)
        date_text = str(booking_date)

        before_ids = {row.id for row in _appointments_for(db, workspace, patient)}

        first, turn1 = _send_turn(
            db=db,
            workspace=workspace,
            patient=patient,
            message=(
                f"عايز احجز ليزر ابط مع {doctor_name} يوم {date_text}، "
                "وريني المواعيد المتاحة"
            ),
            conversation_id=None,
            before_ids=before_ids,
            turn_number=1,
        )
        turns.append(turn1)
        created_after_first = _new_rows(db, workspace, patient, before_ids)

        _, turn2 = _send_turn(
            db=db,
            workspace=workspace,
            patient=patient,
            message="اختار أول ميعاد متاح واحجزه",
            conversation_id=first.conversation_id,
            before_ids=before_ids,
            turn_number=2,
        )
        turns.append(turn2)

        created_final = _new_rows(db, workspace, patient, before_ids)
        newest = created_final[-1] if created_final else None

        ok = (
            len(created_after_first) == 0
            and len(created_final) == 1
            and newest is not None
            and newest.service_id == UUID(str(service["id"]))
            and newest.duration_minutes == 15
        )
        return CaseResult(
            name="options_then_select_one_write",
            status="PASS" if ok else "FAIL",
            duration_ms=int((perf_counter() - started) * 1000),
            turns=turns,
            details={
                "requested_date": date_text,
                "created_after_options": len(created_after_first),
                "created_after_selection": len(created_final),
                "created_appointment_id": str(newest.id) if newest else None,
                "duration_minutes": newest.duration_minutes if newest else None,
            },
            error=None if ok else (
                "Expected zero writes while showing booking options, then exactly "
                "one 15-minute appointment after selecting the first verified option."
            ),
        )
    except Exception as exc:  # noqa: BLE001
        return CaseResult(
            name="options_then_select_one_write",
            status="FAIL",
            duration_ms=int((perf_counter() - started) * 1000),
            turns=turns,
            error=f"{type(exc).__name__}: {exc}",
        )


def _run_availability_only_no_write(
    *,
    db: Session,
    workspace: Workspace,
    catalog: dict[str, Any],
    patient,
) -> CaseResult:
    started = perf_counter()
    turns: list[TurnResult] = []
    try:
        service = _catalog_row(catalog, "services", "ليزر إزالة الشعر - إبط")
        primary_branch = _primary_branch_row(workspace, catalog)
        doctor, booking_date, timezone_name, slot = _find_doctor_and_slot(
            db,
            workspace,
            catalog,
            branch_id=UUID(str(primary_branch["id"])),
            service_id=UUID(str(service["id"])),
        )
        doctor_name = _doctor_name(doctor)
        date_text, time_text = _format_local_slot(slot, timezone_name)

        before_ids = {row.id for row in _appointments_for(db, workspace, patient)}

        first, turn1 = _send_turn(
            db=db,
            workspace=workspace,
            patient=patient,
            message=(
                f"هل ليزر الابط مع {doctor_name} يوم {date_text} "
                f"الساعة {time_text} متاح؟ بس بسأل عن التوفر"
            ),
            conversation_id=None,
            before_ids=before_ids,
            turn_number=1,
        )
        turns.append(turn1)

        _, turn2 = _send_turn(
            db=db,
            workspace=workspace,
            patient=patient,
            message="تمام شكرا، مش هحجز دلوقتي",
            conversation_id=first.conversation_id,
            before_ids=before_ids,
            turn_number=2,
        )
        turns.append(turn2)

        created_final = _new_rows(db, workspace, patient, before_ids)
        ok = len(created_final) == 0
        return CaseResult(
            name="availability_only_never_writes",
            status="PASS" if ok else "FAIL",
            duration_ms=int((perf_counter() - started) * 1000),
            turns=turns,
            details={
                "requested_date": date_text,
                "requested_time": time_text,
                "created_final": len(created_final),
            },
            error=None if ok else (
                "Availability-only conversation unexpectedly created an appointment."
            ),
        )
    except Exception as exc:  # noqa: BLE001
        return CaseResult(
            name="availability_only_never_writes",
            status="FAIL",
            duration_ms=int((perf_counter() - started) * 1000),
            turns=turns,
            error=f"{type(exc).__name__}: {exc}",
        )


def _run_side_question_resume(
    *,
    db: Session,
    workspace: Workspace,
    catalog: dict[str, Any],
    patient,
) -> CaseResult:
    started = perf_counter()
    turns: list[TurnResult] = []
    try:
        service = _catalog_row(catalog, "services", "ليزر إزالة الشعر - جسم كامل سيدات")
        primary_branch = _primary_branch_row(workspace, catalog)
        doctor, booking_date, _, _ = _find_doctor_and_slot(
            db,
            workspace,
            catalog,
            branch_id=UUID(str(primary_branch["id"])),
            service_id=UUID(str(service["id"])),
        )
        doctor_name = _doctor_name(doctor)
        date_text = str(booking_date)

        before_ids = {row.id for row in _appointments_for(db, workspace, patient)}

        first, turn1 = _send_turn(
            db=db,
            workspace=workspace,
            patient=patient,
            message=(
                f"عايز احجز ليزر جسم كامل سيدات مع {doctor_name} "
                f"يوم {date_text}، إيه المواعيد؟"
            ),
            conversation_id=None,
            before_ids=before_ids,
            turn_number=1,
        )
        turns.append(turn1)
        created_after_first = _new_rows(db, workspace, patient, before_ids)

        second, turn2 = _send_turn(
            db=db,
            workspace=workspace,
            patient=patient,
            message="قبل ما اختار، الجلسة سعرها كام؟",
            conversation_id=first.conversation_id,
            before_ids=before_ids,
            turn_number=2,
        )
        turns.append(turn2)
        created_after_side_question = _new_rows(db, workspace, patient, before_ids)

        _, turn3 = _send_turn(
            db=db,
            workspace=workspace,
            patient=patient,
            message="تمام، احجز أول ميعاد من اللي عرضتهم",
            conversation_id=second.conversation_id or first.conversation_id,
            before_ids=before_ids,
            turn_number=3,
        )
        turns.append(turn3)

        created_final = _new_rows(db, workspace, patient, before_ids)
        newest = created_final[-1] if created_final else None

        ok = (
            len(created_after_first) == 0
            and len(created_after_side_question) == 0
            and len(created_final) == 1
            and newest is not None
            and newest.service_id == UUID(str(service["id"]))
            and newest.duration_minutes == 60
        )
        return CaseResult(
            name="options_side_question_resume",
            status="PASS" if ok else "FAIL",
            duration_ms=int((perf_counter() - started) * 1000),
            turns=turns,
            details={
                "requested_date": date_text,
                "created_after_options": len(created_after_first),
                "created_after_side_question": len(created_after_side_question),
                "created_after_resume": len(created_final),
                "created_appointment_id": str(newest.id) if newest else None,
                "duration_minutes": newest.duration_minutes if newest else None,
            },
            error=None if ok else (
                "Expected the booking flow to survive the side pricing question, "
                "perform no early write, then create exactly one 60-minute appointment "
                "after the customer resumes and selects the first option."
            ),
        )
    except Exception as exc:  # noqa: BLE001
        return CaseResult(
            name="options_side_question_resume",
            status="FAIL",
            duration_ms=int((perf_counter() - started) * 1000),
            turns=turns,
            error=f"{type(exc).__name__}: {exc}",
        )


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Run five focused SINGLE-BRANCH conversational booking regressions."
    )
    parser.add_argument("--workspace-slug", default="tia-demo")
    parser.add_argument("--workspace-id", type=UUID, default=None)
    parser.add_argument(
        "--keep-data",
        action="store_true",
        help="Commit test appointments/conversations instead of rolling them back.",
    )
    parser.add_argument(
        "--report",
        default="artifacts/agent-booking-focus-single-branch.json",
        help="JSON report path, relative to backend unless absolute.",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()

    environment = str(settings.environment or "").strip().lower()
    if environment == "production":
        print("Refusing to run focused booking regression in production.", file=sys.stderr)
        return 2

    engine = create_engine(settings.database_url, pool_pre_ping=True)
    connection = engine.connect()
    outer = connection.begin()
    db = Session(
        bind=connection,
        expire_on_commit=False,
        join_transaction_mode="create_savepoint",
    )

    report: FocusReport | None = None
    exit_code = 1

    try:
        if args.workspace_id is not None:
            workspace = db.scalar(
                select(Workspace).where(Workspace.id == args.workspace_id)
            )
        else:
            workspace = db.scalar(
                select(Workspace).where(Workspace.slug == args.workspace_slug)
            )

        if workspace is None:
            raise RuntimeError("Workspace not found.")

        report = FocusReport(
            started_at=datetime.now(UTC).isoformat(),
            workspace_id=str(workspace.id),
            workspace_slug=workspace.slug,
            rollback=not args.keep_data,
        )

        catalog = build_clinic_catalog(db, workspace)
        patients = _fixture_patients(db, workspace)

        required_patients = {
            "busy-evening": patients.get("busy-evening"),
            "cancelled-slot": patients.get("cancelled-slot"),
            "history": patients.get("history"),
            "injectables": patients.get("injectables"),
            "pending-new-cairo": patients.get("pending-new-cairo"),
        }
        missing = [name for name, patient in required_patients.items() if patient is None]
        if missing:
            raise RuntimeError(
                "Missing realistic fixture patients: "
                + ", ".join(missing)
                + ". Run seed_realistic_aesthetic_clinic.py first."
            )

        cases = [
            _run_underarm_exact(
                db=db,
                workspace=workspace,
                catalog=catalog,
                patient=required_patients["busy-evening"],
            ),
            _run_full_body_exact(
                db=db,
                workspace=workspace,
                catalog=catalog,
                patient=required_patients["cancelled-slot"],
            ),
            _run_options_then_select(
                db=db,
                workspace=workspace,
                catalog=catalog,
                patient=required_patients["history"],
            ),
            _run_availability_only_no_write(
                db=db,
                workspace=workspace,
                catalog=catalog,
                patient=required_patients["injectables"],
            ),
            _run_side_question_resume(
                db=db,
                workspace=workspace,
                catalog=catalog,
                patient=required_patients["pending-new-cairo"],
            ),
        ]

        for result in cases:
            _record(report, result)

        exit_code = 1 if report.counts().get("FAIL", 0) else 0

    except Exception as exc:  # noqa: BLE001
        print(traceback.format_exc(), file=sys.stderr)
        if report is not None:
            _record(
                report,
                CaseResult(
                    name="suite_exception",
                    status="FAIL",
                    duration_ms=0,
                    error=f"{type(exc).__name__}: {exc}",
                ),
            )
        exit_code = 1

    finally:
        try:
            db.close()
        finally:
            if args.keep_data:
                outer.commit()
            else:
                outer.rollback()
            connection.close()
            engine.dispose()

    if report is not None:
        report_path = Path(args.report)
        if not report_path.is_absolute():
            report_path = Path.cwd() / report_path
        report_path.parent.mkdir(parents=True, exist_ok=True)

        payload = {
            **{key: value for key, value in asdict(report).items() if key != "results"},
            "counts": report.counts(),
            "results": [asdict(row) for row in report.results],
        }
        report_path.write_text(
            json.dumps(payload, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )

        print("\nSummary:", json.dumps(report.counts(), ensure_ascii=False))
        print(f"Report: {report_path}")
        if not args.keep_data:
            print("Database writes rolled back: yes")
        print("WhatsApp/n8n used: no")

    return exit_code


if __name__ == "__main__":
    raise SystemExit(main())
