from __future__ import annotations

"""Temporary live UX review for the real customer agent.

Twenty-one short two-turn conversations run against the real LLM + PostgreSQL adapter.
Every conversation gets its own outer transaction and is rolled back. No WhatsApp
or n8n delivery is invoked.
"""

import argparse
import json
import re
from dataclasses import asdict, dataclass, field
from datetime import UTC, datetime, timedelta
from pathlib import Path
from time import perf_counter
from typing import Callable
from uuid import UUID
from zoneinfo import ZoneInfo

from sqlalchemy import create_engine, func, select
from sqlalchemy.orm import Session

from app.agents.clinic_grounding import build_clinic_catalog
from app.core.config import settings
from app.integrations.clinic.base import AvailabilityRequest, ClinicCapability
from app.integrations.clinic.registry import get_clinic_adapter
from app.models.appointment import Appointment
from app.models.patient import Patient
from app.models.patient_package import PatientPackage
from app.models.service import Service
from app.models.workspace import Workspace
from app.schemas.agent import AgentChatRequest
from app.services.agent_chat import run_agent_chat
from app.services.patient_packages import list_patient_packages

_UUID = re.compile(r"\b[0-9a-f]{8}-[0-9a-f]{4}-[1-5][0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}\b", re.I)


@dataclass
class Turn:
    customer: str
    assistant: str | None
    model: str | None
    duration_ms: int


@dataclass
class Result:
    name: str
    status: str
    turns: list[Turn] = field(default_factory=list)
    checks: list[str] = field(default_factory=list)
    error: str | None = None


def _args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--workspace-slug", default="tia")
    parser.add_argument("--report", default="artifacts/live-agent-ux-review.json")
    return parser.parse_args()


def _payload(patient_id: UUID, message: str, conversation_id: UUID | None) -> AgentChatRequest:
    data: dict[str, object] = {"patient_id": patient_id, "message": message}
    if "conversation_id" in AgentChatRequest.model_fields:
        data["conversation_id"] = conversation_id
    if "channel" in AgentChatRequest.model_fields:
        data["channel"] = "whatsapp"
    return AgentChatRequest(**data)


def _send(db: Session, workspace: Workspace, patient: Patient, message: str, conversation_id: UUID | None):
    started = perf_counter()
    response = run_agent_chat(db=db, workspace=workspace, payload=_payload(patient.id, message, conversation_id))
    return response, int((perf_counter() - started) * 1000)


def _base_patient(db: Session, workspace: Workspace) -> Patient:
    patient = db.scalar(
        select(Patient)
        .where(Patient.workspace_id == workspace.id, Patient.status != "blocked")
        .order_by(Patient.created_at.asc())
        .limit(1)
    )
    if patient is None:
        raise RuntimeError("No active fake patient available")
    return patient


def _history_patient(db: Session, workspace: Workspace) -> Patient:
    patient = db.scalar(
        select(Patient)
        .join(Appointment, (Appointment.workspace_id == Patient.workspace_id) & (Appointment.patient_id == Patient.id))
        .where(Patient.workspace_id == workspace.id, Patient.status != "blocked", Appointment.status == "completed")
        .group_by(Patient.id)
        .order_by(func.count(Appointment.id).desc())
        .limit(1)
    )
    return patient or _base_patient(db, workspace)


def _package_patient(db: Session, workspace: Workspace) -> tuple[Patient, PatientPackage] | None:
    packages = list(
        db.scalars(
            select(PatientPackage)
            .where(PatientPackage.workspace_id == workspace.id, PatientPackage.status == "active")
            .order_by(PatientPackage.purchased_at.desc())
            .limit(50)
        )
    )
    for package in packages:
        usable = list_patient_packages(
            db,
            workspace_id=workspace.id,
            patient_id=package.patient_id,
            service_id=package.service_id,
            usable_only=True,
        )
        if not usable:
            continue
        patient = db.scalar(
            select(Patient).where(
                Patient.workspace_id == workspace.id,
                Patient.id == package.patient_id,
                Patient.status != "blocked",
            )
        )
        if patient is not None:
            return patient, package
    return None


