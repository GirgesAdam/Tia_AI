from __future__ import annotations

"""Rollback-only real-LLM review for compound V2 booking/package requests."""

import argparse
import json
from dataclasses import asdict
from datetime import timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

from sqlalchemy import create_engine, func, select
from sqlalchemy.orm import Session

from app.core.config import settings
from app.integrations.clinic.base import AvailabilityRequest
from app.integrations.clinic.registry import get_clinic_adapter
from app.models.appointment import Appointment
from app.models.patient_package import PackageUsage, PatientPackage
from app.models.workspace import Workspace
from scripts import run_v2_package_booking_review as base


def _args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--workspace-slug", default="tia")
    parser.add_argument("--report", default="artifacts/v2-compound-booking-review.json")
    return parser.parse_args()


def _second_available_day(db: Session, workspace: Workspace, offer, doctor, first_day, first_availability):
    adapter = get_clinic_adapter(db=db, workspace=workspace)
    branch_id = str(workspace.primary_branch_id or "")
    for offset in range(1, 22):
        day = first_day + timedelta(days=offset)
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
            return day, availability
    raise RuntimeError("No second available day found for compound package fixture")


def _local_time(availability) -> str:
    return availability.slots[0].start_at.astimezone(ZoneInfo(availability.timezone)).strftime("%H:%M")


def _appointments(db: Session, patient_id):
    return list(
        db.scalars(
            select(Appointment)
            .where(Appointment.patient_id == patient_id)
            .order_by(Appointment.created_at.asc(), Appointment.id.asc())
        )
    )


def _package_usages(db: Session, package_id):
    return list(
        db.scalars(
            select(PackageUsage)
            .where(PackageUsage.patient_package_id == package_id)
            .order_by(PackageUsage.created_at.asc(), PackageUsage.id.asc())
        )
    )


def _result(name: str):
    return base.Result(name=name)


def _case_two_sessions_same_package(db: Session, workspace: Workspace):
    result = _result("two_sessions_same_existing_package_one_turn")
    patient = base._new_patient(db, workspace, "two-same-package")
    offer, service, doctor, day1, avail1 = base._offer_context(db, workspace)
    package = base._seed_package(db, workspace, patient, offer, key=f"compound-two-{patient.id}")
    day2, avail2 = _second_available_day(db, workspace, offer, doctor, day1, avail1)
    t1, t2 = _local_time(avail1), _local_time(avail2)
    service_name = str(service.get("name") or offer.service_name)
    doctor_name = str(doctor.get("name") or "الدكتور")
    message = (
        f"عايز أحجز جلستين {service_name} على جهاز {offer.device_name} مع {doctor_name}: "
        f"الأولى يوم {day1.isoformat()} الساعة {t1} والتانية يوم {day2.isoformat()} الساعة {t2}. "
        "احجز الاتنين دلوقتي"
    )
    response, duration = base._send(db, workspace, patient, message, None)
    result.turns = [base.Turn(message, response.reply, response.model, duration)]
    appointments = _appointments(db, patient.id)
    usages = _package_usages(db, package.id)
    result.db_checks = [
        f"appointment_count={len(appointments)}",
        f"package_ids={[str(row.patient_package_id) if row.patient_package_id else None for row in appointments]}",
        f"expected_package_id={package.id}",
        f"usage_count={len(usages)}",
        f"usage_statuses={[row.status for row in usages]}",
    ]
    return result


def _case_two_different_sessions(db: Session, workspace: Workspace):
    result = _result("two_different_sessions_one_turn")
    patient = base._new_patient(db, workspace, "two-different")
    offer1, service1, doctor1, day1, avail1 = base._offer_context(db, workspace)
    offer2, service2, doctor2, day2, avail2 = base._offer_context(
        db, workspace, exclude_service_id=offer1.service_id
    )
    message = (
        f"احجزلي {service1.get('name') or offer1.service_name} على جهاز {offer1.device_name} "
        f"مع {doctor1.get('name') or 'الدكتور'} يوم {day1.isoformat()} الساعة {_local_time(avail1)}، "
        f"وكمان {service2.get('name') or offer2.service_name} على جهاز {offer2.device_name} "
        f"مع {doctor2.get('name') or 'الدكتور'} يوم {day2.isoformat()} الساعة {_local_time(avail2)}. "
        "نفذ الحجزين دلوقتي"
    )
    response, duration = base._send(db, workspace, patient, message, None)
    result.turns = [base.Turn(message, response.reply, response.model, duration)]
    appointments = _appointments(db, patient.id)
    result.db_checks = [
        f"appointment_count={len(appointments)}",
        f"service_ids={[str(row.service_id) for row in appointments]}",
        f"expected_service_ids={[str(offer1.service_id), str(offer2.service_id)]}",
        f"package_ids={[str(row.patient_package_id) if row.patient_package_id else None for row in appointments]}",
    ]
    return result


