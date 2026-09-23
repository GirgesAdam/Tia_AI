from __future__ import annotations

from contextlib import nullcontext
from datetime import UTC, datetime
from types import SimpleNamespace
from uuid import uuid4

from app.agents.v2.semantic_context import build_semantic_context
from app.agents.v2.turn_contract import (
    TiaTurnUnderstanding,
    TurnEntities,
    TurnOperation,
)
from app.services.agent_v2.planner import (
    PlanStep,
    PlannerContext,
    VerificationFacts,
    WriteIntent,
    advance_step_after_verification,
    plan_turn,
)
from app.services.agent_v2.read_executor import ReadExecutionContext, execute_step_reads
from app.services.agent_v2.write_executor import execute_write_ready_step


NOW = datetime(2026, 9, 23, 16, 0, tzinfo=UTC)


def _planner_context() -> PlannerContext:
    return PlannerContext(
        semantic_context=build_semantic_context(
            {"services": [], "doctors": [], "appointments": []}
        ),
        active_task=None,
        now=NOW,
    )


def test_pulse_balance_question_is_read_only() -> None:
    operation = TurnOperation(
        type="pulse_info",
        entities=TurnEntities(),
        requested_pulse_details=["balance"],
        execution_intent="informational",
    )
    step = plan_turn(
        TiaTurnUnderstanding(operations=[operation], safety_signals=[]),
        _planner_context(),
    ).steps[0]

    assert step.disposition == "read"
    assert step.write_intent is None
    assert [read.kind for read in step.reads] == ["pulse_balance"]
    assert step.response_goal == "pulse_information"


def test_pulse_info_reads_only_requested_facts() -> None:
    operation = TurnOperation(
        type="pulse_info",
        entities=TurnEntities(),
        requested_pulse_details=["offers", "overage_price"],
        execution_intent="informational",
    )
    step = plan_turn(
        TiaTurnUnderstanding(operations=[operation], safety_signals=[]),
        _planner_context(),
    ).steps[0]

    assert [read.kind for read in step.reads] == [
        "pulse_pack_offers",
        "pulse_billing_settings",
    ]


def test_buy_pulse_pack_requires_verified_unique_offer() -> None:
    operation = TurnOperation(
        type="buy_pulse_pack",
        entities=TurnEntities(pulse_count=2000),
        execution_intent="execute",
    )
    step = plan_turn(
        TiaTurnUnderstanding(operations=[operation], safety_signals=[]),
        _planner_context(),
    ).steps[0]

    assert step.disposition == "read"
    assert step.write_intent is not None
    assert step.write_intent.kind == "buy_pulse_pack"
    assert step.write_intent.parameters["pulse_count"] == 2000

    ready = advance_step_after_verification(
        step,
        VerificationFacts(
            pulse_offer_match_count=1,
            verified_parameters={
                "pulse_pack_offer_id": str(uuid4()),
                "device_key": "candela_gentle",
                "pulse_count": 2000,
                "price_minor": 250_000,
                "currency": "EGP",
            },
        ),
    )
    assert ready.disposition == "write_ready"

    ambiguous = advance_step_after_verification(
        step,
        VerificationFacts(pulse_offer_match_count=2),
    )
    assert ambiguous.disposition == "clarify"
    assert ambiguous.write_intent is not None


def test_pulse_offer_read_filters_by_count_without_model_math(monkeypatch) -> None:
    offer_1000 = SimpleNamespace(
        id=uuid4(),
        workspace_id=uuid4(),
        device_key="candela_gentle",
        device_name="Candela Gentle",
        pulses_count=1000,
        price_minor=150_000,
        currency="EGP",
        is_active=True,
        created_at=NOW,
        updated_at=NOW,
        model_dump=lambda **_kwargs: {
            "pulses_count": 1000,
            "price_minor": 150_000,
            "currency": "EGP",
        },
    )
    offer_2000 = SimpleNamespace(
        id=uuid4(),
        workspace_id=offer_1000.workspace_id,
        device_key="candela_gentle",
        device_name="Candela Gentle",
        pulses_count=2000,
        price_minor=250_000,
        currency="EGP",
        is_active=True,
        created_at=NOW,
        updated_at=NOW,
        model_dump=lambda **_kwargs: {
            "pulses_count": 2000,
            "price_minor": 250_000,
            "currency": "EGP",
        },
    )
    monkeypatch.setattr(
        "app.services.agent_v2.read_executor.list_pulse_pack_offers",
        lambda *_args, **_kwargs: [offer_1000, offer_2000],
    )

    operation = TurnOperation(
        type="buy_pulse_pack",
        entities=TurnEntities(pulse_count=2000),
        execution_intent="execute",
    )
    step = plan_turn(
        TiaTurnUnderstanding(operations=[operation], safety_signals=[]),
        _planner_context(),
    ).steps[0]
    context = ReadExecutionContext(
        db=object(),
        workspace=SimpleNamespace(id=offer_1000.workspace_id),
        patient=SimpleNamespace(id=uuid4()),
        now=NOW,
    )

    bundle = execute_step_reads(step, context)

    assert bundle.verification.pulse_offer_match_count == 1
    assert bundle.verification.verified_parameters["pulse_count"] == 2000
    assert bundle.verification.verified_parameters["price_minor"] == 250_000


def test_agent_pulse_purchase_never_assumes_payment(monkeypatch) -> None:
    workspace = SimpleNamespace(id=uuid4())
    patient = SimpleNamespace(id=uuid4(), status="active")
    offer_id = uuid4()
    captured = {}

    def fake_purchase(_db, **kwargs):
        captured.update(kwargs)
        return SimpleNamespace(
            id=uuid4(),
            status="active",
            sale_price_minor=250_000,
            currency="EGP",
        )

    monkeypatch.setattr(
        "app.services.agent_v2.write_executor.purchase_pulse_pack_offer",
        fake_purchase,
    )

    step = PlanStep(
        operation_index=0,
        operation_type="buy_pulse_pack",
        disposition="write_ready",
        write_intent=WriteIntent(
            kind="buy_pulse_pack",
            authorized=True,
            parameters={"pulse_pack_offer_id": str(offer_id)},
        ),
        response_goal="pulse_pack_purchased",
    )
    db = SimpleNamespace(
        begin_nested=lambda: nullcontext(),
        commit=lambda: None,
        rollback=lambda: None,
    )

    result = execute_write_ready_step(
        db,
        workspace=workspace,
        patient=patient,
        step=step,
        idempotency_key="pulse-agent-test",
        commit=False,
    )

    assert result["ok"] is True
    assert result["amount_paid_minor"] == 0
    assert captured["amount_paid_minor"] == 0
    assert result["sale_price_minor"] == 250_000
    assert result["currency"] == "EGP"
    assert captured["payment_method"] == "unknown"
    assert captured["actor_type"] == "ai"