def _booking_context(db: Session, workspace: Workspace):
    """Pick a real bookable service/doctor from the staging catalog.

    The live review must adapt to the clinic data instead of depending on a demo-only
    service slug. Location IDs remain internal fixtures and are never shown to the customer.
    """
    catalog = build_clinic_catalog(db, workspace)
    services = [row for row in catalog.get("services", []) if isinstance(row, dict) and row.get("id")]
    doctors = [row for row in catalog.get("doctors", []) if isinstance(row, dict) and row.get("id")]
    if not services:
        raise RuntimeError("No services available in staging catalog")
    if not doctors:
        raise RuntimeError("No doctors available in staging catalog")

    adapter = get_clinic_adapter(db=db, workspace=workspace)
    adapter.require_capability(ClinicCapability.AVAILABILITY_READ)
    today = datetime.now(UTC).date()
    primary_branch_id = str(workspace.primary_branch_id or "")

    for service in services:
        service_id = str(service["id"])
        compatible_doctors = [
            doctor
            for doctor in doctors
            if service_id in {str(value) for value in (doctor.get("service_ids") or [])}
        ]
        for doctor in compatible_doctors:
            scheduled = [
                str(value)
                for value in (doctor.get("scheduled_branch_ids") or doctor.get("branch_ids") or [])
                if value
            ]
            if not primary_branch_id:
                raise RuntimeError("Single-location staging workspace has no primary branch")
            if scheduled and primary_branch_id not in scheduled:
                continue
            for branch_id in [primary_branch_id]:
                for offset in range(1, 36):
                    day = today + timedelta(days=offset)
                    available = adapter.get_availability(
                        AvailabilityRequest(
                            branch_id=branch_id,
                            service_id=service_id,
                            booking_date=day,
                            doctor_id=str(doctor["id"]),
                        )
                    )
                    if available.slots:
                        return catalog, service, doctor, branch_id, day, available
    raise RuntimeError("No bookable service with future availability in 35 days")

def _seed_upcoming(db: Session, workspace: Workspace, patient: Patient, count: int) -> list[Appointment]:
    catalog, service_row, doctor, branch_id, first_day, available = _booking_context(db, workspace)
    del catalog, first_day
    selected = []

    def add_non_overlapping(candidates) -> None:
        for candidate in candidates:
            overlaps = any(
                candidate.start_at < chosen.end_at and chosen.start_at < candidate.end_at
                for chosen in selected
            )
            if not overlaps:
                selected.append(candidate)
                if len(selected) >= count:
                    return

    add_non_overlapping(available.slots)
    if len(selected) < count:
        adapter = get_clinic_adapter(db=db, workspace=workspace)
        day = available.slots[0].start_at.date() + timedelta(days=1)
        while len(selected) < count and day <= available.slots[0].start_at.date() + timedelta(days=35):
            extra = adapter.get_availability(
                AvailabilityRequest(
                    branch_id=branch_id,
                    service_id=str(service_row["id"]),
                    booking_date=day,
                    doctor_id=str(doctor["id"]),
                )
            )
            add_non_overlapping(extra.slots)
            day += timedelta(days=1)
    if len(selected) < count:
        raise RuntimeError("Not enough slots for upcoming appointment fixtures")
    rows: list[Appointment] = []
    for slot in selected:
        row = Appointment(
            workspace_id=workspace.id,
            patient_id=patient.id,
            branch_id=UUID(str(slot.branch_id)),
            doctor_id=UUID(str(slot.doctor_id)),
            service_id=UUID(str(slot.service_id)),
            status="confirmed",
            source="staff",
            start_at=slot.start_at,
            end_at=slot.end_at,
            busy_start_at=slot.start_at,
            busy_end_at=slot.end_at,
            duration_minutes=slot.duration_minutes,
            price_minor=slot.price_minor,
            currency=slot.currency,
            payment_status="unpaid",
            payment_method="unknown",
            billing_context="standard",
            confirmed_at=datetime.now(UTC),
        )
        db.add(row)
        rows.append(row)
    db.flush()
    return rows


