from __future__ import annotations

import base64
import json
import os
from datetime import UTC, datetime

from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session

from app.core.config import settings
from app.models.workspace import Workspace
from app.services.demo_reset import acquire_demo_request_lock
from tools.agent_eval.harness import (
    ScenarioResult,
    aggregate_tokens,
    assert_demo_only,
    jsonable,
)
from tools.agent_eval.run_batch_01 import (
    case_device_price,
    case_full_booking,
    case_price,
    summarize,
)

CASES = [case_price, case_device_price, case_full_booking]


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
    results = [_run_case(engine, "tia", case_fn) for case_fn in CASES]
    summary = summarize(results)
    summary["eval_infra_errors"] = sum(
        row.execution_error is not None for row in results
    )
    payload = {
        "run_metadata": {
            "kind": "token_attribution_baseline",
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
