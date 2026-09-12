from __future__ import annotations

"""Rollback-only follow-up review for the remaining V2 package booking cases."""

import argparse
import json
from dataclasses import asdict
from pathlib import Path
from zoneinfo import ZoneInfo

from sqlalchemy import create_engine, func, select
from sqlalchemy.orm import Session

from app.core.config import settings
from app.models.appointment import Appointment
from app.models.patient_package import PackageUsage
from app.models.workspace import Workspace
from scripts import run_v2_package_booking_review as base


def _args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--workspace-slug", default="tia")
    parser.add_argument("--report", default="artifacts/v2-package-booking-followup-review.json")
    return parser.parse_args()


def _auto_confirmation(engine, slug: str) -> base.Result:
    result = base._execute(engine, slug, "auto_existing_package_without_mention")
    confirmation = result.turns[-1].assistant if result.turns else None
    mentions_package = bool(confirmation and ("باكيدج" in confirmation or "package" in confirmation.casefold()))
    result.name = "auto_package_confirmation_mentions_usage"
    result.db_checks.append(f"confirmation_mentions_package={mentions_package}")
    return result


def _device_explicit(engine, slug: str) -> base.Result:
    connection = engine.connect()
    outer = connection.begin()
    db = Session(bind=connection, expire_on_commit=False, join_transaction_mode="create_savepoint")
    result = base.Result(name="same_service_different_device_explicit_booking")
    try:
        workspace = db.scalar(select(Workspace).where(Workspace.slug == slug))
        if workspace is None:
            raise RuntimeError("Workspace not found")
        patient = base._new_patient(db, workspace, "device-explicit")
        offer_a, _service_a, _doctor_a, _day_a, _availability_a = base._offer_context(db, workspace)
        package = base._seed_package(
            db,
            workspace,
            patient,
            offer_a,
            key=f"review-device-explicit-{patient.id}",
        )
        offer_b, service_b, doctor_b, day_b, availability_b = base._offer_context(
            db,
            workspace,
            service_id=offer_a.service_id,
            exclude_device_key=offer_a.device_key,
        )
        before_usage = db.scalar(
            select(func.count(PackageUsage.id)).where(PackageUsage.patient_package_id == package.id)
        ) or 0
        before_appointments = db.scalar(
            select(func.count(Appointment.id)).where(Appointment.patient_id == patient.id)
        ) or 0

        service_name = str(service_b.get("name") or offer_b.service_name)
        doctor_name = str(doctor_b.get("name") or "الدكتور")
        first = (
            f"عايز أحجز {service_name} على جهاز {offer_b.device_name} مع {doctor_name} "
            f"يوم {day_b.isoformat()}، إيه المواعيد المتاحة؟"
        )
        one, d1 = base._send(db, workspace, patient, first, None)
        slot = availability_b.slots[0]
        local = slot.start_at.astimezone(ZoneInfo(availability_b.timezone))
        second = (
            f"تمام احجزلي يوم {day_b.isoformat()} الساعة {local.strftime('%H:%M')} "
            f"مع {doctor_name} على جهاز {offer_b.device_name}"
        )
        two, d2 = base._send(db, workspace, patient, second, one.conversation_id)
        result.turns = [
            base.Turn(first, one.reply, one.model, d1),
            base.Turn(second, two.reply, two.model, d2),
        ]

        created = base._new_appointments(db, workspace, patient, int(before_appointments))
        appointment = created[-1] if created else None
        after_usage = db.scalar(
            select(func.count(PackageUsage.id)).where(PackageUsage.patient_package_id == package.id)
        ) or 0
        result.db_checks.extend(
            [
                f"appointment_delta={len(created)}",
                f"package_device={offer_a.device_key}",
                f"booked_device={offer_b.device_key}",
                f"appointment_device={appointment.laser_device_key if appointment else None}",
                f"appointment_package_id={appointment.patient_package_id if appointment else None}",
                f"mismatched_package_usage_delta={int(after_usage) - int(before_usage)}",
            ]
        )
        return result
    except Exception as exc:
        result.error = f"{type(exc).__name__}: {exc}"
        return result
    finally:
        db.close()
        if outer.is_active:
            outer.rollback()
        connection.close()


def main() -> int:
    args = _args()
    if not settings.agent_v2_live_enabled:
        raise RuntimeError("Follow-up review refuses to run unless AGENT_V2_LIVE_ENABLED=true")
    engine = create_engine(settings.database_url, pool_pre_ping=True)
    results = [
        _auto_confirmation(engine, args.workspace_slug),
        _device_explicit(engine, args.workspace_slug),
    ]
    payload = [asdict(result) for result in results]
    for row in payload:
        print(json.dumps(row, ensure_ascii=False, separators=(",", ":")), flush=True)
    report = Path(args.report)
    report.parent.mkdir(parents=True, exist_ok=True)
    report.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    engine.dispose()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
