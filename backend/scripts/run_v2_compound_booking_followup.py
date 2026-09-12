from __future__ import annotations

"""Rollback-only follow-up for two different non-overlapping session bookings."""

import argparse
import json
from dataclasses import asdict
from pathlib import Path
from zoneinfo import ZoneInfo

from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from app.core.config import settings
from app.models.workspace import Workspace
from scripts import run_v2_compound_booking_review as compound
from scripts import run_v2_package_booking_review as base


def _args():
    parser = argparse.ArgumentParser()
    parser.add_argument("--workspace-slug", default="tia")
    parser.add_argument("--report", default="artifacts/v2-compound-booking-followup.json")
    return parser.parse_args()


def _run(db: Session, workspace: Workspace):
    result = base.Result(name="two_different_sessions_non_overlapping_one_turn")
    patient = base._new_patient(db, workspace, "two-different-followup")
    offer1, service1, doctor1, day1, avail1 = base._offer_context(db, workspace)
    offer2, service2, doctor2, first_day2, first_avail2 = base._offer_context(
        db, workspace, exclude_service_id=offer1.service_id
    )
    day2, avail2 = compound._second_available_day(
        db, workspace, offer2, doctor2, max(first_day2, day1), first_avail2
    )
    t1 = avail1.slots[0].start_at.astimezone(ZoneInfo(avail1.timezone)).strftime("%H:%M")
    t2 = avail2.slots[0].start_at.astimezone(ZoneInfo(avail2.timezone)).strftime("%H:%M")
    message = (
        f"احجزلي {service1.get('name') or offer1.service_name} على جهاز {offer1.device_name} "
        f"مع {doctor1.get('name') or 'الدكتور'} يوم {day1.isoformat()} الساعة {t1}، "
        f"وكمان {service2.get('name') or offer2.service_name} على جهاز {offer2.device_name} "
        f"مع {doctor2.get('name') or 'الدكتور'} يوم {day2.isoformat()} الساعة {t2}. "
        "نفذ الحجزين دلوقتي"
    )
    response, duration = base._send(db, workspace, patient, message, None)
    result.turns = [base.Turn(message, response.reply, response.model, duration)]
    appointments = compound._appointments(db, patient.id)
    result.db_checks = [
        f"appointment_count={len(appointments)}",
        f"service_ids={[str(row.service_id) for row in appointments]}",
        f"expected_service_ids={[str(offer1.service_id), str(offer2.service_id)]}",
        f"start_dates={[row.start_at.date().isoformat() for row in appointments]}",
        f"package_ids={[str(row.patient_package_id) if row.patient_package_id else None for row in appointments]}",
    ]
    return result


def main() -> int:
    args = _args()
    if not settings.agent_v2_live_enabled:
        raise RuntimeError("Compound follow-up refuses to run unless AGENT_V2_LIVE_ENABLED=true")
    engine = create_engine(settings.database_url, pool_pre_ping=True)
    connection = engine.connect()
    outer = connection.begin()
    db = Session(bind=connection, expire_on_commit=False, join_transaction_mode="create_savepoint")
    try:
        workspace = db.query(Workspace).filter(Workspace.slug == args.workspace_slug).one()
        result = _run(db, workspace)
        print(json.dumps(asdict(result), ensure_ascii=False, separators=(",", ":")), flush=True)
        report = Path(args.report)
        report.parent.mkdir(parents=True, exist_ok=True)
        report.write_text(json.dumps([asdict(result)], ensure_ascii=False, indent=2), encoding="utf-8")
    finally:
        db.close()
        if outer.is_active:
            outer.rollback()
        connection.close()
        engine.dispose()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
