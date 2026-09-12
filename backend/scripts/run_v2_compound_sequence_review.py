from __future__ import annotations

"""Rollback-only real-LLM review for compound same-anchor visit scheduling."""

import argparse
import json
from dataclasses import asdict
from datetime import UTC, timedelta
from pathlib import Path
from uuid import UUID
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
from app.services.appointment_creation import create_appointment_operation
from app.services.package_offers import list_package_offers
from scripts import run_v2_package_booking_review as base

_PAIR_CACHE: dict[str, tuple[dict[str, object], dict[str, object], dict[str, object] | None]] = {}
_OCCUPIED_PAIR_CACHE: tuple[dict[str, object], dict[str, object]] | None = None


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
        if not scheduled or branch_id in scheduled:
            result.append(row)
    return result[:2]


def _device_rows(service: dict[str, object]):
    if service.get("requires_laser_device") is not True:
        return [(None, None)]
    rows = service.get("laser_devices")
    if not isinstance(rows, list):
        return []
    return [
        (str(row["device_key"]), str(row.get("device_name") or row["device_key"]))
        for row in rows[:2]
        if isinstance(row, dict) and row.get("device_key")
    ]


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
        "end_at": slot.end_at,
        "duration_minutes": int(slot.duration_minutes),
    }


def _service_phrase(spec: dict[str, object]) -> str:
    phrase = f"{spec['service_name']} مع {spec['doctor_name']}"
    if spec.get("device_name"):
        phrase += f" على جهاز {spec['device_name']}"
    return phrase


def _local_time(spec: dict[str, object]) -> str:
    return spec["start_at"].astimezone(ZoneInfo(str(spec["timezone"]))).strftime("%H:%M")


def _catalog_combos(catalog: dict[str, object], branch_id: str):
    services = [
        row
        for row in (catalog.get("services") or [])
        if isinstance(row, dict) and row.get("id")
    ]
    combos: list[tuple[dict[str, object], dict[str, object], str | None, str | None]] = []
    for service in services:
        service_id = str(service["id"])
        for device_key, device_name in _device_rows(service):
            for doctor in _doctor_rows(catalog, service_id, branch_id):
                combos.append((service, doctor, device_key, device_name))
    return combos


def _find_sequence_pair(db: Session, workspace: Workspace, *, package_position: str | None = None):
    cache_key = package_position or "none"
    cached = _PAIR_CACHE.get(cache_key)
    if cached is not None:
        return cached

    catalog = build_clinic_catalog(db, workspace)
    branch_id = str(workspace.primary_branch_id or "")
    if not branch_id:
        raise RuntimeError("Staging workspace has no primary branch")
    adapter = get_clinic_adapter(db=db, workspace=workspace)
    today = base.datetime.now(UTC).date()

    offers = (
        list_package_offers(db, workspace_id=workspace.id, active_only=True)
        if package_position
        else []
    )
    offer_by_scope = {
        (str(offer.service_id), str(offer.device_key) if offer.device_key else None): {
            "sessions_count": int(offer.sessions_count),
            "service_id": str(offer.service_id),
            "device_key": str(offer.device_key) if offer.device_key else None,
        }
        for offer in offers
    }
    combos = _catalog_combos(catalog, branch_id)

    for offset in range(1, 15):
        day = today + timedelta(days=offset)
        available: list[tuple[dict[str, object], dict[str, object], str | None, str | None, object]] = []
        for service, doctor, device_key, device_name in combos:
            service_id = str(service["id"])
            scope = (service_id, device_key)
            if package_position == "first" and scope not in offer_by_scope:
                continue
            availability = adapter.get_availability(
                AvailabilityRequest(
                    branch_id=branch_id,
                    service_id=service_id,
                    booking_date=day,
                    doctor_id=str(doctor["id"]),
                    laser_device_key=device_key,
                )
            )
            if availability.slots:
                available.append((service, doctor, device_key, device_name, availability))

        second_index: dict[object, list[tuple]] = {}
        for row in available:
            service, _doctor, device_key, _device_name, availability = row
            service_id = str(service["id"])
            if package_position == "second" and (service_id, device_key) not in offer_by_scope:
                continue
            for slot in availability.slots:
                second_index.setdefault(slot.start_at, []).append((*row, slot))

        for first_service, first_doctor, first_device_key, first_device_name, first_availability in available:
            first_id = str(first_service["id"])
            if package_position == "first" and (first_id, first_device_key) not in offer_by_scope:
                continue
            for first_slot in first_availability.slots[:10]:
                for second_row in second_index.get(first_slot.end_at, []):
                    (
                        second_service,
                        second_doctor,
                        second_device_key,
                        second_device_name,
                        second_availability,
                        second_slot,
                    ) = second_row
                    second_id = str(second_service["id"])
                    if second_id == first_id:
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
                    package = None
                    if package_position == "first":
                        package = offer_by_scope[(first_id, first_device_key)]
                    elif package_position == "second":
                        package = offer_by_scope[(second_id, second_device_key)]
                    result = (first, second, package)
                    _PAIR_CACHE[cache_key] = result
                    return result
    raise RuntimeError(f"No sequential staging fixture found package_position={package_position}")


