from __future__ import annotations

# Eval-only source change to force Railway to apply the no-cache focused command.
import json

from app.core.config import settings
from sqlalchemy import create_engine

from tools.agent_eval.harness import jsonable
from tools.agent_eval.run_batch_03 import (
    case_01_handoff_during_active_booking,
    case_04_lifecycle_while_human_owns,
    case_05_two_appointments_explicit_date,
    case_06_two_same_service_explicit_date,
    case_07_real_appointment_ambiguity,
    case_08_candidate_selection_followup,
    case_09_cancel_one_of_multiple,
    case_15_package_booking_then_reschedule,
    run_case,
)

CASES = [
    case_01_handoff_during_active_booking,
    case_04_lifecycle_while_human_owns,
    case_05_two_appointments_explicit_date,
    case_06_two_same_service_explicit_date,
    case_07_real_appointment_ambiguity,
    case_08_candidate_selection_followup,
    case_09_cancel_one_of_multiple,
    case_15_package_booking_then_reschedule,
]


def main() -> int:
    engine = create_engine(settings.database_url, pool_pre_ping=True)
    rows = [run_case(engine, "tia", case_fn) for case_fn in CASES]
    had_infra_error = False
    for result in rows:
        row = jsonable(result)
        had_infra_error = had_infra_error or bool(row.get("execution_error"))
        compact = {
            "id": row["id"],
            "execution_error": row.get("execution_error"),
            "issues": row.get("issues") or [],
            "turns": [
                {
                    "turn_number": turn.get("turn_number"),
                    "user_message": turn.get("user_message"),
                    "agent_response": turn.get("agent_response"),
                    "verified_reads": turn.get("verified_reads") or [],
                    "actions": turn.get("actions") or [],
                    "write_attempted": turn.get("write_attempted"),
                    "write_result": turn.get("write_result"),
                    "handoff_state": turn.get("handoff_state"),
                    "runtime_state": turn.get("runtime_state") or {},
                    "operations": [
                        op
                        for trace in (turn.get("structured_trace") or [])
                        for op in ((trace.get("understanding") or {}).get("operations") or [])
                    ],
                    "plan_reads": [
                        read
                        for trace in (turn.get("structured_trace") or [])
                        for step in ((trace.get("plan") or {}).get("steps") or [])
                        for read in (step.get("reads") or [])
                    ],
                }
                for turn in (row.get("turns") or [])
            ],
            "db_verification": row.get("db_verification") or {},
            "evaluation": row.get("evaluation") or {},
        }
        print("FOCUSED_SCENARIO=" + json.dumps(compact, ensure_ascii=False, default=str), flush=True)
    return 2 if had_infra_error else 0


if __name__ == "__main__":
    raise SystemExit(main())
