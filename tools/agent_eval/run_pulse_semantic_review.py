from __future__ import annotations

import argparse
import json
import os
from dataclasses import asdict
from datetime import UTC, datetime
from pathlib import Path
from zoneinfo import ZoneInfo

from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session

from app.models.workspace import Workspace
from app.services.pulse_billing import list_patient_pulse_balances
from tools.agent_eval.harness import assert_demo_only, jsonable, send_turn
from tools.agent_eval.run_pulse_domain import (
    _active_offer,
    _active_patient,
    _laser_booking_fixture,
    _patient_with_pulse_balance,
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


def _turn_payload(turn) -> dict[str, object]:
    return {
        "user_message": turn.user_message,
        "agent_response": turn.agent_response,
        "latency_ms": turn.latency_ms,
        "verified_reads": turn.verified_reads,
        "write_attempted": turn.write_attempted,
        "write_result": turn.write_result,
        "token_usage": turn.token_usage,
        "llm_calls": turn.llm_calls,
    }


def _price_paraphrases(db: Session, workspace: Workspace) -> list[dict[str, object]]:
    patient = _active_patient(db, workspace)
    offer = _active_offer(db, workspace)
    messages = [
        f"الألف نبضة بتوع {offer.device_name} عاملين كام؟",
        f"لو عايزة {offer.pulses_count} نبضة على {offer.device_name} هدفع كام؟",
        f"سعر عرض {offer.pulses_count} pulse بتاع {offer.device_name} إيه؟",
        f"{offer.pulses_count} نبضة على {offer.device_name} تكلفتهم قد إيه؟",
    ]
    rows: list[dict[str, object]] = []
    for index, message in enumerate(messages, start=1):
        _, turn = send_turn(
            db,
            workspace,
            patient,
            f"pulse_price_paraphrase_{index}",
            1,
            message,
            None,
        )
        rows.append(
            {
                "scenario_id": f"pulse_price_paraphrase_{index}",
                "expected_verified_offer": {
                    "device_name": offer.device_name,
                    "pulses_count": offer.pulses_count,
                    "price_minor": offer.price_minor,
                    "currency": offer.currency,
                },
                "turns": [_turn_payload(turn)],
            }
        )
    return rows


def _billing_paraphrases(db: Session, workspace: Workspace) -> list[dict[str, object]]:
    patient = _patient_with_pulse_balance(db, workspace)
    balances = [
        row
        for row in list_patient_pulse_balances(
            db,
            workspace_id=workspace.id,
            patient_id=patient.id,
        )
        if row.pulses_remaining > 0
    ]
    if not balances:
        raise RuntimeError("EVAL_INFRA_ERROR: no patient with remaining Pulse balance")
    balance = balances[0]
    offer = _active_offer(db, workspace)
    if offer.device_key != balance.device_key:
        matching = [
            candidate
            for candidate in [_active_offer(db, workspace)]
            if candidate.device_key == balance.device_key
        ]
        if matching:
            offer = matching[0]
    _catalog, service, doctor, available, slot = _laser_booking_fixture(
        db,
        workspace,
        offer=offer,
    )
    local = slot.start_at.astimezone(ZoneInfo(available.timezone))
    messages = [
        (
            f"احجزيلي {service['name']} مع {doctor['name']} "
            f"يوم {local.date().isoformat()} الساعة {local.strftime('%H:%M')} "
            "وخلي حساب الجلسة من رصيد النبضات اللي عندي."
        ),
        (
            f"ثبتيلي {service['name']} مع {doctor['name']} "
            f"يوم {local.date().isoformat()} الساعة {local.strftime('%H:%M')} "
            "وعايزها تتحاسب على الـpulse balance."
        ),
    ]
    rows: list[dict[str, object]] = []
    for index, message in enumerate(messages, start=1):
        _, turn = send_turn(
            db,
            workspace,
            patient,
            f"pulse_billing_wording_{index}",
            1,
            message,
            None,
        )
        rows.append(
            {
                "scenario_id": f"pulse_billing_wording_{index}",
                "expected_semantics": {
                    "billing_source": "pulse_balance",
                    "consumption_recorded_at_booking": False,
                },
                "turns": [_turn_payload(turn)],
            }
        )
    return rows


def _purchase_then_bill_paraphrases(
    db: Session,
    workspace: Workspace,
) -> list[dict[str, object]]:
    offer = _active_offer(db, workspace)
    patient = _active_patient(db, workspace)
    _catalog, service, doctor, available, slot = _laser_booking_fixture(
        db,
        workspace,
        offer=offer,
    )
    local = slot.start_at.astimezone(ZoneInfo(available.timezone))

    first_response, first_turn = send_turn(
        db,
        workspace,
        patient,
        "pulse_purchase_bill_paraphrase_1",
        1,
        f"هاتلي باقة {offer.pulses_count} نبضة على {offer.device_name}.",
        None,
    )
    _, second_turn = send_turn(
        db,
        workspace,
        patient,
        "pulse_purchase_bill_paraphrase_1",
        2,
        (
            f"واحجزيلي {service['name']} مع {doctor['name']} "
            f"يوم {local.date().isoformat()} الساعة {local.strftime('%H:%M')} "
            "وخلي حسابها على النبضات اللي لسه ضفتها."
        ),
        first_response.conversation_id,
    )

    _, compound_turn = send_turn(
        db,
        workspace,
        patient,
        "pulse_purchase_bill_paraphrase_2",
        1,
        (
            f"زوديلي {offer.pulses_count} pulse على {offer.device_name} "
            f"واحجزيلي {service['name']} مع {doctor['name']} "
            f"يوم {local.date().isoformat()} الساعة {local.strftime('%H:%M')} "
            "وخلي الجلسة تتحاسب من الرصيد الجديد."
        ),
        None,
    )

    return [
        {
            "scenario_id": "pulse_purchase_bill_paraphrase_1",
            "expected_semantics": {
                "purchase_and_booking_are_separate_actions": True,
                "billing_source": "pulse_balance",
                "consumption_recorded_at_booking": False,
            },
            "turns": [_turn_payload(first_turn), _turn_payload(second_turn)],
        },
        {
            "scenario_id": "pulse_purchase_bill_paraphrase_2",
            "expected_semantics": {
                "purchase_and_booking_are_separate_actions": True,
                "billing_source": "pulse_balance",
                "consumption_recorded_at_booking": False,
            },
            "turns": [_turn_payload(compound_turn)],
        },
    ]


def main() -> None:
    args = parse_args()
    require_explicit_demo_eval()
    from app.core.config import settings

    engine = create_engine(settings.database_url, pool_pre_ping=True)
    connection = engine.connect()
    outer = connection.begin()
    db = Session(
        bind=connection,
        expire_on_commit=False,
        join_transaction_mode="create_savepoint",
    )
    try:
        workspace = db.scalar(
            select(Workspace).where(Workspace.slug == args.workspace_slug)
        )
        if workspace is None:
            raise RuntimeError("Workspace not found")
        assert_demo_only(workspace)
        results = [
            *_price_paraphrases(db, workspace),
            *_billing_paraphrases(db, workspace),
            *_purchase_then_bill_paraphrases(db, workspace),
        ]
        payload = {
            "run_metadata": {
                "git_sha": args.git_sha,
                "workspace": args.workspace_slug,
                "generated_at": datetime.now(UTC).isoformat(),
                "suite": "pulse_semantic_review",
                "evaluation_mode": "qualitative_no_pass_fail",
            },
            "scenario_results": results,
        }
        output_dir = Path(args.output_dir)
        output_dir.mkdir(parents=True, exist_ok=True)
        path = output_dir / "pulse_semantic_review.json"
        path.write_text(
            json.dumps(jsonable(payload), ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        print(json.dumps(jsonable(payload), ensure_ascii=False, indent=2))
    finally:
        db.close()
        if outer.is_active:
            outer.rollback()
        connection.close()


if __name__ == "__main__":
    main()
