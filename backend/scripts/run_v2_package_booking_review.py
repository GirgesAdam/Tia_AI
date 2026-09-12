from __future__ import annotations

"""Focused real-LLM review for V2 package-aware booking.

Uses the real V2 live facade, real staging PostgreSQL data, real package offers and
availability, and rolls every conversation back at the outer transaction boundary.
No WhatsApp/n8n delivery is invoked.
"""

import argparse
import json
from dataclasses import asdict, dataclass, field
from datetime import UTC, datetime, timedelta
from pathlib import Path
from time import perf_counter
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
from app.models.patient_package import PackageUsage, PatientPackage
from app.models.workspace import Workspace
from app.schemas.agent import AgentChatRequest
from app.services.agent_v2.live_chat import run_agent_chat
from app.services.package_offers import list_package_offers, purchase_package_offer


@dataclass
class Turn:
    customer: str
    assistant: str | None
    model: str | None
    duration_ms: int


@dataclass
class Result:
    name: str
    turns: list[Turn] = field(default_factory=list)
    db_checks: list[str] = field(default_factory=list)
    error: str | None = None


def _args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--workspace-slug", default="tia")
    parser.add_argument("--report", default="artifacts/v2-package-booking-review.json")
    parser.add_argument("--case", dest="cases", action="append", default=None)
    return parser.parse_args()


def _payload(patient_id: UUID, message: str, conversation_id: UUID | None) -> AgentChatRequest:
    data: dict[str, object] = {"patient_id": patient_id, "message": message}
    if "conversation_id" in AgentChatRequest.model_fields:
        data["conversation_id"] = conversation_id
    if "channel" in AgentChatRequest.model_fields:
        data["channel"] = "whatsapp"
    return AgentChatRequest(**data)


def _send(
    db: Session,
    workspace: Workspace,
    patient: Patient,
    message: str,
    conversation_id: UUID | None,
) -> tuple[object, int]:
    started = perf_counter()
    response = run_agent_chat(
        db=db,
        workspace=workspace,
        payload=_payload(patient.id, message, conversation_id),
    )
    return response, int((perf_counter() - started) * 1000)


def _new_patient(db: Session, workspace: Workspace, label: str) -> Patient:
    patient = Patient(
        workspace_id=workspace.id,
        first_name=f"Package Review {label}",
        preferred_language="ar",
        source="other",
        status="active",
    )
    db.add(patient)
    db.flush()
    return patient


def _offer_context(
    db: Session,
    workspace: Workspace,
    *,
    exclude_service_id: UUID | None = None,
    service_id: UUID | None = None,
    exclude_device_key: str | None = None,
):
    catalog = build_clinic_catalog(db, workspace)
    services = {
        str(row["id"]): row
        for row in catalog.get("services", [])
        if isinstance(row, dict) and row.get("id")
    }
    doctors = [
        row
        for row in catalog.get("doctors", [])
        if isinstance(row, dict) and row.get("id")
    ]
    offers = list_package_offers(
        db,
        workspace_id=workspace.id,
        service_id=service_id,
        active_only=True,
    )
    adapter = get_clinic_adapter(db=db, workspace=workspace)
    adapter.require_capability(ClinicCapability.AVAILABILITY_READ)
    branch_id = str(workspace.primary_branch_id or "")
    if not branch_id:
        raise RuntimeError("Single-location staging workspace has no primary branch")
    today = datetime.now(UTC).date()

    for offer in offers:
        if exclude_service_id is not None and offer.service_id == exclude_service_id:
            continue
        if exclude_device_key is not None and offer.device_key == exclude_device_key:
            continue
        service = services.get(str(offer.service_id))
        if service is None:
            continue
        compatible = [
            row
            for row in doctors
            if str(offer.service_id) in {str(item) for item in (row.get("service_ids") or [])}
        ]
        for doctor in compatible:
            scheduled = {
                str(item)
                for item in (doctor.get("scheduled_branch_ids") or doctor.get("branch_ids") or [])
                if item
            }
            if scheduled and branch_id not in scheduled:
                continue
            for offset in range(1, 36):
                day = today + timedelta(days=offset)
                availability = adapter.get_availability(
                    AvailabilityRequest(
                        branch_id=branch_id,
                        service_id=str(offer.service_id),
                        booking_date=day,
                        doctor_id=str(doctor["id"]),
                        laser_device_key=offer.device_key,
                    )
                )
                if availability.slots:
                    return offer, service, doctor, day, availability
    raise RuntimeError("No active package offer with matching future availability")


