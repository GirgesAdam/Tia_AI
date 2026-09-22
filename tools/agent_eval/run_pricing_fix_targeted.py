from __future__ import annotations

import base64
import json
import os
from datetime import UTC, datetime

from app.core.config import settings
from app.models.service import Service
from app.models.workspace import Workspace
from app.services.demo_reset import acquire_demo_request_lock
from sqlalchemy import create_engine, select, text
from sqlalchemy.orm import Session

from tools.agent_eval.harness import (
    ScenarioResult,
    aggregate_tokens,
    assert_demo_only,
    default_evaluation,
    jsonable,
    money,
    state_snapshot,
)
from tools.agent_eval.run_batch_01 import (
    case_device_price,
    case_price,
    classify_issue,
    quiet_patient,
    run_messages,
    summarize,
)

PRIMARY_CASES = [case_price, case_device_price]


def _neighbor_normal_service(db: Session, workspace: Workspace):
    patient = quiet_patient(db, workspace)
    service = db.scalar(
        select(Service)
        .where(
            Service.workspace_id == workspace.id,
            Service.is_active.is_(True),
            Service.slug != "prp-skin",
            Service.price_minor > 0,
            Service.requires_laser_device.is_(False),
        )
        .order_by(Service.name)
        .limit(1)
    )
    if service is None:
        raise RuntimeError("EVAL_INFRA_ERROR: no alternate normal priced service")
    before = state_snapshot(db, workspace, patient)
    turns = run_messages(
        db,
        workspace,
        patient,
        "neighbor_normal_service_price",
        [f"{service.name} بكام؟"],
    )
    after = state_snapshot(db, workspace, patient)
    expected = money(int(service.price_minor))
    grounded = expected in (turns[-1].agent_response or "").replace(",", "")
    return (
        "neighbor_normal_service_price",
        "pricing",
        "Verify another non-device service price from canonical DB.",
        turns,
        before,
        after,
        {
            "service_name": service.name,
            "expected_price_egp": expected,
            "reply_contains_current_price": grounded,
        },
        default_evaluation(grounding_ok=grounded),
        classify_issue(
            grounded,
            severity="P1",
            title="Neighbor normal-service price incorrect",
            detail=f"Canonical price is {expected} EGP.",
        ),
    )


def _neighbor_prime_price(db: Session, workspace: Workspace):
    patient = quiet_patient(db, workspace)
    service = db.scalar(
        select(Service).where(
            Service.workspace_id == workspace.id,
            Service.slug == "laser-hair-removal-underarm",
            Service.is_active.is_(True),
        )
    )
    if service is None:
        raise RuntimeError("EVAL_INFRA_ERROR: underarm service missing")
    prime = db.execute(
        text(
            "SELECT device_name, price_minor FROM service_device_prices "
            "WHERE workspace_id=:workspace_id AND service_id=:service_id "
            "AND device_key='prime_lase' AND is_active IS TRUE"
        ),
        {"workspace_id": workspace.id, "service_id": service.id},
    ).mappings().first()
    if prime is None:
        raise RuntimeError("EVAL_INFRA_ERROR: Prime Lase price missing")
    before = state_snapshot(db, workspace, patient)
    turns = run_messages(
        db,
        workspace,
        patient,
        "neighbor_prime_lase_price",
        ["ليزر الإبط بكام؟", "على Prime Lase؟"],
    )
    after = state_snapshot(db, workspace, patient)
    expected = money(int(prime["price_minor"]))
    grounded = expected in (turns[-1].agent_response or "").replace(",", "")
    return (
        "neighbor_prime_lase_price",
        "pricing",
        "Verify Prime Lase price for the same laser service.",
        turns,
        before,
        after,
        {
            "device": str(prime["device_name"]),
            "expected_price_egp": expected,
            "reply_contains_current_price": grounded,
        },
        default_evaluation(grounding_ok=grounded, continuity_ok=grounded),
        classify_issue(
            grounded,
            severity="P1",
            title="Prime Lase price incorrect",
            detail=f"Canonical Prime Lase price is {expected} EGP.",
        ),
    )


