from __future__ import annotations

"""Rollback-only real-LLM review for compound same-anchor visit scheduling."""

import argparse
import json
from dataclasses import asdict
from datetime import UTC, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session

from app.agents.clinic_grounding import build_clinic_catalog
from app.core.config import settings
from app.integrations.clinic.base import AvailabilityRequest
from app.integrations.clinic.registry import get_clinic_adapter
from app.models.appointment import Appointment
from app.models.patient_package import PackageUsage, PatientPackage
from app.models.workspace import Workspace
from app.services.package_offers import list_package_offers
from scripts import run_v2_package_booking_review as base


def _args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--workspace-slug", default="tia")
    parser.add_argument("--report", default="artifacts/v2-compound-sequence-review.json")
    return parser.parse_args()


def _doctor_rows(catalog: dict[str, object], service_id: str, branch_id: str):
    rows = catalog.get("doctors")
    if not isinstance(rows, list):
        return []
    result = []
    for row in rows:
        if not isinstance(row, dict) or not row.get("id"):
            continue
        if service_id not in {str(item) for item in (row.get("service_ids") or [])}:
            continue
        scheduled = {
            str(item)
            for item in (row.get("scheduled_branch_ids") or row.get("branch_ids") or [])
            if item
        }
        if scheduled and branch_id not in scheduled:
            continue
        result.append(row)
    return result


def _device_rows(service: dict[str, object]):
    if service.get("requires_laser_device") is not True:
        return [(None, None)]
    rows = service.get("laser_devices")
    if not isinstance(rows, list):
        return []
    result = []
    for row in rows:
        if not isinstance(row, dict) or not row.get("device_key"):
            continue
        result.append((str(row["device_key"]), str(row.get("device_name") or row["device_key"])))
    return result


def _availability(adapter, branch_id: str, service_id: str, doctor_id: str, day, device_key):
    return adapter.get_availability(
        AvailabilityRequest(
            branch_id=branch_id,
            service_id=service_id,
            booking_date=day,
            doctor_id=doctor_id,
            laser_device_key=device_key,
        )
    )


def _spec(service, doctor, availability, slot, device_key, device_name):
    return {
        "service_id": str(service["id"]),
        "service_name": str(service.get("name") or "الخدمة"),
        "doctor_id": str(doctor["id"]),
        "doctor_name": str(doctor.get("name") or "الدكتور"),
        "device_key": device_key,
        "device_name": device_name,
        "timezone": availability.timezone,
        "day": slot.start_at.astimezone(ZoneInfo(availability.timezone)).date(),
        "start_at": slot.start_at,
        "duration_minutes": int(slot.duration_minutes),
    }


def _service_phrase(spec) -> str:
    phrase = f"{spec['service_name']} مع {spec['doctor_name']}"
    if spec.get("device_name"):
        phrase += f" على جهاز {spec['device_name']}"
    return phrase


def _local_time(spec) -> str:
    return spec["start_at"].astimezone(ZoneInfo(spec["timezone"])).strftime("%H:%M")


def _find_sequence_pair(db: Session, workspace: Workspace, *, package_position: str | None = None):
    catalog = build_clinic_catalog(db, workspace)
    services = [row for row in (catalog.get("services") or []) if isinstance(row, dict) and row.get("id")]
    branch_id = str(workspace.primary_branch_id or "")
    if not branch_id:
        raise RuntimeError("Staging workspace has no primary branch")
    adapter = get_clinic_adapter(db=db, workspace=workspace)
    today = base.datetime.now(UTC).date()

    offers = list_package_offers(db, workspace_id=workspace.id, active_only=True) if package_position else []
    offer_by_scope = {
        (str(offer.service_id), str(offer.device_key) if offer.device_key else None): offer
        for offer in offers
    }

    for offset in range(1, 30):
        day = today + timedelta(days=offset)
        for first_service in services:
            first_id = str(first_service["id"])
            for first_device_key, first_device_name in _device_rows(first_service):
                if package_position == "first" and (first_id, first_device_key) not in offer_by_scope:
                    continue
                for first_doctor in _doctor_rows(catalog, first_id, branch_id):
                    first_availability = _availability(
                        adapter,
                        branch_id,
                        first_id,
                        str(first_doctor["id"]),
                        day,
                        first_device_key,
                    )
                    for first_slot in first_availability.slots[:8]:
                        target = first_slot.start_at + timedelta(minutes=int(first_slot.duration_minutes))
                        for second_service in services:
                            second_id = str(second_service["id"])
                            if second_id == first_id:
                                continue
                            for second_device_key, second_device_name in _device_rows(second_service):
                                if package_position == "second" and (
                                    second_id,
                                    second_device_key,
                                ) not in offer_by_scope:
                                    continue
                                for second_doctor in _doctor_rows(catalog, second_id, branch_id):
                                    second_availability = _availability(
                                        adapter,
                                        branch_id,
                                        second_id,
                                        str(second_doctor["id"]),
                                        day,
                                        second_device_key,
                                    )
                                    second_slot = next(
                                        (
                                            slot
                                            for slot in second_availability.slots
                                            if slot.start_at == target
                                        ),
                                        None,
                                    )
                                    if second_slot is None:
                                        continue
                                    first = _spec(
                                        first_service,
                                        first_doctor,
                                        first_availability,
                                        first_slot,
                                        first_device_key,
                                        first_device_name,
                                    )
                                    second = _spec(
                                        second_service,
                                        second_doctor,
                                        second_availability,
                                        second_slot,
                                        second_device_key,
                                        second_device_name,
                                    )
                                    package_offer = None
                                    if package_position == "first":
                                        package_offer = offer_by_scope[(first_id, first_device_key)]
                                    elif package_position == "second":
                                        package_offer = offer_by_scope[(second_id, second_device_key)]
                                    return first, second, package_offer
    raise RuntimeError(f"No sequential staging fixture found package_position={package_position}")