def _seed_package(
    db: Session,
    workspace: Workspace,
    patient: Patient,
    offer,
    *,
    key: str,
) -> PatientPackage:
    package = purchase_package_offer(
        db,
        workspace_id=workspace.id,
        patient_id=patient.id,
        offer_id=offer.id,
        amount_paid_minor=0,
        payment_method="unknown",
        created_by_user_id=None,
        idempotency_key=key,
        actor_type="ai",
    )
    db.flush()
    return package


def _new_appointments(db: Session, workspace: Workspace, patient: Patient, before: int):
    rows = list(
        db.scalars(
            select(Appointment)
            .where(
                Appointment.workspace_id == workspace.id,
                Appointment.patient_id == patient.id,
            )
            .order_by(Appointment.created_at.asc())
        )
    )
    return rows[before:]


def _usage_for_appointment(db: Session, workspace: Workspace, appointment: Appointment):
    return db.scalar(
        select(PackageUsage).where(
            PackageUsage.workspace_id == workspace.id,
            PackageUsage.appointment_id == appointment.id,
        )
    )


def _book_two_turns(
    db: Session,
    workspace: Workspace,
    patient: Patient,
    *,
    service_name: str,
    device_name: str,
    doctor_name: str,
    day,
    availability,
    first_prefix: str,
) -> list[Turn]:
    slot = availability.slots[0]
    local = slot.start_at.astimezone(ZoneInfo(availability.timezone))
    first = (
        f"{first_prefix} {service_name} على جهاز {device_name} مع {doctor_name} "
        f"يوم {day.isoformat()}، إيه المواعيد المتاحة؟"
    )
    one, d1 = _send(db, workspace, patient, first, None)
    second = f"تمام احجزلي الساعة {local.strftime('%H:%M')} في نفس اليوم مع نفس الدكتور"
    two, d2 = _send(db, workspace, patient, second, one.conversation_id)
    return [
        Turn(first, one.reply, one.model, d1),
        Turn(second, two.reply, two.model, d2),
    ]


def _case_auto_existing(db: Session, workspace: Workspace) -> Result:
    result = Result(name="auto_existing_package_without_mention")
    patient = _new_patient(db, workspace, "auto")
    offer, service, doctor, day, availability = _offer_context(db, workspace)
    package = _seed_package(db, workspace, patient, offer, key=f"review-auto-{patient.id}")
    before = db.scalar(
        select(func.count(Appointment.id)).where(
            Appointment.workspace_id == workspace.id,
            Appointment.patient_id == patient.id,
        )
    ) or 0
    result.turns = _book_two_turns(
        db,
        workspace,
        patient,
        service_name=str(service.get("name") or offer.service_name),
        device_name=str(offer.device_name),
        doctor_name=str(doctor.get("name") or "الدكتور"),
        day=day,
        availability=availability,
        first_prefix="عايز أحجز",
    )
    created = _new_appointments(db, workspace, patient, int(before))
    appointment = created[-1] if created else None
    usage = _usage_for_appointment(db, workspace, appointment) if appointment else None
    result.db_checks.extend(
        [
            f"appointment_delta={len(created)}",
            f"expected_package_id={package.id}",
            f"appointment_package_id={appointment.patient_package_id if appointment else None}",
            f"usage_package_id={usage.patient_package_id if usage else None}",
            f"usage_status={usage.status if usage else None}",
        ]
    )
    return result


def _case_explicit_existing(db: Session, workspace: Workspace) -> Result:
    result = Result(name="explicit_existing_package")
    patient = _new_patient(db, workspace, "explicit")
    offer, service, doctor, day, availability = _offer_context(db, workspace)
    package = _seed_package(db, workspace, patient, offer, key=f"review-explicit-{patient.id}")
    before = db.scalar(select(func.count(Appointment.id)).where(Appointment.patient_id == patient.id)) or 0
    result.turns = _book_two_turns(
        db,
        workspace,
        patient,
        service_name=str(service.get("name") or offer.service_name),
        device_name=str(offer.device_name),
        doctor_name=str(doctor.get("name") or "الدكتور"),
        day=day,
        availability=availability,
        first_prefix="عايز أحجز الجلسة الجاية من الباكيدج اللي عندي لـ",
    )
    created = _new_appointments(db, workspace, patient, int(before))
    appointment = created[-1] if created else None
    usage = _usage_for_appointment(db, workspace, appointment) if appointment else None
    result.db_checks.extend(
        [
            f"appointment_delta={len(created)}",
            f"expected_package_id={package.id}",
            f"appointment_package_id={appointment.patient_package_id if appointment else None}",
            f"usage_status={usage.status if usage else None}",
        ]
    )
    return result


