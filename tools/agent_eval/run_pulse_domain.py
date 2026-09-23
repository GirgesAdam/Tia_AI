from __future__ import annotations

import argparse
import json
import os
from dataclasses import asdict
from datetime import UTC, datetime
from pathlib import Path

from app.models.patient import Patient
from app.models.payment_transaction import PaymentTransaction
from app.models.pulse_billing import PatientPulsePack, PulsePackOffer
from app.models.workspace import Workspace
from app.services.pulse_billing import (
    list_patient_pulse_balances,
    list_pulse_billing_settings,
)
from sqlalchemy import func, select
from sqlalchemy.orm import Session
from sqlalchemy import create_engine

from tools.agent_eval.harness import (
    ScenarioResult,
    aggregate_tokens,
    assert_demo_only,
    batch_token_summary,
    classify_issue,
    default_evaluation,
    jsonable,
    send_turn,
)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--workspace-slug", default="tia")
    parser.add_argument("--output-dir", default="backend/eval_results")
    parser.add_argument("--git-sha", default=os.getenv("GITHUB_SHA") or "unknown")
    return parser.parse_args()


def require_explicit_demo_eval() -> None:
    if os.getenv("TIA_AGENT_EVAL_CONFIRM_DEMO") != "1":
        raise RuntimeError("Set TIA_AGENT_EVAL_CONFIRM_DEMO=1 to run the live Demo evaluation.")


def _patient_with_pulse_balance(db: Session, workspace: Workspace) -> Patient:
    candidate_ids = list(
        db.scalars(
            select(PatientPulsePack.patient_id)
            .where(
                PatientPulsePack.workspace_id == workspace.id,
                PatientPulsePack.status == "active",
            )
            .distinct()
            .limit(100)
        )
    )
    for patient_id in candidate_ids:
        patient = db.scalar(
            select(Patient).where(
                Patient.workspace_id == workspace.id,
                Patient.id == patient_id,
                Patient.status != "blocked",
            )
        )
        if patient is None:
            continue
        balances = list_patient_pulse_balances(
            db,
            workspace_id=workspace.id,
            patient_id=patient.id,
        )
        if any(row.pulses_remaining > 0 for row in balances):
            return patient
    raise RuntimeError("EVAL_INFRA_ERROR: demo has no patient with active Pulse balance")


def _active_offer(db: Session, workspace: Workspace) -> PulsePackOffer:
    row = db.scalar(
        select(PulsePackOffer)
        .where(
            PulsePackOffer.workspace_id == workspace.id,
            PulsePackOffer.is_active.is_(True),
        )
        .order_by(PulsePackOffer.device_key, PulsePackOffer.pulses_count)
        .limit(1)
    )
    if row is None:
        raise RuntimeError("EVAL_INFRA_ERROR: demo has no active Pulse-pack offer")
    return row


def _active_patient(db: Session, workspace: Workspace) -> Patient:
    row = db.scalar(
        select(Patient)
        .where(
            Patient.workspace_id == workspace.id,
            Patient.status != "blocked",
        )
        .order_by(Patient.created_at)
        .limit(1)
    )
    if row is None:
        raise RuntimeError("EVAL_INFRA_ERROR: demo has no active patient")
    return row


def _result(
    *,
    scenario_id: str,
    purpose: str,
    turns,
    verification: dict,
    ok: bool,
    issue_title: str,
    issue_detail: str,
    action: bool = False,
) -> ScenarioResult:
    return ScenarioResult(
        id=scenario_id,
        category="pulses",
        purpose=purpose,
        turns=turns,
        state_before={},
        state_after={},
        db_verification=verification,
        evaluation=default_evaluation(
            db_ok=ok,
            action_ok=ok if action else None,
            grounding_ok=ok,
        ),
        issues=classify_issue(
            ok,
            severity="P1",
            title=issue_title,
            detail=issue_detail,
        ),
        token_usage=aggregate_tokens(turns),
    )