def _appointments(db: Session, patient_id):
    return list(
        db.scalars(
            select(Appointment)
            .where(Appointment.patient_id == patient_id)
            .order_by(Appointment.start_at.asc(), Appointment.id.asc())
        )
    )


def _appointment_checks(rows):
    return [
        f"appointment_count={len(rows)}",
        f"service_ids={[str(row.service_id) for row in rows]}",
        f"starts={[row.start_at.isoformat() for row in rows]}",
        f"ends={[row.end_at.isoformat() for row in rows]}",
        f"package_ids={[str(row.patient_package_id) if row.patient_package_id else None for row in rows]}",
    ]


def _run_one_message(db, workspace, patient, name: str, message: str):
    result = base.Result(name=name)
    response, duration = base._send(db, workspace, patient, message, None)
    result.turns = [base.Turn(message, response.reply, response.model, duration)]
    rows = _appointments(db, patient.id)
    result.db_checks = _appointment_checks(rows)
    return result


def _case_two_services_implicit(db: Session, workspace: Workspace):
    patient = base._new_patient(db, workspace, "seq-implicit")
    first, second, _ = _find_sequence_pair(db, workspace)
    anchor = _local_time(first)
    message = (
        f"احجزلي {_service_phrase(first)} و{_service_phrase(second)} يوم {first['day'].isoformat()} "
        f"الساعة {anchor}. نفذ الحجزين دلوقتي"
    )
    result = _run_one_message(db, workspace, patient, "two_services_same_anchor_implicit", message)
    result.db_checks.extend(
        [
            f"requested_anchor={first['start_at'].isoformat()}",
            f"expected_second_start={second['start_at'].isoformat()}",
            f"first_duration_minutes={first['duration_minutes']}",
        ]
    )
    return result


def _case_two_services_after_wording(db: Session, workspace: Workspace):
    patient = base._new_patient(db, workspace, "seq-after")
    first, second, _ = _find_sequence_pair(db, workspace)
    anchor = _local_time(first)
    message = (
        f"عايز أعمل {_service_phrase(first)} وبعدها {_service_phrase(second)} يوم {first['day'].isoformat()}. "
        f"أنا مناسبني الساعة {anchor}، احجزهم"
    )
    result = _run_one_message(db, workspace, patient, "two_services_same_anchor_after_wording", message)
    result.db_checks.extend(
        [
            f"requested_anchor={first['start_at'].isoformat()}",
            f"expected_second_start={second['start_at'].isoformat()}",
        ]
    )
    return result


def _case_book_then_buy_same_service(db: Session, workspace: Workspace):
    patient = base._new_patient(db, workspace, "seq-book-buy")
    offer, service, doctor, day, availability = base._offer_context(db, workspace)
    slot = availability.slots[0]
    local = slot.start_at.astimezone(ZoneInfo(availability.timezone))
    device = f" على جهاز {offer.device_name}" if offer.device_name else ""
    message = (
        f"احجزلي أول جلسة {service.get('name') or offer.service_name}{device} مع {doctor.get('name') or 'الدكتور'} "
        f"يوم {day.isoformat()} الساعة {local.strftime('%H:%M')}، وبالمرة اشتريلي باكيدج "
        f"{offer.sessions_count} جلسات لنفس الخدمة{device}. نفذ الاتنين"
    )
    result = _run_one_message(db, workspace, patient, "book_then_buy_same_service_dependency", message)
    packages = list(db.scalars(select(PatientPackage).where(PatientPackage.patient_id == patient.id)))
    rows = _appointments(db, patient.id)
    usage = base._usage_for_appointment(db, workspace, rows[-1]) if rows else None
    result.db_checks.extend(
        [
            f"package_count={len(packages)}",
            f"purchased_package_id={packages[-1].id if packages else None}",
            f"appointment_package_id={rows[-1].patient_package_id if rows else None}",
            f"usage_package_id={usage.patient_package_id if usage else None}",
            f"usage_status={usage.status if usage else None}",
        ]
    )
    return result