def _case_opt_out(db: Session, workspace: Workspace) -> Result:
    result = Result(name="explicit_standalone_opt_out")
    patient = _new_patient(db, workspace, "optout")
    offer, service, doctor, day, availability = _offer_context(db, workspace)
    package = _seed_package(db, workspace, patient, offer, key=f"review-optout-{patient.id}")
    before_usage = db.scalar(
        select(func.count(PackageUsage.id)).where(PackageUsage.patient_package_id == package.id)
    ) or 0
    before = db.scalar(select(func.count(Appointment.id)).where(Appointment.patient_id == patient.id)) or 0
    result.turns = _book_two_turns(
        db,
        workspace,
        patient,
        service_name=str(service.get("name") or offer.service_name),
        device_name=str(offer.device_name),
        doctor_name=str(doctor.get("name") or "الدكتور"),
        day=day,
        availability=availability,
        first_prefix="عايز أحجز جلسة منفردة وماتستخدمش الباكيدج لـ",
    )
    created = _new_appointments(db, workspace, patient, int(before))
    appointment = created[-1] if created else None
    after_usage = db.scalar(
        select(func.count(PackageUsage.id)).where(PackageUsage.patient_package_id == package.id)
    ) or 0
    result.db_checks.extend(
        [
            f"appointment_delta={len(created)}",
            f"appointment_package_id={appointment.patient_package_id if appointment else None}",
            f"package_usage_delta={int(after_usage) - int(before_usage)}",
        ]
    )
    return result


def _case_different_service(db: Session, workspace: Workspace) -> Result:
    result = Result(name="different_service_while_other_package_exists")
    patient = _new_patient(db, workspace, "different")
    offer_a, _service_a, _doctor_a, _day_a, _availability_a = _offer_context(db, workspace)
    package = _seed_package(db, workspace, patient, offer_a, key=f"review-other-{patient.id}")
    offer_b, service_b, doctor_b, day_b, availability_b = _offer_context(
        db,
        workspace,
        exclude_service_id=offer_a.service_id,
    )
    before_usage = db.scalar(
        select(func.count(PackageUsage.id)).where(PackageUsage.patient_package_id == package.id)
    ) or 0
    before = db.scalar(select(func.count(Appointment.id)).where(Appointment.patient_id == patient.id)) or 0
    result.turns = _book_two_turns(
        db,
        workspace,
        patient,
        service_name=str(service_b.get("name") or offer_b.service_name),
        device_name=str(offer_b.device_name),
        doctor_name=str(doctor_b.get("name") or "الدكتور"),
        day=day_b,
        availability=availability_b,
        first_prefix="عايز أحجز",
    )
    created = _new_appointments(db, workspace, patient, int(before))
    appointment = created[-1] if created else None
    after_usage = db.scalar(
        select(func.count(PackageUsage.id)).where(PackageUsage.patient_package_id == package.id)
    ) or 0
    result.db_checks.extend(
        [
            f"existing_package_service_id={offer_a.service_id}",
            f"booked_service_id={offer_b.service_id}",
            f"appointment_package_id={appointment.patient_package_id if appointment else None}",
            f"other_package_usage_delta={int(after_usage) - int(before_usage)}",
        ]
    )
    return result


def _case_device_mismatch(db: Session, workspace: Workspace) -> Result:
    result = Result(name="same_service_different_device_package")
    patient = _new_patient(db, workspace, "device")
    offer_a, _service_a, _doctor_a, _day_a, _availability_a = _offer_context(db, workspace)
    package = _seed_package(db, workspace, patient, offer_a, key=f"review-device-{patient.id}")
    offer_b, service_b, doctor_b, day_b, availability_b = _offer_context(
        db,
        workspace,
        service_id=offer_a.service_id,
        exclude_device_key=offer_a.device_key,
    )
    before_usage = db.scalar(
        select(func.count(PackageUsage.id)).where(PackageUsage.patient_package_id == package.id)
    ) or 0
    before = db.scalar(select(func.count(Appointment.id)).where(Appointment.patient_id == patient.id)) or 0
    result.turns = _book_two_turns(
        db,
        workspace,
        patient,
        service_name=str(service_b.get("name") or offer_b.service_name),
        device_name=str(offer_b.device_name),
        doctor_name=str(doctor_b.get("name") or "الدكتور"),
        day=day_b,
        availability=availability_b,
        first_prefix="عايز أحجز",
    )
    created = _new_appointments(db, workspace, patient, int(before))
    appointment = created[-1] if created else None
    after_usage = db.scalar(
        select(func.count(PackageUsage.id)).where(PackageUsage.patient_package_id == package.id)
    ) or 0
    result.db_checks.extend(
        [
            f"package_device={offer_a.device_key}",
            f"booked_device={offer_b.device_key}",
            f"appointment_package_id={appointment.patient_package_id if appointment else None}",
            f"mismatched_package_usage_delta={int(after_usage) - int(before_usage)}",
        ]
    )
    return result


