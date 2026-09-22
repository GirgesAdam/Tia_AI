from __future__ import annotations

import base64
import json
import os
from datetime import UTC, datetime

from app.core.config import settings
from app.models.workspace import Workspace
from app.services.demo_reset import acquire_demo_request_lock
from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session

from tools.agent_eval.harness import (
    ScenarioResult,
    aggregate_tokens,
    assert_demo_only,
    batch_token_summary,
    classify_issue,
    default_evaluation,
    jsonable,
    local_slot,
    state_snapshot,
)
from tools.agent_eval.run_batch_01 import (
    branch_name,
    case_device_price,
    case_full_booking,
    case_price,
    context_with_two_doctors,
    created_appointments,
    doctor_name,
    quiet_patient,
    run_messages,
)

ATTRIBUTION_VERSION = 1
SCHEMA_HEAD = "0078_repair_schedule_billing_categories"
CASES = [case_price, case_device_price, case_full_booking]


def case_full_booking_dynamic(db: Session, workspace: Workspace):
    patient = quiet_patient(db, workspace)
    catalog, service, branch_id, first, _ = context_with_two_doctors(db, workspace)
    doctor, _, available = first
    date_text, time_text = local_slot(available, available.slots[0])
    before = state_snapshot(db, workspace, patient)
    turns = run_messages(
        db,
        workspace,
        patient,
        "full_booking",
        [
            f"عايزه احجز {service['name']}",
            f"في {branch_name(catalog, branch_id)}",
            f"مع دكتورة {doctor_name(doctor)}",
            f"يوم {date_text} الساعة {time_text}",
            "تمام احجزي",
        ],
    )
    after = state_snapshot(db, workspace, patient)
    created = created_appointments(before, after)
    ok = (
        len(created) == 1
        and created[0]["service_id"] == str(service["id"])
        and created[0]["doctor_id"] == str(doctor["id"])
        and created[0]["branch_id"] == branch_id
    )
    return (
        "full_booking",
        "booking",
        "Complete a canonical bookable service→branch→doctor→slot→booking flow.",
        turns,
        before,
        after,
        {
            "fixture_service": str(service["name"]),
            "fixture_doctor": doctor_name(doctor),
            "fixture_branch": branch_name(catalog, branch_id),
            "created_appointments": created,
            "exactly_one_correct_booking": ok,
        },
        default_evaluation(action_ok=ok, db_ok=ok),
        classify_issue(
            ok,
            severity="P1",
            title="Full booking final state incorrect",
            detail=f"Expected exactly one grounded appointment, got {len(created)}.",
        ),
    )


def selected_cases() -> list:
    requested = os.getenv("TIA_TOKEN_BASELINE_SCENARIOS", "all").strip().lower()
    if requested in {"", "all"}:
        return CASES
    if requested == "full_booking":
        return [case_full_booking_dynamic]
    raise RuntimeError(f"Unsupported token baseline scenario selection: {requested!r}")


def _run_case(engine, slug: str, case_fn) -> ScenarioResult:
    connection = engine.connect()
    outer = connection.begin()
    db = Session(
        bind=connection,
        expire_on_commit=False,
        join_transaction_mode="create_savepoint",
    )
    try:
        workspace = db.scalar(select(Workspace).where(Workspace.slug == slug))
        if workspace is None:
            raise RuntimeError("EVAL_INFRA_ERROR: workspace missing")
        assert_demo_only(workspace)
        acquire_demo_request_lock(db, workspace)
        (
            scenario_id,
            category,
            purpose,
            turns,
            before,
            after,
            verification,
            evaluation,
            issues,
        ) = case_fn(db, workspace)
        return ScenarioResult(
            id=scenario_id,
            category=category,
            purpose=purpose,
            turns=turns,
            state_before=before,
            state_after=after,
            db_verification=verification,
            evaluation=evaluation,
            issues=issues,
            token_usage=aggregate_tokens(turns),
        )
    except Exception as exc:  # noqa: BLE001
        return ScenarioResult(
            id=case_fn.__name__.removeprefix("case_"),
            category="eval_infra",
            purpose="Token attribution baseline infrastructure failure.",
            turns=[],
            state_before={},
            state_after={},
            db_verification={},
            evaluation={"status": "EVAL_INFRA_ERROR"},
            issues=[
                {
                    "severity": "EVAL_INFRA_ERROR",
                    "title": "Evaluation infrastructure error",
                    "detail": f"{type(exc).__name__}: {exc}",
                }
            ],
            token_usage={
                "input_tokens": 0,
                "output_tokens": 0,
                "cached_tokens": 0,
                "total_tokens": 0,
                "calls": 0,
                "metadata_missing_calls": 0,
            },
            execution_error=f"{type(exc).__name__}: {exc}",
        )
    finally:
        db.close()
        if outer.is_active:
            outer.rollback()
        connection.close()


def summarize_attribution(results: list[ScenarioResult]) -> dict:
    pcounts = {f"P{i}": 0 for i in range(4)}
    for row in results:
        for issue in row.issues:
            severity = str(issue.get("severity") or "")
            if severity in pcounts:
                pcounts[severity] += 1
    return {
        "scenarios_run": len(results),
        **pcounts,
        "eval_infra_errors": sum(
            row.execution_error is not None for row in results
        ),
        "tokens": batch_token_summary(results),
    }


def _emit(payload: dict) -> None:
    encoded = base64.b64encode(
        json.dumps(payload, ensure_ascii=False, default=str).encode("utf-8")
    ).decode("ascii")
    print("TOKEN_ATTRIBUTION_B64_BEGIN", flush=True)
    for offset in range(0, len(encoded), 3000):
        print(
            "TOKEN_ATTRIBUTION_B64=" + encoded[offset : offset + 3000],
            flush=True,
        )
    print("TOKEN_ATTRIBUTION_B64_END", flush=True)
    print(
        "TOKEN_ATTRIBUTION_SUMMARY="
        + json.dumps(payload["summary"], ensure_ascii=False),
        flush=True,
    )


def main() -> int:
    if os.getenv("TIA_AGENT_EVAL_CONFIRM_DEMO") != "1":
        raise RuntimeError("Set TIA_AGENT_EVAL_CONFIRM_DEMO=1")

    engine = create_engine(settings.database_url, pool_pre_ping=True)
    cases = selected_cases()
    results = [_run_case(engine, "tia", case_fn) for case_fn in cases]
    summary = summarize_attribution(results)
    payload = {
        "run_metadata": {
            "kind": "token_attribution_baseline",
            "attribution_version": ATTRIBUTION_VERSION,
            "schema_head": SCHEMA_HEAD,
            "git_sha": os.getenv("TIA_AGENT_EVAL_GIT_SHA", "unknown"),
            "generated_at": datetime.now(UTC).isoformat(),
            "model_config": settings.openai_model,
        },
        "scenario_results": [jsonable(row) for row in results],
        "summary": summary,
    }
    _emit(payload)
    engine.dispose()
    if summary["eval_infra_errors"]:
        return 3
    if summary["P0"] or summary["P1"]:
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