def _find_occupied_sequence_pair(db: Session, workspace: Workspace):
    global _OCCUPIED_PAIR_CACHE
    if _OCCUPIED_PAIR_CACHE is not None:
        return _OCCUPIED_PAIR_CACHE

    catalog = build_clinic_catalog(db, workspace)
    branch_id = str(workspace.primary_branch_id or "")
    if not branch_id:
        raise RuntimeError("Staging workspace has no primary branch")
    adapter = get_clinic_adapter(db=db, workspace=workspace)
    today = base.datetime.now(UTC).date()
    combos = _catalog_combos(catalog, branch_id)

    for offset in range(1, 15):
        day = today + timedelta(days=offset)
        available: list[tuple[dict[str, object], dict[str, object], str | None, str | None, object]] = []
        for service, doctor, device_key, device_name in combos:
            availability = adapter.get_availability(
                AvailabilityRequest(
                    branch_id=branch_id,
                    service_id=str(service["id"]),
                    booking_date=day,
                    doctor_id=str(doctor["id"]),
                    laser_device_key=device_key,
                )
            )
            if availability.slots:
                available.append((service, doctor, device_key, device_name, availability))

        second_index: dict[object, list[tuple]] = {}
        for row in available:
            _service, _doctor, _device_key, _device_name, availability = row
            for slot in availability.slots:
                second_index.setdefault(slot.start_at, []).append((*row, slot))

        for first_service, first_doctor, first_device_key, first_device_name, first_availability in available:
            first_id = str(first_service["id"])
            for first_slot in first_availability.slots[:10]:
                for second_row in second_index.get(first_slot.end_at, []):
                    (
                        second_service,
                        second_doctor,
                        second_device_key,
                        second_device_name,
                        second_availability,
                        second_slot,
                    ) = second_row
                    if str(second_service["id"]) == first_id:
                        continue
                    if str(second_doctor["id"]) == str(first_doctor["id"]):
                        continue
                    if (
                        first_device_key is not None
                        and second_device_key is not None
                        and first_device_key == second_device_key
                    ):
                        continue
                    if not any(slot.start_at > second_slot.start_at for slot in second_availability.slots):
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
                    _OCCUPIED_PAIR_CACHE = (first, second)
                    return _OCCUPIED_PAIR_CACHE
    raise RuntimeError("No occupied-slot compound fixture with distinct resources was found")


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
    result.db_checks = _appointment_checks(_appointments(db, patient.id))
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
    result.db_checks += [
        f"requested_anchor={first['start_at'].isoformat()}",
        f"naive_second_start={second['start_at'].isoformat()}",
    ]
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
    result.db_checks += [
        f"expected_first_start={first['start_at'].isoformat()}",
        f"naive_second_start={second['start_at'].isoformat()}",
    ]
    return result


def _case_natural(db: Session, workspace: Workspace):
    patient = base._new_patient(db, workspace, "seq-natural")
    first, second, _ = _find_sequence_pair(db, workspace)
    anchor = _local_time(first)
    message = (
        f"ممكن تحجزلي يوم {first['day'].isoformat()} الساعة {anchor} {_service_phrase(first)}، "
        f"وعايز في نفس الزيارة {_service_phrase(second)} كمان الساعة {anchor}"
    )
    result = _run_one_message(db, workspace, patient, "same_visit_natural_phrase", message)
    result.db_checks += [
        f"expected_first_start={first['start_at'].isoformat()}",
        f"naive_second_start={second['start_at'].isoformat()}",
    ]
    return result


def _case_book_then_buy_same(db: Session, workspace: Workspace):
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
    result.db_checks += [
        f"package_count={len(packages)}",
        f"purchased_package_id={packages[-1].id if packages else None}",
        f"appointment_package_id={rows[-1].patient_package_id if rows else None}",
        f"usage_package_id={usage.patient_package_id if usage else None}",
        f"usage_status={usage.status if usage else None}",
    ]
    return result