def _case_first_purchase_then_book(db: Session, workspace: Workspace) -> Result:
    result = Result(name="first_package_purchase_then_first_booking")
    patient = _new_patient(db, workspace, "firstbuy")
    offer, service, doctor, day, availability = _offer_context(db, workspace)
    service_name = str(service.get("name") or offer.service_name)
    before_packages = db.scalar(
        select(func.count(PatientPackage.id)).where(PatientPackage.patient_id == patient.id)
    ) or 0
    buy_message = (
        f"عايز أشتري باكيدج {offer.sessions_count} جلسات {service_name} "
        f"على جهاز {offer.device_name} دلوقتي"
    )
    buy, d1 = _send(db, workspace, patient, buy_message, None)
    packages = list(
        db.scalars(
            select(PatientPackage)
            .where(PatientPackage.patient_id == patient.id)
            .order_by(PatientPackage.created_at.asc())
        )
    )
    purchased = packages[-1] if len(packages) > int(before_packages) else None
    ask_message = (
        f"عايز أحجز أول جلسة يوم {day.isoformat()} مع {doctor.get('name') or 'الدكتور'}، "
        "إيه المتاح؟"
    )
    ask, d2 = _send(db, workspace, patient, ask_message, buy.conversation_id)
    slot = availability.slots[0]
    local = slot.start_at.astimezone(ZoneInfo(availability.timezone))
    book_message = f"تمام احجزلي الساعة {local.strftime('%H:%M')} على نفس الجهاز"
    book, d3 = _send(db, workspace, patient, book_message, ask.conversation_id)
    result.turns = [
        Turn(buy_message, buy.reply, buy.model, d1),
        Turn(ask_message, ask.reply, ask.model, d2),
        Turn(book_message, book.reply, book.model, d3),
    ]
    appointments = list(
        db.scalars(
            select(Appointment)
            .where(Appointment.patient_id == patient.id)
            .order_by(Appointment.created_at.asc())
        )
    )
    appointment = appointments[-1] if appointments else None
    usage = _usage_for_appointment(db, workspace, appointment) if appointment else None
    result.db_checks.extend(
        [
            f"package_delta={len(packages) - int(before_packages)}",
            f"purchased_package_id={purchased.id if purchased else None}",
            f"appointment_package_id={appointment.patient_package_id if appointment else None}",
            f"usage_package_id={usage.patient_package_id if usage else None}",
            f"usage_status={usage.status if usage else None}",
        ]
    )
    return result


CASES = {
    "auto_existing_package_without_mention": _case_auto_existing,
    "explicit_existing_package": _case_explicit_existing,
    "explicit_standalone_opt_out": _case_opt_out,
    "different_service_while_other_package_exists": _case_different_service,
    "same_service_different_device_package": _case_device_mismatch,
    "first_package_purchase_then_first_booking": _case_first_purchase_then_book,
}


def _execute(engine, slug: str, name: str) -> Result:
    connection = engine.connect()
    outer = connection.begin()
    db = Session(bind=connection, expire_on_commit=False, join_transaction_mode="create_savepoint")
    try:
        workspace = db.scalar(select(Workspace).where(Workspace.slug == slug))
        if workspace is None:
            raise RuntimeError("Workspace not found")
        return CASES[name](db, workspace)
    except Exception as exc:
        return Result(name=name, error=f"{type(exc).__name__}: {exc}")
    finally:
        db.close()
        if outer.is_active:
            outer.rollback()
        connection.close()


def main() -> int:
    args = _args()
    if not settings.agent_v2_live_enabled:
        raise RuntimeError("Package review refuses to run unless AGENT_V2_LIVE_ENABLED=true")
    engine = create_engine(settings.database_url, pool_pre_ping=True)
    selected = args.cases or list(CASES)
    report = []
    for index, name in enumerate(selected, start=1):
        if name not in CASES:
            raise KeyError(name)
        print(f"[package-review {index:02d}/{len(selected):02d}] {name}", flush=True)
        result = _execute(engine, args.workspace_slug, name)
        report.append(asdict(result))
        print(json.dumps(asdict(result), ensure_ascii=False, separators=(",", ":")), flush=True)

    path = Path(args.report)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"Report: {path.resolve()}", flush=True)
    return 1 if any(item["error"] for item in report) else 0


if __name__ == "__main__":
    raise SystemExit(main())