def _case_service_then_other_package(db: Session, workspace: Workspace):
    patient = base._new_patient(db, workspace, "seq-service-package")
    first, second, offer = _find_sequence_pair(db, workspace, package_position="second")
    assert offer is not None
    anchor = _local_time(first)
    second_device = f" على جهاز {second['device_name']}" if second.get("device_name") else ""
    message = (
        f"احجزلي {_service_phrase(first)} يوم {first['day'].isoformat()} الساعة {anchor}، وكمان اشتريلي "
        f"باكيدج {offer.sessions_count} جلسات {second['service_name']}{second_device} واحجز أول جلسة منها "
        f"مع {second['doctor_name']} في نفس اليوم الساعة {anchor}. نفذ الكل"
    )
    result = _run_one_message(db, workspace, patient, "service_then_other_package_same_anchor", message)
    packages = list(db.scalars(select(PatientPackage).where(PatientPackage.patient_id == patient.id)))
    rows = _appointments(db, patient.id)
    result.db_checks.extend(
        [
            f"package_count={len(packages)}",
            f"expected_first_start={first['start_at'].isoformat()}",
            f"expected_second_start={second['start_at'].isoformat()}",
        ]
    )
    if rows:
        usages = list(
            db.scalars(
                select(PackageUsage).where(PackageUsage.appointment_id.in_([row.id for row in rows]))
            )
        )
        result.db_checks.append(
            f"usage_links={[(str(row.appointment_id), str(row.patient_package_id), row.status) for row in usages]}"
        )
    return result


def _case_package_then_other_service(db: Session, workspace: Workspace):
    patient = base._new_patient(db, workspace, "seq-package-service")
    first, second, offer = _find_sequence_pair(db, workspace, package_position="first")
    assert offer is not None
    anchor = _local_time(first)
    first_device = f" على جهاز {first['device_name']}" if first.get("device_name") else ""
    message = (
        f"اشتريلي باكيدج {offer.sessions_count} جلسات {first['service_name']}{first_device} واحجز أول جلسة منها "
        f"مع {first['doctor_name']} يوم {first['day'].isoformat()} الساعة {anchor}، وكمان احجزلي "
        f"{_service_phrase(second)} في نفس اليوم الساعة {anchor}. نفذ الكل"
    )
    result = _run_one_message(db, workspace, patient, "package_then_other_service_same_anchor", message)
    packages = list(db.scalars(select(PatientPackage).where(PatientPackage.patient_id == patient.id)))
    rows = _appointments(db, patient.id)
    result.db_checks.extend(
        [
            f"package_count={len(packages)}",
            f"expected_first_start={first['start_at'].isoformat()}",
            f"expected_second_start={second['start_at'].isoformat()}",
        ]
    )
    return result


def _case_repeat_natural_phrase(db: Session, workspace: Workspace):
    patient = base._new_patient(db, workspace, "seq-natural")
    first, second, _ = _find_sequence_pair(db, workspace)
    anchor = _local_time(first)
    message = (
        f"ممكن تحجزلي يوم {first['day'].isoformat()} الساعة {anchor} {_service_phrase(first)}، "
        f"وعايز في نفس الزيارة {_service_phrase(second)} كمان الساعة {anchor}"
    )
    result = _run_one_message(db, workspace, patient, "same_visit_natural_phrase", message)
    result.db_checks.extend(
        [
            f"expected_first_start={first['start_at'].isoformat()}",
            f"expected_second_start={second['start_at'].isoformat()}",
        ]
    )
    return result


CASES = [
    ("two_services_same_anchor_implicit", _case_two_services_implicit),
    ("two_services_same_anchor_after_wording", _case_two_services_after_wording),
    ("same_visit_natural_phrase", _case_repeat_natural_phrase),
    ("book_then_buy_same_service_dependency", _case_book_then_buy_same_service),
    ("service_then_other_package_same_anchor", _case_service_then_other_package),
    ("package_then_other_service_same_anchor", _case_package_then_other_service),
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
        raise RuntimeError("Compound sequence review requires AGENT_V2_LIVE_ENABLED=true")
    engine = create_engine(settings.database_url, pool_pre_ping=True)
    results = []
    for index, (name, func) in enumerate(CASES, start=1):
        print(f"[compound-sequence {index:02d}/{len(CASES):02d}] {name}", flush=True)
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