def _compound_other_package(db: Session, workspace: Workspace, *, package_first: bool):
    label = "package-first" if package_first else "service-first"
    patient = base._new_patient(db, workspace, f"seq-{label}")
    package_position = "first" if package_first else "second"
    first, second, offer = _find_sequence_pair(db, workspace, package_position=package_position)
    assert offer is not None
    package_spec = first if package_first else second
    standalone_spec = second if package_first else first
    anchor = _local_time(first)
    package_device = f" على جهاز {package_spec['device_name']}" if package_spec.get("device_name") else ""
    package_request = (
        f"اشتريلي باكيدج {offer['sessions_count']} جلسات {package_spec['service_name']}{package_device} "
        f"واحجز أول جلسة منها مع {package_spec['doctor_name']} في نفس اليوم الساعة {anchor}"
    )
    standalone_request = (
        f"احجزلي {_service_phrase(standalone_spec)} يوم {first['day'].isoformat()} الساعة {anchor}"
    )
    message = (
        f"{package_request}، وكمان {standalone_request}. نفذ الكل"
        if package_first
        else f"{standalone_request}، وكمان {package_request}. نفذ الكل"
    )
    result = _run_one_message(
        db,
        workspace,
        patient,
        "package_then_other_service_same_anchor" if package_first else "service_then_other_package_same_anchor",
        message,
    )
    packages = list(db.scalars(select(PatientPackage).where(PatientPackage.patient_id == patient.id)))
    rows = _appointments(db, patient.id)
    usages = (
        list(db.scalars(select(PackageUsage).where(PackageUsage.appointment_id.in_([row.id for row in rows]))))
        if rows
        else []
    )
    result.db_checks += [
        f"package_count={len(packages)}",
        f"expected_first_start={first['start_at'].isoformat()}",
        f"naive_second_start={second['start_at'].isoformat()}",
        f"usage_links={[(str(row.appointment_id), str(row.patient_package_id), row.status) for row in usages]}",
    ]
    return result


def _case_second_naive_slot_is_occupied(db: Session, workspace: Workspace):
    patient = base._new_patient(db, workspace, "seq-occupied-main")
    blocker_patient = base._new_patient(db, workspace, "seq-occupied-blocker")
    first, second = _find_occupied_sequence_pair(db, workspace)
    branch_id = workspace.primary_branch_id
    if branch_id is None:
        raise RuntimeError("Staging workspace has no primary branch")

    blocker = create_appointment_operation(
        db,
        workspace=workspace,
        patient_id=blocker_patient.id,
        branch_id=branch_id,
        doctor_id=UUID(str(second["doctor_id"])),
        service_id=UUID(str(second["service_id"])),
        requested_start_at=second["start_at"],
        created_by_user_id=None,
        patient_package_id=None,
        source="ai",
        laser_device_key=str(second["device_key"]) if second.get("device_key") else None,
        idempotency_key=f"v2-compound-blocker:{blocker_patient.id}:{second['start_at'].isoformat()}",
        actor_type="ai",
    )

    adapter = get_clinic_adapter(db=db, workspace=workspace)
    after_blocker = adapter.get_availability(
        AvailabilityRequest(
            branch_id=str(branch_id),
            service_id=str(second["service_id"]),
            booking_date=second["day"],
            doctor_id=str(second["doctor_id"]),
            laser_device_key=str(second["device_key"]) if second.get("device_key") else None,
        )
    )
    next_slot = next(
        (slot for slot in after_blocker.slots if slot.start_at > second["start_at"]),
        None,
    )
    if next_slot is None:
        raise RuntimeError("Occupied compound fixture has no later verified slot")

    anchor = _local_time(first)
    message = (
        f"احجزلي {_service_phrase(first)} وبعدها {_service_phrase(second)} يوم {first['day'].isoformat()} "
        f"من الساعة {anchor}. عايزهم ورا بعض ونفذ الحجزين"
    )
    result = _run_one_message(
        db,
        workspace,
        patient,
        "second_compound_slot_occupied_shift_next",
        message,
    )
    result.db_checks += [
        f"blocker_appointment_id={blocker.id}",
        f"blocked_naive_second_start={second['start_at'].isoformat()}",
        f"expected_next_verified_start={next_slot.start_at.isoformat()}",
        f"first_resource_doctor={first['doctor_id']}",
        f"second_resource_doctor={second['doctor_id']}",
        f"first_device={first.get('device_key')}",
        f"second_device={second.get('device_key')}",
    ]
    return result


CASES = [
    ("two_services_same_anchor_implicit", _case_two_services_implicit),
    ("two_services_same_anchor_after_wording", _case_two_services_after_wording),
    ("same_visit_natural_phrase", _case_natural),
    ("book_then_buy_same_service_dependency", _case_book_then_buy_same),
    ("service_then_other_package_same_anchor", lambda db, ws: _compound_other_package(db, ws, package_first=False)),
    ("package_then_other_service_same_anchor", lambda db, ws: _compound_other_package(db, ws, package_first=True)),
    ("second_compound_slot_occupied_shift_next", _case_second_naive_slot_is_occupied),
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
