from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path
from uuid import UUID

from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session

import app.services.agent_chat as agent_chat_module
from app.core.config import settings
from app.models.workspace import Workspace
from app.services.conversation_flows import get_active_flow
from scripts.run_extended_booking_conversation_review import _setup_case
from scripts.run_daily_clinic_conversation_review import _send

# Final verification remains limited to the four booking conversations under review.
CASES = (
    "booking_exact_time_unavailable_then_flexible",
    "booking_change_service_mid_conversation",
    "reschedule_two_appointments_choose_one",
    "booking_time_constraints_keep_changing",
)


def _compact_flow(flow) -> dict | None:
    if flow is None:
        return None
    snapshot = flow.option_snapshot if isinstance(flow.option_snapshot, dict) else {}
    slots = snapshot.get("slots") if isinstance(snapshot.get("slots"), list) else []
    return {
        "flow_type": flow.flow_type,
        "status": flow.status,
        "capabilities": list(flow.capabilities or []),
        "entity_state": dict(flow.entity_state or {}),
        "last_decision": dict(flow.last_decision or {}),
        "option_date": snapshot.get("date"),
        "option_slots": [
            {
                "start_time_24h": slot.get("start_time_24h"),
                "doctor_name": slot.get("doctor_name"),
                "service_name": slot.get("service_name"),
                "service_id": slot.get("service_id"),
                "doctor_id": slot.get("doctor_id"),
            }
            for slot in slots[:20]
            if isinstance(slot, dict)
        ],
    }


def _run_case(engine, slug: str, name: str) -> dict:
    connection = engine.connect()
    outer = connection.begin()
    db = Session(bind=connection, expire_on_commit=False, join_transaction_mode="create_savepoint")
    result = {"name": name, "error": None, "turns": []}
    original = agent_chat_module.interpret_customer_turn
    decisions: list[dict] = []

    def traced(*, flow, history, timezone_name, local_now, clinic_catalog):
        decision = original(
            flow=flow,
            history=history,
            timezone_name=timezone_name,
            local_now=local_now,
            clinic_catalog=clinic_catalog,
        )
        decisions.append(decision.model_dump(mode="json"))
        return decision

    agent_chat_module.interpret_customer_turn = traced
    try:
        workspace = db.scalar(select(Workspace).where(Workspace.slug == slug))
        if workspace is None:
            raise RuntimeError("Workspace not found")
        patient, messages, _ = _setup_case(name, db, workspace)
        conversation_id: UUID | None = None
        for message in messages:
            before_count = len(decisions)
            response, duration_ms = _send(db, workspace, patient, message, conversation_id)
            conversation_id = response.conversation_id
            decision = decisions[-1] if len(decisions) > before_count else None
            flow = get_active_flow(
                db,
                workspace_id=workspace.id,
                conversation_id=conversation_id,
                patient_id=patient.id,
            )
            result["turns"].append(
                {
                    "customer": message,
                    "assistant": response.reply,
                    "duration_ms": duration_ms,
                    "decision": decision,
                    "flow_after": _compact_flow(flow),
                }
            )
    except Exception as exc:  # noqa: BLE001
        result["error"] = f"{type(exc).__name__}: {exc}"
    finally:
        agent_chat_module.interpret_customer_turn = original
        db.close()
        if outer.is_active:
            outer.rollback()
        connection.close()
    return result


def main() -> int:
    if str(settings.environment or "").strip().lower() == "production":
        raise SystemExit("Refusing to run booking diagnostic in production.")
    engine = create_engine(settings.database_url, pool_pre_ping=True)
    try:
        results = []
        for idx, name in enumerate(CASES, start=1):
            print(f"[{idx}/{len(CASES)}] {name}", flush=True)
            results.append(_run_case(engine, "tia", name))
    finally:
        engine.dispose()
    report = {
        "created_at": datetime.now(UTC).isoformat(),
        "cases": results,
        "database_writes_persisted": False,
    }
    path = Path("artifacts/booking-followup-diagnostic.json")
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"Report: {path}", flush=True)
    return 1 if any(case.get("error") for case in results) else 0


if __name__ == "__main__":
    raise SystemExit(main())
