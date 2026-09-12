from __future__ import annotations

"""Rollback-only real-LLM review for a compound visit whose second naive slot is occupied."""

import argparse
import json
from dataclasses import asdict
from datetime import UTC
from pathlib import Path
from uuid import UUID

from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session

from app.core.config import settings
from app.integrations.clinic.base import AvailabilityRequest
from app.integrations.clinic.registry import get_clinic_adapter
from app.models.workspace import Workspace
from app.services.appointment_creation import create_appointment_operation
from scripts import run_v2_compound_sequence_review as seq
from scripts import run_v2_package_booking_review as base


def _args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--workspace-slug", default="tia")
    parser.add_argument("--report", default="artifacts/v2-compound-occupied-review.json")
    return parser.parse_args()


def _run_case(db: Session, workspace: Workspace):
    patient = base._new_patient(db, workspace, "seq-occupied-main")
    blocker_patient = base._new_patient(db, workspace, "seq-occupied-blocker")

    # Reuse a fixture with different doctors/resources so the blocker only removes
    # the naive second session; it must not invalidate the first service itself.
    first, second, _offer = seq._find_sequence_pair(db, workspace, package_position="second")
    if str(first["doctor_id"]) == str(second["doctor_id"]):
        raise RuntimeError("Occupied fixture unexpectedly uses the same doctor")
    first_device = first.get("device_key")
    second_device = second.get("device_key")
    if first_device is not None and second_device is not None and first_device == second_device:
        raise RuntimeError("Occupied fixture unexpectedly uses the same laser device")

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
        laser_device_key=str(second_device) if second_device else None,
        idempotency_key=f"v2-compound-blocker:{blocker_patient.id}:{second['start_at'].isoformat()}",
        actor_type="ai",
    )

    adapter = get_clinic_adapter(db=db, workspace=workspace)
    second_live = adapter.get_availability(
        AvailabilityRequest(
            branch_id=str(branch_id),
            service_id=str(second["service_id"]),
            booking_date=second["day"],
            doctor_id=str(second["doctor_id"]),
            laser_device_key=str(second_device) if second_device else None,
            now=base.datetime.now(UTC),
        )
    )
    first_live = adapter.get_availability(
        AvailabilityRequest(
            branch_id=str(branch_id),
            service_id=str(first["service_id"]),
            booking_date=first["day"],
            doctor_id=str(first["doctor_id"]),
            laser_device_key=str(first_device) if first_device else None,
            now=base.datetime.now(UTC),
        )
    )
    if not any(slot.start_at == first["start_at"] for slot in first_live.slots):
        raise RuntimeError("Blocker unexpectedly invalidated the first session")
    if any(slot.start_at == second["start_at"] for slot in second_live.slots):
        raise RuntimeError("Blocker did not remove the naive second session")

    second_by_start = {slot.start_at: slot for slot in second_live.slots}
    joint_pair = next(
        (
            (first_slot, second_by_start[first_slot.end_at])
            for first_slot in first_live.slots
            if first_slot.start_at >= first["start_at"] and first_slot.end_at in second_by_start
        ),
        None,
    )
    if joint_pair is None:
        raise RuntimeError("Occupied fixture has no later same-day joint window")
    expected_first, expected_second = joint_pair

    anchor = seq._local_time(first)
    first_message = (
        f"احجزلي {seq._service_phrase(first)} وبعدها {seq._service_phrase(second)} "
        f"يوم {first['day'].isoformat()} من الساعة {anchor}. عايزهم ورا بعض ونفذ الحجزين"
    )
    first_response, first_duration = base._send(
        db,
        workspace,
        patient,
        first_message,
        None,
    )
    after_offer = seq._appointments(db, patient.id)

    confirmation = "تمام احجز الاتنين في المواعيد دي"
    second_response, second_duration = base._send(
        db,
        workspace,
        patient,
        confirmation,
        first_response.conversation_id,
    )
    after_confirmation = seq._appointments(db, patient.id)

    result = base.Result(name="second_compound_slot_occupied_offer_and_confirm_joint_window")
    result.turns = [
        base.Turn(first_message, first_response.reply, first_response.model, first_duration),
        base.Turn(confirmation, second_response.reply, second_response.model, second_duration),
    ]
    result.db_checks = [
        f"appointment_count_after_offer={len(after_offer)}",
        f"appointment_count_after_confirmation={len(after_confirmation)}",
        f"service_ids_after_confirmation={[str(row.service_id) for row in after_confirmation]}",
        f"starts_after_confirmation={[row.start_at.isoformat() for row in after_confirmation]}",
        f"ends_after_confirmation={[row.end_at.isoformat() for row in after_confirmation]}",
        f"blocker_appointment_id={blocker.id}",
        f"blocked_naive_second_start={second['start_at'].isoformat()}",
        f"expected_joint_first_start={expected_first.start_at.isoformat()}",
        f"expected_joint_second_start={expected_second.start_at.isoformat()}",
        f"first_resource_doctor={first['doctor_id']}",
        f"second_resource_doctor={second['doctor_id']}",
        f"first_device={first_device}",
        f"second_device={second_device}",
        "expected_target_appointment_count_after_offer=0",
        "expected_target_appointment_count_after_confirmation=2",
    ]
    return result


def main() -> int:
    args = _args()
    if not settings.agent_v2_live_enabled:
        raise RuntimeError("Occupied compound review requires AGENT_V2_LIVE_ENABLED=true")
    engine = create_engine(settings.database_url, pool_pre_ping=True)
    connection = engine.connect()
    outer = connection.begin()
    db = Session(bind=connection, expire_on_commit=False, join_transaction_mode="create_savepoint")
    try:
        workspace = db.scalar(select(Workspace).where(Workspace.slug == args.workspace_slug))
        if workspace is None:
            raise RuntimeError("Workspace not found")
        result = _run_case(db, workspace)
        print(json.dumps(asdict(result), ensure_ascii=False, separators=(",", ":")), flush=True)
        report = Path(args.report)
        report.parent.mkdir(parents=True, exist_ok=True)
        report.write_text(json.dumps(asdict(result), ensure_ascii=False, indent=2), encoding="utf-8")
        return 0
    finally:
        db.close()
        if outer.is_active:
            outer.rollback()
        connection.close()
        engine.dispose()


if __name__ == "__main__":
    raise SystemExit(main())
