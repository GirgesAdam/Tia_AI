from __future__ import annotations

import base64
import json
import os
import statistics
from datetime import UTC, datetime, timedelta
from pathlib import Path
from uuid import UUID

from sqlalchemy import create_engine, select, text
from sqlalchemy.orm import Session

from app.core.config import settings
from app.integrations.clinic.base import AvailabilityRequest, ClinicCapability
from app.integrations.clinic.registry import get_clinic_adapter
from app.models.workspace import Workspace
from app.services.demo_reset import acquire_demo_request_lock
from tools.agent_eval import harness
from tools.agent_eval import run_batch_01 as batch

AFFECTED = [
    batch.case_ambiguous_laser,
    batch.case_full_booking,
    batch.case_unavailable,
    batch.case_reschedule,
    batch.case_cancel,
    batch.case_package_other_service,
    batch.case_multi_question,
]
GENERIC_SLUGS = {"hydrafacial"}
_fixture_context: dict = {}


def _bookable_context(db: Session, workspace: Workspace, *, service_slug: str | None = None, exclude_service_id: str | None = None):
    catalog = harness.build_clinic_catalog(db, workspace)
    branches = [r for r in catalog.get("branches", []) if isinstance(r, dict) and r.get("id")]
    if len(branches) != 1:
        raise RuntimeError(f"EVAL_INFRA_ERROR: active branches={len(branches)} expected=1")
    branch = branches[0]
    branch_id = str(branch["id"])
    services = [r for r in catalog.get("services", []) if isinstance(r, dict) and r.get("id")]
    doctors = [r for r in catalog.get("doctors", []) if isinstance(r, dict) and r.get("id")]
    exact_required = bool(service_slug and service_slug not in GENERIC_SLUGS)
    if service_slug and exact_required:
        services = [r for r in services if r.get("slug") == service_slug]
        if not services:
            raise RuntimeError(f"EVAL_INFRA_ERROR: required active service missing slug={service_slug!r}")
    elif service_slug in GENERIC_SLUGS:
        preferred = [r for r in services if r.get("slug") == service_slug and not r.get("requires_laser_device")]
        fallback = [r for r in services if not r.get("requires_laser_device") and r not in preferred]
        services = preferred + fallback

    adapter = get_clinic_adapter(db=db, workspace=workspace)
    adapter.require_capability(ClinicCapability.AVAILABILITY_READ)
    today = datetime.now(UTC).date()
    for service in services:
        service_id = str(service["id"])
        if exclude_service_id and service_id == str(exclude_service_id):
            continue
        for doctor in doctors:
            if service_id not in {str(v) for v in (doctor.get("service_ids") or [])}:
                continue
            scheduled = {str(v) for v in (doctor.get("scheduled_branch_ids") or doctor.get("branch_ids") or []) if v}
            if scheduled and branch_id not in scheduled:
                continue
            for offset in range(1, 91):
                day = today + timedelta(days=offset)
                available = adapter.get_availability(AvailabilityRequest(
                    branch_id=branch_id,
                    service_id=service_id,
                    booking_date=day,
                    doctor_id=str(doctor["id"]),
                ))
                if available.slots:
                    db_service = db.get(harness.Service, UUID(service_id))\n                    if db_service is None or not db_service.is_active:\n                        raise RuntimeError("EVAL_INFRA_ERROR: catalog service missing from active DB services")
                    device_prices = db.execute(text("""
                        SELECT device_key, device_name, price_minor
                        FROM service_device_prices
                        WHERE workspace_id=:wid AND service_id=:sid AND price_minor > 0
                        ORDER BY device_key
                    """), {"wid": workspace.id, "sid": UUID(service_id)}).mappings().all()
                    _fixture_context.clear()
                    _fixture_context.update({
                        "workspace_id": str(workspace.id),
                        "branch_id": branch_id,
                        "branch_name": str(branch.get("name") or ""),
                        "service_id": service_id,
                        "service_name": str(service.get("name") or ""),
                        "service_slug": str(db_service.slug or ""),
                        "service_price_minor": int(db_service.price_minor or 0),
                        "requires_laser_device": bool(service.get("requires_laser_device")),
                        "doctor_id": str(doctor["id"]),
                        "doctor_name": batch.doctor_name(doctor),
                        "doctor_service_relationship_verified": True,
                        "doctor_branch_relationship_verified": True,
                        "working_hours_verified": True,
                        "selected_availability_date": day.isoformat(),
                        "selected_exact_slot": available.slots[0].start_at.isoformat(),
                        "laser_device_prices": [dict(r) for r in device_prices],
                        "fixture_valid": True,
                    })
                    return catalog, service, doctor, branch_id, day, available
    label = service_slug if service_slug else "<dynamic>"
    raise RuntimeError(f"EVAL_INFRA_ERROR: no valid bookable fixture for {label}")