def _neighbor_unspecified_device(db: Session, workspace: Workspace):
    patient = quiet_patient(db, workspace)
    service = db.scalar(
        select(Service).where(
            Service.workspace_id == workspace.id,
            Service.slug == "laser-hair-removal-underarm",
            Service.is_active.is_(True),
        )
    )
    if service is None:
        raise RuntimeError("EVAL_INFRA_ERROR: underarm service missing")
    devices = db.execute(
        text(
            "SELECT device_name, price_minor FROM service_device_prices "
            "WHERE workspace_id=:workspace_id AND service_id=:service_id "
            "AND is_active IS TRUE AND price_minor > 0 ORDER BY device_key"
        ),
        {"workspace_id": workspace.id, "service_id": service.id},
    ).mappings().all()
    if len(devices) < 2:
        raise RuntimeError("EVAL_INFRA_ERROR: multi-device underarm fixture missing")
    before = state_snapshot(db, workspace, patient)
    turns = run_messages(
        db,
        workspace,
        patient,
        "neighbor_unspecified_device_price",
        ["ليزر الإبط بكام؟"],
    )
    after = state_snapshot(db, workspace, patient)
    reply = (turns[-1].agent_response or "").replace(",", "")
    expected_prices = [money(int(row["price_minor"])) for row in devices]
    expected_names = [str(row["device_name"]) for row in devices]
    all_prices = all(value in reply for value in expected_prices)
    all_names = all(value.casefold() in reply.casefold() for value in expected_names)
    correct = all_prices and all_names
    return (
        "neighbor_unspecified_device_price",
        "pricing",
        "Do not silently select one device when multiple verified device prices exist.",
        turns,
        before,
        after,
        {
            "device_names": expected_names,
            "expected_prices_egp": expected_prices,
            "all_verified_options_present": correct,
        },
        default_evaluation(grounding_ok=correct),
        classify_issue(
            correct,
            severity="P1",
            title="Unspecified laser device was silently priced",
            detail="Expected all configured device names and canonical prices.",
        ),
    )


NEIGHBOR_CASES = [
    _neighbor_normal_service,
    _neighbor_prime_price,
    _neighbor_unspecified_device,
]


def _locked_run_case(engine, slug: str, case_fn) -> ScenarioResult:
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
            id=case_fn.__name__.removeprefix("case_").removeprefix("_neighbor_"),
            category="eval_infra",
            purpose="Targeted pricing evaluation infrastructure failure.",
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
    print("PRICING_TARGETED_B64_BEGIN", flush=True)
    for offset in range(0, len(encoded), 3000):
        print(
            "PRICING_TARGETED_B64=" + encoded[offset : offset + 3000],
            flush=True,
        )
    print("PRICING_TARGETED_B64_END", flush=True)
    print(
        "PRICING_TARGETED_SUMMARY="
        + json.dumps(payload["summary"], ensure_ascii=False),
        flush=True,
    )


def main() -> int:
    if os.getenv("TIA_AGENT_EVAL_CONFIRM_DEMO") != "1":
        raise RuntimeError("Set TIA_AGENT_EVAL_CONFIRM_DEMO=1")
    phase = os.getenv("TIA_AGENT_EVAL_PRICING_PHASE", "primary").strip().lower()
    cases = PRIMARY_CASES if phase == "primary" else NEIGHBOR_CASES if phase == "neighbors" else None
    if cases is None:
        raise RuntimeError(f"Unsupported pricing eval phase: {phase!r}")

    engine = create_engine(settings.database_url, pool_pre_ping=True)
    results = [_locked_run_case(engine, "tia", case_fn) for case_fn in cases]
    summary = summarize(results)
    summary["eval_infra_errors"] = sum(
        row.execution_error is not None for row in results
    )
    payload = {
        "run_metadata": {
            "kind": "pricing_fix_targeted",
            "phase": phase,
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
    return 0 if not summary["P0"] and not summary["P1"] else 2


if __name__ == "__main__":
    raise SystemExit(main())