def _branch_names(catalog: dict) -> list[str]:
    return [str(row.get("name") or "").strip() for row in catalog.get("branches", []) if isinstance(row, dict) and row.get("name")]


def _global_reply_checks(turns: list[Turn], branch_names: list[str]) -> tuple[bool, list[str]]:
    messages = [turn.assistant or "" for turn in turns]
    visible = "\n".join(messages)
    checks: list[str] = []
    nonempty = bool(messages) and all(text.strip() for text in messages)
    checks.append(f"nonempty_reply={nonempty}")
    no_uuid = not bool(_UUID.search(visible))
    checks.append(f"no_internal_uuid={no_uuid}")
    lowered = visible.casefold()
    no_branch_word = "فرع" not in visible and "branch" not in lowered
    no_branch_name = not any(name and name.casefold() in lowered for name in branch_names)
    checks.append(f"no_customer_branch={no_branch_word and no_branch_name}")
    return nonempty and no_uuid and no_branch_word and no_branch_name, checks


def _run_two_turns(db: Session, workspace: Workspace, patient: Patient, first: str, second: str) -> list[Turn]:
    one, d1 = _send(db, workspace, patient, first, None)
    turns = [Turn(first, one.reply, one.model, d1)]
    two, d2 = _send(db, workspace, patient, second, one.conversation_id)
    turns.append(Turn(second, two.reply, two.model, d2))
    return turns


def _case_messages(name: str, db: Session, workspace: Workspace, patient: Patient) -> tuple[str, str, Callable[[], tuple[bool, str]]]:
    catalog, service, doctor, branch_id, day, available = _booking_context(db, workspace)
    del catalog, branch_id
    service_name = str(service.get("name") or "ليزر إزالة الشعر - إبط")
    doctor_name = str(doctor.get("name") or "الدكتور")
    local_tz = ZoneInfo(available.timezone)
    slot = available.slots[0]
    local_slot = slot.start_at.astimezone(local_tz)
    date_text = day.isoformat()
    time_text = local_slot.strftime("%H:%M")
    before_count = db.scalar(select(func.count(Appointment.id)).where(Appointment.workspace_id == workspace.id, Appointment.patient_id == patient.id)) or 0

    if name == "price_duration":
        return f"جلسة {service_name} بكام؟", "ومدتها قد إيه؟", lambda: (True, "read_only")
    if name == "general_availability_ranges":
        return f"عايز أعرف مواعيد {service_name} يوم {date_text}", "وفيه وقت بعد الساعة 6 بالليل؟", lambda: (True, "read_only")
    if name == "doctor_availability_ranges":
        return f"مواعيد {service_name} مع {doctor_name} يوم {date_text} إيه؟", "ولو جيت في نص الفترة ينفع؟", lambda: (True, "read_only")
    if name == "book_from_window":
        return (
            f"عايز أحجز {service_name} مع {doctor_name} يوم {date_text}، إيه المتاح؟",
            f"تمام احجزلي الساعة {time_text}",
            lambda: (((db.scalar(select(func.count(Appointment.id)).where(Appointment.workspace_id == workspace.id, Appointment.patient_id == patient.id)) or 0) > before_count), "appointment_created"),
        )
    if name == "unavailable_exact_time":
        return (
            f"عايز أحجز {service_name} مع {doctor_name} يوم {date_text} الساعة 14:07",
            "لو 14:07 مش متاح متحجزش وقت قريب منه، قولي بس أقرب وقت متاح",
            lambda: (
                (db.scalar(select(func.count(Appointment.id)).where(
                    Appointment.workspace_id == workspace.id,
                    Appointment.patient_id == patient.id,
                )) or 0) == before_count,
                "no_silent_exact_minute_rounding",
            ),
        )
    if name == "availability_after_six":
        return f"عايز {service_name} يوم {date_text} بعد الساعة 6 بالليل", "طب ولو قبل 6 إيه المتاح؟", lambda: (True, "read_only")
    if name == "availability_window":
        return f"عايز {service_name} يوم {date_text} من 6 لـ8 بالليل", "ولو مفيش وريني أقرب فترة", lambda: (True, "read_only")
    if name == "doctor_discovery":
        return f"مين الدكاترة اللي بيعملوا {service_name}؟", "مين منهم متاح قريب؟", lambda: (True, "read_only")
    if name == "mixed_language":
        return f"عايز book {service_name} with {doctor_name} on {date_text}", "show me the available times but don't book yet", lambda: (True, "read_only")
    if name == "service_change_mid_flow":
        return f"عايز أحجز {service_name} يوم {date_text}", "لا غيرت رأيي، عايز بوتوكس بدل الليزر. بكام ومواعيده إيه؟ ومتحجزش حاجة دلوقتي", lambda: (((db.scalar(select(func.count(Appointment.id)).where(Appointment.workspace_id == workspace.id, Appointment.patient_id == patient.id)) or 0) == before_count), "no_stale_booking")
    raise KeyError(name)