def _token_summary(rows: list[harness.ScenarioResult]) -> dict:
    executed = [r for r in rows if int(r.token_usage.get("calls", 0)) > 0]
    totals = [int(r.token_usage.get("total_tokens", 0)) for r in executed]
    turns = sum(len(r.turns) for r in executed)
    calls = sum(int(r.token_usage.get("calls", 0)) for r in executed)
    return {
        "executed_llm_scenarios": len(executed),
        "input_tokens": sum(int(r.token_usage.get("input_tokens", 0)) for r in executed),
        "output_tokens": sum(int(r.token_usage.get("output_tokens", 0)) for r in executed),
        "cached_tokens": sum(int(r.token_usage.get("cached_tokens", 0)) for r in executed),
        "total_tokens": sum(totals),
        "average_per_executed_scenario": round(statistics.mean(totals), 2) if totals else 0,
        "median_per_executed_scenario": statistics.median(totals) if totals else 0,
        "max_tokens": max(totals) if totals else 0,
        "max_scenario": max(executed, key=lambda r: r.token_usage.get("total_tokens", 0)).id if executed else None,
        "tokens_per_turn": round(sum(totals) / turns, 2) if turns else 0,
        "llm_calls": calls,
        "llm_calls_per_scenario": round(calls / len(executed), 2) if executed else 0,
    }


def run_case(engine, slug: str, case_fn):
    connection = engine.connect()
    outer = connection.begin()
    db = Session(bind=connection, expire_on_commit=False, join_transaction_mode="create_savepoint")
    original = batch.booking_context
    try:
        workspace = db.scalar(select(Workspace).where(Workspace.slug == slug))
        if workspace is None:
            raise RuntimeError("EVAL_INFRA_ERROR: workspace missing")
        harness.assert_demo_only(workspace)
        acquire_demo_request_lock(db, workspace)
        batch.booking_context = _bookable_context
        _fixture_context.clear()
        case = case_fn(db, workspace)
        scenario_id, category, purpose, turns, before, after, verification, evaluation, issues = case
        evidence = dict(_fixture_context)
        if turns:
            patient_id = db.scalar(text("SELECT patient_id FROM conversations WHERE id=:cid"), {"cid": UUID(turns[0].runtime_state["conversation_id"])})
            evidence["patient_id"] = str(patient_id) if patient_id else None
        if scenario_id == "package_holder_other_service":
            pkgs = before.get("packages") or []
            evidence["package_id"] = pkgs[0]["id"] if pkgs else None
            evidence["package_service_id"] = pkgs[0]["service_id"] if pkgs else None
        evidence["fixture_valid"] = bool(evidence.get("fixture_valid"))
        verification = {**verification, "fixture_evidence": evidence}
        return harness.ScenarioResult(
            id=scenario_id, category=category, purpose=purpose, turns=turns,
            state_before=before, state_after=after, db_verification=verification,
            evaluation=evaluation, issues=issues, token_usage=harness.aggregate_tokens(turns),
        )
    except Exception as exc:
        return harness.ScenarioResult(
            id=case_fn.__name__.removeprefix("case_"),
            category="eval_infra",
            purpose="Fixture/evaluation infrastructure failure before valid Agent execution.",
            turns=[], state_before={}, state_after={},
            db_verification={"fixture_evidence": dict(_fixture_context), "fixture_valid": False},
            evaluation={"status": "EVAL_INFRA_ERROR"},
            issues=[{"severity": "EVAL_INFRA_ERROR", "title": "Evaluation infrastructure error", "detail": f"{type(exc).__name__}: {exc}"}],
            token_usage={"input_tokens":0,"output_tokens":0,"cached_tokens":0,"total_tokens":0,"calls":0,"metadata_missing_calls":0},
            execution_error=f"{type(exc).__name__}: {exc}",
        )
    finally:
        batch.booking_context = original
        db.close()
        if outer.is_active:
            outer.rollback()
        connection.close()


def main() -> int:
    if os.getenv("TIA_AGENT_EVAL_CONFIRM_DEMO") != "1":
        raise RuntimeError("Set TIA_AGENT_EVAL_CONFIRM_DEMO=1")
    engine = create_engine(settings.database_url, pool_pre_ping=True)
    rows = [run_case(engine, "tia", fn) for fn in AFFECTED]
    infra = [r for r in rows if r.execution_error]
    payload = {
        "run_metadata": {"kind":"batch_01_invalid_scenarios_only","git_sha":os.getenv("TIA_AGENT_EVAL_GIT_SHA","unknown"),"generated_at":datetime.now(UTC).isoformat()},
        "scenario_results": [harness.jsonable(r) for r in rows],
        "summary": {
            "rerun_scenarios": len(rows),
            "eval_infra_errors": len(infra),
            "agent_p0": sum(1 for r in rows for i in r.issues if i.get("severity")=="P0"),
            "agent_p1": sum(1 for r in rows for i in r.issues if i.get("severity")=="P1"),
            "pass": sum(1 for r in rows if not r.issues and not r.execution_error),
            "tokens": _token_summary(rows),
        },
    }
    encoded=base64.b64encode(json.dumps(payload,ensure_ascii=False,default=str).encode()).decode()
    print("CLEAN_RERUN_B64_BEGIN",flush=True)
    for i in range(0,len(encoded),3000):
        print("CLEAN_RERUN_B64="+encoded[i:i+3000],flush=True)
    print("CLEAN_RERUN_B64_END",flush=True)
    print("CLEAN_RERUN_SUMMARY="+json.dumps(payload["summary"],ensure_ascii=False),flush=True)
    engine.dispose()
    return 0 if not infra else 3

if __name__ == "__main__":
    raise SystemExit(main())