def _compound_buy_book(db: Session, workspace: Workspace, *, booking_first: bool):
    name = "book_then_buy_same_package_one_turn" if booking_first else "buy_package_then_book_one_turn"
    result = _result(name)
    patient = base._new_patient(db, workspace, "book-first" if booking_first else "buy-first")
    offer, service, doctor, day, availability = base._offer_context(db, workspace)
    service_name = str(service.get("name") or offer.service_name)
    booking = (
        f"احجزلي أول جلسة {service_name} على جهاز {offer.device_name} مع {doctor.get('name') or 'الدكتور'} "
        f"يوم {day.isoformat()} الساعة {_local_time(availability)}"
    )
    buying = f"اشتريلي باكيدج {offer.sessions_count} جلسات {service_name} على جهاز {offer.device_name}"
    message = f"{booking}، وبالمرة {buying}. نفذ الاتنين دلوقتي" if booking_first else f"{buying}، وبعدها {booking}. نفذ الاتنين دلوقتي"
    response, duration = base._send(db, workspace, patient, message, None)
    result.turns = [base.Turn(message, response.reply, response.model, duration)]
    packages = list(db.scalars(select(PatientPackage).where(PatientPackage.patient_id == patient.id)))
    appointments = _appointments(db, patient.id)
    package = packages[-1] if packages else None
    usage = base._usage_for_appointment(db, workspace, appointments[-1]) if appointments else None
    result.db_checks = [
        f"package_count={len(packages)}",
        f"appointment_count={len(appointments)}",
        f"purchased_package_id={package.id if package else None}",
        f"appointment_package_id={appointments[-1].patient_package_id if appointments else None}",
        f"usage_package_id={usage.patient_package_id if usage else None}",
        f"usage_status={usage.status if usage else None}",
    ]
    return result


def _case_different_package_and_session(db: Session, workspace: Workspace):
    result = _result("buy_one_package_and_book_different_service_one_turn")
    patient = base._new_patient(db, workspace, "different-package")
    package_offer, package_service, _package_doctor, _package_day, _package_avail = base._offer_context(db, workspace)
    session_offer, session_service, session_doctor, session_day, session_avail = base._offer_context(
        db, workspace, exclude_service_id=package_offer.service_id
    )
    message = (
        f"اشتريلي باكيدج {package_offer.sessions_count} جلسات {package_service.get('name') or package_offer.service_name} "
        f"على جهاز {package_offer.device_name}، وكمان احجزلي جلسة {session_service.get('name') or session_offer.service_name} "
        f"على جهاز {session_offer.device_name} مع {session_doctor.get('name') or 'الدكتور'} "
        f"يوم {session_day.isoformat()} الساعة {_local_time(session_avail)}. نفذ الاتنين دلوقتي"
    )
    response, duration = base._send(db, workspace, patient, message, None)
    result.turns = [base.Turn(message, response.reply, response.model, duration)]
    packages = list(db.scalars(select(PatientPackage).where(PatientPackage.patient_id == patient.id)))
    appointments = _appointments(db, patient.id)
    result.db_checks = [
        f"package_count={len(packages)}",
        f"appointment_count={len(appointments)}",
        f"package_service_ids={[str(row.service_id) for row in packages]}",
        f"appointment_service_ids={[str(row.service_id) for row in appointments]}",
        f"appointment_package_ids={[str(row.patient_package_id) if row.patient_package_id else None for row in appointments]}",
        f"expected_package_service={package_offer.service_id}",
        f"expected_session_service={session_offer.service_id}",
    ]
    return result


CASES = [
    ("two_sessions_same_existing_package_one_turn", _case_two_sessions_same_package),
    ("two_different_sessions_one_turn", _case_two_different_sessions),
    ("buy_package_then_book_one_turn", lambda db, ws: _compound_buy_book(db, ws, booking_first=False)),
    ("book_then_buy_same_package_one_turn", lambda db, ws: _compound_buy_book(db, ws, booking_first=True)),
    ("buy_one_package_and_book_different_service_one_turn", _case_different_package_and_session),
]


def _execute(engine, slug: str, name: str, func):
    connection = engine.connect()
    outer = connection.begin()
    db = Session(bind=connection, expire_on_commit=False, join_transaction_mode="create_savepoint")
    try:
        workspace = db.scalar(select(Workspace).where(Workspace.slug == slug))
        if workspace is None:
            raise RuntimeError("Workspace not found")
        return func(db, workspace)
    except Exception as exc:
        return base.Result(name=name, error=f"{type(exc).__name__}: {exc}")
    finally:
        db.close()
        if outer.is_active:
            outer.rollback()
        connection.close()


def main() -> int:
    args = _args()
    if not settings.agent_v2_live_enabled:
        raise RuntimeError("Compound review refuses to run unless AGENT_V2_LIVE_ENABLED=true")
    engine = create_engine(settings.database_url, pool_pre_ping=True)
    results = []
    for index, (name, func) in enumerate(CASES, start=1):
        print(f"[compound-review {index:02d}/{len(CASES):02d}] {name}", flush=True)
        result = _execute(engine, args.workspace_slug, name, func)
        results.append(result)
        print(json.dumps(asdict(result), ensure_ascii=False, separators=(",", ":")), flush=True)
    payload = [asdict(row) for row in results]
    report = Path(args.report)
    report.parent.mkdir(parents=True, exist_ok=True)
    report.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    engine.dispose()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