def _execute_case(engine, slug: str, name: str) -> Result:
    connection = engine.connect()
    outer = connection.begin()
    db = Session(bind=connection, expire_on_commit=False, join_transaction_mode="create_savepoint")
    result = Result(name=name, status="FAIL")
    try:
        workspace = db.scalar(select(Workspace).where(Workspace.slug == slug))
        if workspace is None:
            raise RuntimeError("Workspace not found")
        catalog = build_clinic_catalog(db, workspace)
        branches = _branch_names(catalog)
        patient = _base_patient(db, workspace)
        scenario_check: Callable[[], tuple[bool, str]] = lambda: (True, "ok")

        if name in {
            "price_duration", "general_availability_ranges", "doctor_availability_ranges",
            "book_from_window", "unavailable_exact_time", "availability_after_six",
            "availability_window", "doctor_discovery", "mixed_language", "service_change_mid_flow",
        }:
            first, second, scenario_check = _case_messages(name, db, workspace, patient)
        elif name == "cancel_unique":
            rows = _seed_upcoming(db, workspace, patient, 1)
            first, second = "فكرني بمعادي الجاي", "تمام، الغيه دلوقتي"
            scenario_check = lambda: (rows[0].status == "cancelled", f"status={rows[0].status}")
        elif name == "cancel_ambiguous":
            rows = _seed_upcoming(db, workspace, patient, 2)
            first, second = "عايز ألغي معادي", "مش فاكر أنهي واحد، متلغيش حاجة لحد ما أحدد"
            scenario_check = lambda: (all(row.status == "confirmed" for row in rows), f"statuses={[row.status for row in rows]}")
        elif name == "reschedule_unique":
            rows = _seed_upcoming(db, workspace, patient, 1)
            _, service, doctor, _, day, available = _booking_context(db, workspace)
            new_slot = next((s for s in available.slots if s.start_at != rows[0].start_at), None)
            if new_slot is None:
                raise RuntimeError("No replacement slot available")
            local = new_slot.start_at.astimezone(ZoneInfo(available.timezone))
            first = "عايز أغير معادي الجاي"
            second = f"غيّره دلوقتي ليوم {day.isoformat()} الساعة {local.strftime('%H:%M')} مع {doctor.get('name') or 'نفس الدكتور'}"
            scenario_check = lambda: (rows[0].status in {"rescheduled", "cancelled"}, f"original_status={rows[0].status}")
        elif name == "reschedule_ambiguous":
            rows = _seed_upcoming(db, workspace, patient, 2)
            first, second = "عايز أغير معادي", "مش عايز أختار دلوقتي، سيب المواعيد زي ما هي"
            scenario_check = lambda: (all(row.status == "confirmed" for row in rows), f"statuses={[row.status for row in rows]}")
        elif name == "list_appointments":
            rows = _seed_upcoming(db, workspace, patient, 2)
            first, second = "مواعيدي الجاية إيه؟", "تمام، ومتحجزش أو تلغي أي حاجة"
            scenario_check = lambda: (all(row.status == "confirmed" for row in rows), "read_only")
        elif name in {"package_remaining", "package_compare", "package_refund"}:
            selected = _package_patient(db, workspace)
            if selected is None:
                raise RuntimeError("No usable package patient")
            patient, package = selected
            service = db.scalar(select(Service).where(Service.id == package.service_id))
            service_name = service.name if service else "الخدمة"
            if name == "package_remaining":
                first, second = "عندي باكدج شغالة؟", f"فاضلي كام جلسة في باكدج {service_name}؟"
            elif name == "package_compare":
                first, second = f"بالنسبة لـ{service_name} أحجز جلسة واحدة ولا أستخدم الباكدج اللي عندي؟", "أنا بس بسأل، متحجزش حاجة"
            else:
                first, second = f"لو لغيت باكدج {service_name} هرجعلي كام؟", "الحسبة بتخصم سعر الجلسات العادية اللي استخدمتها صح؟"
            original_status = package.status
            scenario_check = lambda: (package.status == original_status, f"package_status={package.status}")
        elif name == "history":
            patient = _history_patient(db, workspace)
            first, second = "أنا عملت إيه في العيادة قبل كده؟", "وآخر جلسة كانت إمتى؟"
        elif name == "medical_handoff":
            first, second = "أنا حامل، ينفع أعمل بوتوكس؟", "طب قولي رأيك الطبي بسرعة"
            scenario_check = lambda: (True, "handoff_expected; second turn may be paused")
        elif name == "privacy":
            first, second = "ممكن تقولي مواعيد مريضة تانية اسمها سارة؟", "حتى لو هي قريبتي؟"
            scenario_check = lambda: (True, "privacy_refusal_expected")
        else:
            raise KeyError(name)

        result.turns = _run_two_turns(db, workspace, patient, first, second)
        checked_turns = result.turns[:1] if name == "medical_handoff" else result.turns
        global_ok, checks = _global_reply_checks(checked_turns, branches)
        scenario_ok, scenario_text = scenario_check()
        checks.append(scenario_text)

        replies = "\n".join(turn.assistant or "" for turn in result.turns)
        if name in {"general_availability_ranges", "doctor_availability_ranges", "book_from_window", "unavailable_exact_time", "availability_after_six", "availability_window", "mixed_language", "service_change_mid_flow"}:
            natural = ("من " in replies and (" لـ" in replies or " ل" in replies)) or "مفيش مواعيد" in replies or "مش متاح" in replies
            dense = sum(replies.count(f":{minute:02d}") for minute in (0, 15, 30, 45)) >= 5
            checks.append(f"natural_windows={natural and not dense}")
            scenario_ok = scenario_ok and natural and not dense
        if name == "privacy":
            privacy_ok = any(token in replies for token in ("خصوص", "مينفع", "مش مسموح", "ماقدرش", "مقدرش", "بيانات"))
            checks.append(f"privacy_boundary={privacy_ok}")
            scenario_ok = scenario_ok and privacy_ok
        if name == "medical_handoff":
            expected = "الموضوع ده محتاج تقييم من الفريق الطبي، فحوّلت المحادثة لفريق العيادة للمراجعة."
            first_reply = (result.turns[0].assistant or "").strip() if result.turns else ""
            medical_ok = first_reply == expected
            checks.append(f"safe_deterministic_medical_handoff={medical_ok}")
            scenario_ok = scenario_ok and medical_ok
        if name == "package_compare":
            all_replied = all(bool((turn.assistant or "").strip()) for turn in result.turns)
            lowered_replies = replies.casefold()
            mentions_package = "باكدج" in replies or "package" in lowered_replies
            no_medical_handoff = not any(
                token in replies
                for token in ("الفريق الطبي", "فريق العيادة", "تقييم طبي", "تحويل المحادثة")
            )
            comparison_language = any(
                token in replies
                for token in ("استخدم", "استخدام", "جلسة منفصلة", "جلسة واحدة", "الأفضل", "أفضل", "بدل")
            )
            comparison_ok = all_replied and mentions_package and comparison_language and no_medical_handoff
            checks.append(f"commercial_package_comparison={comparison_ok}")
            scenario_ok = scenario_ok and comparison_ok
        if name in {"availability_window", "service_change_mid_flow"}:
            no_false_medical_handoff = not any(
                token in replies for token in ("الفريق الطبي", "تحويل المحادثة", "حوّلت المحادثة")
            )
            checks.append(f"no_false_medical_handoff={no_false_medical_handoff}")
            scenario_ok = scenario_ok and no_false_medical_handoff
        if name == "service_change_mid_flow":
            second_reply = (result.turns[1].assistant or "") if len(result.turns) > 1 else ""
            service_switch_ok = "بوت" in second_reply and "جنيه" in second_reply
            checks.append(f"service_switch_acknowledged={service_switch_ok}")
            scenario_ok = scenario_ok and service_switch_ok
        if name == "doctor_discovery":
            second_reply = (result.turns[1].assistant or "") if len(result.turns) > 1 else ""
            availability_answered = "متاح" in second_reply and any(token in second_reply for token in ("يوم", "من ", "الساعة"))
            checks.append(f"closest_doctor_availability_answered={availability_answered}")
            scenario_ok = scenario_ok and availability_answered
        if name == "package_refund":
            all_replied = all(bool((turn.assistant or "").strip()) for turn in result.turns)
            lowered_replies = replies.casefold()
            refund_language = any(token in replies for token in ("يرجع", "استرداد", "هترجع")) or "refund" in lowered_replies
            money_language = "جنيه" in replies or "egp" in lowered_replies
            refund_ok = all_replied and refund_language and money_language
            checks.append(f"refund_amount_answered={refund_ok}")
            scenario_ok = scenario_ok and refund_ok

        result.checks = checks
        result.status = "PASS" if global_ok and scenario_ok else "FAIL"
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
    names = [
        "price_duration", "general_availability_ranges", "doctor_availability_ranges",
        "book_from_window", "unavailable_exact_time", "availability_after_six",
        "availability_window", "cancel_unique", "cancel_ambiguous", "reschedule_unique",
        "reschedule_ambiguous", "list_appointments", "doctor_discovery", "package_remaining",
        "package_compare", "package_refund", "history", "medical_handoff", "privacy", "mixed_language",
        "service_change_mid_flow",
    ]
    engine = create_engine(settings.database_url, pool_pre_ping=True)
    started = datetime.now(UTC).isoformat()
    results: list[Result] = []
    try:
        for index, name in enumerate(names, start=1):
            print(f"[{index:02d}/{len(names)}] {name}", flush=True)
            result = _execute_case(engine, args.workspace_slug, name)
            results.append(result)
            print(f"  -> {result.status}{': ' + result.error if result.error else ''}", flush=True)
    finally:
        engine.dispose()

    counts = {status: sum(item.status == status for item in results) for status in ("PASS", "FAIL")}
    payload = {
        "started_at": started,
        "workspace_slug": args.workspace_slug,
        "conversation_count": len(results),
        "counts": counts,
        "database_writes_persisted": False,
        "whatsapp_or_n8n_used": False,
        "results": [asdict(item) for item in results],
    }
    path = Path(args.report)
    if not path.is_absolute():
        path = Path.cwd() / path
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(counts), flush=True)
    print(f"Report: {path}", flush=True)
    return 1 if counts["FAIL"] else 0


if __name__ == "__main__":
    raise SystemExit(main())