def case_balance(db: Session, workspace: Workspace) -> ScenarioResult:
    patient = _patient_with_pulse_balance(db, workspace)
    balances = list_patient_pulse_balances(
        db,
        workspace_id=workspace.id,
        patient_id=patient.id,
    )
    _, turn = send_turn(
        db,
        workspace,
        patient,
        "pulse_balance",
        1,
        "معايا كام pulse متبقية؟",
        None,
    )
    reply = (turn.agent_response or "").replace(",", "")
    expected = [row.pulses_remaining for row in balances]
    grounded = (
        "pulse_balance" in turn.verified_reads
        and not turn.write_attempted
        and any(str(value) in reply for value in expected)
    )
    return _result(
        scenario_id="pulse_balance",
        purpose="Read canonical patient Pulse balance without a write.",
        turns=[turn],
        verification={
            "balances": [row.model_dump(mode="json") for row in balances],
            "verified_read": "pulse_balance" in turn.verified_reads,
            "write_attempted": turn.write_attempted,
        },
        ok=grounded,
        issue_title="Pulse balance answer was not canonically grounded",
        issue_detail=f"Expected one of remaining balances {expected} from pulse_balance read.",
    )


def case_offer_price(db: Session, workspace: Workspace) -> ScenarioResult:
    patient = _active_patient(db, workspace)
    offer = _active_offer(db, workspace)
    _, turn = send_turn(
        db,
        workspace,
        patient,
        "pulse_offer_price",
        1,
        f"باقة {offer.pulses_count} pulse على {offer.device_name} بكام؟",
        None,
    )
    expected_price = f"{offer.price_minor / 100:g}"
    reply = (turn.agent_response or "").replace(",", "")
    ok = (
        "pulse_pack_offers" in turn.verified_reads
        and not turn.write_attempted
        and expected_price in reply
    )
    return _result(
        scenario_id="pulse_offer_price",
        purpose="Read the exact active Pulse-pack offer price.",
        turns=[turn],
        verification={
            "offer_id": str(offer.id),
            "device": offer.device_name,
            "pulses_count": offer.pulses_count,
            "price_minor": offer.price_minor,
            "verified_read": "pulse_pack_offers" in turn.verified_reads,
        },
        ok=ok,
        issue_title="Pulse-pack price was not grounded from the offer read",
        issue_detail=f"Expected verified offer price {expected_price} EGP.",
    )


def case_overage_price(db: Session, workspace: Workspace) -> ScenarioResult:
    patient = _active_patient(db, workspace)
    settings = [
        row
        for row in list_pulse_billing_settings(db, workspace_id=workspace.id)
        if row.overage_price_minor is not None
    ]
    if not settings:
        raise RuntimeError("EVAL_INFRA_ERROR: no configured Pulse overage price")
    row = settings[0]
    _, turn = send_turn(
        db,
        workspace,
        patient,
        "pulse_overage_price",
        1,
        f"الـ pulse الزيادة على {row.device_name} سعرها كام؟",
        None,
    )
    expected_price = f"{int(row.overage_price_minor or 0) / 100:g}"
    reply = (turn.agent_response or "").replace(",", "")
    ok = (
        "pulse_billing_settings" in turn.verified_reads
        and not turn.write_attempted
        and expected_price in reply
    )
    return _result(
        scenario_id="pulse_overage_price",
        purpose="Read device-specific Pulse overage price from canonical settings.",
        turns=[turn],
        verification={
            "device": row.device_name,
            "overage_price_minor": row.overage_price_minor,
            "verified_read": "pulse_billing_settings" in turn.verified_reads,
        },
        ok=ok,
        issue_title="Pulse overage price was not grounded",
        issue_detail=f"Expected verified overage price {expected_price} EGP.",
    )


def case_purchase_without_payment(db: Session, workspace: Workspace) -> ScenarioResult:
    patient = _active_patient(db, workspace)
    offer = _active_offer(db, workspace)
    before_packs = int(
        db.scalar(
            select(func.count(PatientPulsePack.id)).where(
                PatientPulsePack.workspace_id == workspace.id,
                PatientPulsePack.patient_id == patient.id,
            )
        )
        or 0
    )
    before_payments = int(
        db.scalar(
            select(func.count(PaymentTransaction.id)).where(
                PaymentTransaction.workspace_id == workspace.id,
                PaymentTransaction.patient_id == patient.id,
            )
        )
        or 0
    )
    _, turn = send_turn(
        db,
        workspace,
        patient,
        "pulse_pack_purchase",
        1,
        f"اشتريلي باقة {offer.pulses_count} pulse على {offer.device_name}",
        None,
    )
    after_packs = int(
        db.scalar(
            select(func.count(PatientPulsePack.id)).where(
                PatientPulsePack.workspace_id == workspace.id,
                PatientPulsePack.patient_id == patient.id,
            )
        )
        or 0
    )
    after_payments = int(
        db.scalar(
            select(func.count(PaymentTransaction.id)).where(
                PaymentTransaction.workspace_id == workspace.id,
                PaymentTransaction.patient_id == patient.id,
            )
        )
        or 0
    )
    created = list(
        db.scalars(
            select(PatientPulsePack)
            .where(
                PatientPulsePack.workspace_id == workspace.id,
                PatientPulsePack.patient_id == patient.id,
            )
            .order_by(PatientPulsePack.created_at.desc())
            .limit(1)
        )
    )
    latest = created[0] if created else None
    ok = (
        "pulse_pack_offers" in turn.verified_reads
        and turn.write_attempted
        and after_packs == before_packs + 1
        and after_payments == before_payments
        and latest is not None
        and latest.pulse_pack_offer_id == offer.id
        and latest.purchase_transaction_id is None
    )
    return _result(
        scenario_id="pulse_pack_purchase",
        purpose="Create the verified Pulse pack while recording no fictional payment.",
        turns=[turn],
        verification={
            "offer_id": str(offer.id),
            "before_pack_count": before_packs,
            "after_pack_count": after_packs,
            "before_payment_count": before_payments,
            "after_payment_count": after_payments,
            "purchase_transaction_id": (
                str(latest.purchase_transaction_id)
                if latest is not None and latest.purchase_transaction_id
                else None
            ),
            "verified_read": "pulse_pack_offers" in turn.verified_reads,
            "write_attempted": turn.write_attempted,
        },
        ok=ok,
        issue_title="Pulse-pack purchase violated verified-write/payment semantics",
        issue_detail=(
            "Expected exactly one new verified Pulse pack and no PaymentTransaction "
            "because the AI action records amount_paid=0."
        ),
        action=True,
    )


CASES = [
    case_balance,
    case_offer_price,
    case_overage_price,
    case_purchase_without_payment,
]


def run_case(engine, workspace_slug: str, case_fn) -> ScenarioResult:
    connection = engine.connect()
    outer = connection.begin()
    db = Session(
        bind=connection,
        expire_on_commit=False,
        join_transaction_mode="create_savepoint",
    )
    try:
        workspace = db.scalar(
            select(Workspace).where(Workspace.slug == workspace_slug)
        )
        if workspace is None:
            raise RuntimeError("Workspace not found")
        assert_demo_only(workspace)
        return case_fn(db, workspace)
    except Exception as exc:  # noqa: BLE001
        return ScenarioResult(
            id=case_fn.__name__.removeprefix("case_"),
            category="pulses",
            purpose="Execution failed before deterministic evaluation completed.",
            turns=[],
            state_before={},
            state_after={},
            db_verification={},
            evaluation=default_evaluation(db_ok=False, grounding_ok=False),
            issues=[
                {
                    "severity": "P1",
                    "title": "Pulse eval scenario execution error",
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


def main() -> None:
    args = parse_args()
    require_explicit_demo_eval()
    from app.core.config import settings

    engine = create_engine(settings.database_url, pool_pre_ping=True)
    results = [run_case(engine, args.workspace_slug, case) for case in CASES]
    summary = {
        "scenarios_run": len(results),
        "fully_correct": sum(not row.issues and row.execution_error is None for row in results),
        "failed": sum(bool(row.issues) or row.execution_error is not None for row in results),
        "tokens": batch_token_summary(results),
        "latency_ms": {
            row.id: [turn.latency_ms for turn in row.turns]
            for row in results
        },
    }
    payload = {
        "run_metadata": {
            "git_sha": args.git_sha,
            "workspace": args.workspace_slug,
            "generated_at": datetime.now(UTC).isoformat(),
            "suite": "pulse_domain",
        },
        "scenario_results": [jsonable(asdict(row)) for row in results],
        "batch_summary": summary,
    }
    output_dir = Path(args.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    path = output_dir / "pulse_domain_eval.json"
    path.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    print(json.dumps(summary, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
