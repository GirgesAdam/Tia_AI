from __future__ import annotations

from contextlib import nullcontext
from datetime import UTC, datetime
from types import SimpleNamespace
from uuid import uuid4

from app.agents.v2.semantic_context import build_semantic_context
from app.agents.v2.semantic_state_view import with_safe_action_context
from app.agents.v2.turn_contract import (
    EntityReference,
    TiaTurnUnderstanding,
    TurnEntities,
    TurnOperation,
)
from app.agents.v2.turn_interpreter import merge_verified_action_context
from app.agents.v2.turn_normalization import (
    dedupe_exact_operations,
    normalize_semantic_invariants,
)
from app.services.agent_v2.planner import (
    PlannerContext,
    PlanStep,
    ReadRequest,
    VerificationFacts,
    WriteIntent,
    advance_step_after_verification,
    plan_turn,
)
from app.services.agent_v2.read_executor import (
    ReadExecutionContext,
    execute_step_reads,
)
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


def test_pulse_pack_pricing_normalizes_from_structured_semantics() -> None:
    operation = TurnOperation(
        type="pricing",
        entities=TurnEntities(
            device=EntityReference(
                text="Candela Gentle",
                ref="device:candela_gentle",
            ),
            pulse_count=1000,
        ),
        requested_service_details=["price"],
        requested_pulse_details=["offers"],
        execution_intent="informational",
    )

    normalized = normalize_semantic_invariants(
        TiaTurnUnderstanding(operations=[operation], safety_signals=[])
    )
    result = normalized.operations[0]

    assert result.type == "pulse_info"
    assert result.entities.pulse_count == 1000
    assert result.entities.device == operation.entities.device
    assert result.requested_service_details == []
    assert result.requested_pulse_details == ["offers"]
    assert result.execution_intent == "informational"


def test_counted_overage_semantics_are_not_normalized_to_pack_offer() -> None:
    operation = TurnOperation(
        type="pricing",
        entities=TurnEntities(
            device=EntityReference(
                text="Candela Gentle",
                ref="device:candela_gentle",
            ),
            pulse_count=1000,
        ),
        requested_service_details=["price"],
        requested_pulse_details=["overage_price"],
        execution_intent="informational",
    )

    normalized = normalize_semantic_invariants(
        TiaTurnUnderstanding(operations=[operation], safety_signals=[])
    )
    result = normalized.operations[0]

    assert result.type == "pulse_info"
    assert result.requested_pulse_details == ["overage_price"]
    assert result.entities.pulse_count == 1000


def test_new_turn_contract_has_no_pulse_billing_choice() -> None:
    properties = TurnOperation.model_json_schema()["properties"]

    assert "pulse_usage" not in properties


def test_pulse_pricing_normalizer_does_not_override_service_pricing() -> None:
    operation = TurnOperation(
        type="pricing",
        entities=TurnEntities(
            service=EntityReference(text="Full Body"),
            pulse_count=1000,
        ),
        requested_service_details=["price"],
        execution_intent="informational",
    )

    normalized = normalize_semantic_invariants(
        TiaTurnUnderstanding(operations=[operation], safety_signals=[])
    )

    assert normalized.operations[0] == operation


def test_pulse_dedupe_identity_preserves_distinct_counts_and_details() -> None:
    first = TurnOperation(
        type="pulse_info",
        entities=TurnEntities(pulse_count=1000),
        requested_pulse_details=["offers"],
        execution_intent="informational",
    )
    second = TurnOperation(
        type="pulse_info",
        entities=TurnEntities(pulse_count=2000),
        requested_pulse_details=["offers"],
        execution_intent="informational",
    )
    third = TurnOperation(
        type="pulse_info",
        entities=TurnEntities(pulse_count=1000),
        requested_pulse_details=["balance"],
        execution_intent="informational",
    )

    normalized = dedupe_exact_operations(
        TiaTurnUnderstanding(
            operations=[first, second, third],
            safety_signals=[],
        )
    )

    assert normalized.operations == [first, second, third]


def test_agent_booking_ignores_legacy_pulse_billing_parameter(monkeypatch) -> None:
    workspace = SimpleNamespace(id=uuid4())
    patient = SimpleNamespace(id=uuid4(), status="active")
    captured = {}

    monkeypatch.setattr(
        "app.services.agent_v2.write_executor.require_tia_workspace_domain_write",
        lambda *_args, **_kwargs: None,
    )
    monkeypatch.setattr(
        "app.services.agent_v2.write_executor.resolve_booking_package",
        lambda *_args, **_kwargs: SimpleNamespace(
            package_id=None,
            package_used=False,
            package_name=None,
        ),
    )

    def fake_create(_db, **kwargs):
        captured.update(kwargs)
        return SimpleNamespace(id=uuid4(), status="pending")

    monkeypatch.setattr(
        "app.services.agent_v2.write_executor.create_appointment_operation",
        fake_create,
    )

    step = PlanStep(
        operation_index=0,
        operation_type="book",
        disposition="write_ready",
        write_intent=WriteIntent(
            kind="booking",
            authorized=True,
            parameters={
                "branch_id": str(uuid4()),
                "doctor_id": str(uuid4()),
                "service_id": str(uuid4()),
                "start_at": "2026-09-25T14:00:00+03:00",
                "device_key": "candela_gentle",
                "package_usage": "unspecified",
                "pulse_usage": "use_existing",
            },
        ),
        response_goal="booking_completed",
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
        idempotency_key="pulse-booking-test",
        commit=False,
    )

    assert result["ok"] is True
    assert "pulse_billing_selected" not in result
    assert "pulse_consumption_recorded" not in result
    assert "billing_context" not in result
    assert "pulse_balance_used" not in result
    assert captured["use_pulse_balance"] is False


def test_explicit_pulse_purchase_continuation_inherits_verified_device() -> None:
    context = build_semantic_context(
        {
            "services": [
                {
                    "id": "service-laser",
                    "name": "ليزر إبط",
                    "laser_devices": [
                        {
                            "device_key": "candela_gentle",
                            "device_name": "Candela Gentle",
                        }
                    ],
                }
            ],
            "doctors": [],
            "appointments": [],
            "packages": [],
        }
    )
    context = with_safe_action_context(
        context,
        action_context={
            "operation_type": "buy_pulse_pack",
            "device_key": "candela_gentle",
            "pulse_count": 1000,
        },
    )
    operation = TurnOperation(
        type="book",
        entities=TurnEntities(),
        continues_previous=True,
        execution_intent="execute",
    )

    merged = merge_verified_action_context(
        TiaTurnUnderstanding(operations=[operation], safety_signals=[]),
        context,
    )

    assert merged.operations[0].entities.device is not None
    assert merged.operations[0].entities.device.ref == "V1"


def test_unrelated_pulse_booking_does_not_inherit_previous_purchase_device() -> None:
    context = build_semantic_context(
        {
            "services": [
                {
                    "id": "service-laser",
                    "name": "ليزر إبط",
                    "laser_devices": [
                        {
                            "device_key": "candela_gentle",
                            "device_name": "Candela Gentle",
                        }
                    ],
                }
            ],
            "doctors": [],
            "appointments": [],
            "packages": [],
        }
    )
    context = with_safe_action_context(
        context,
        action_context={
            "operation_type": "buy_pulse_pack",
            "device_key": "candela_gentle",
            "pulse_count": 1000,
        },
    )
    operation = TurnOperation(
        type="book",
        entities=TurnEntities(),
        continues_previous=False,
        execution_intent="execute",
    )

    merged = merge_verified_action_context(
        TiaTurnUnderstanding(operations=[operation], safety_signals=[]),
        context,
    )

    assert merged.operations[0].entities.device is None


def test_pulse_purchase_and_booking_remain_independent_ordered_steps() -> None:
    purchase = TurnOperation(
        type="buy_pulse_pack",
        entities=TurnEntities(pulse_count=2000),
        execution_intent="execute",
    )
    booking = TurnOperation(
        type="book",
        entities=TurnEntities(
            service=None,
        ),
        execution_intent="execute",
    )
    turn = TiaTurnUnderstanding(
        operations=[purchase, booking],
        safety_signals=[],
    )

    plan = plan_turn(turn, _planner_context())

    assert [step.operation_type for step in plan.steps] == [
        "buy_pulse_pack",
        "book",
    ]
    assert plan.steps[0].write_intent is not None
    assert plan.steps[0].write_intent.kind == "buy_pulse_pack"
    assert plan.steps[1].write_intent is None
    assert plan.steps[1].disposition == "clarify"
    assert plan.steps[1].clarification_field == "service"


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


def test_compound_pack_and_overage_info_plans_both_verified_reads() -> None:
    operation = TurnOperation(
        type="pulse_info",
        entities=TurnEntities(
            device=EntityReference(
                text="Candela Gentle",
                ref="device:candela_gentle",
            ),
            pulse_count=1000,
        ),
        requested_pulse_details=["offers", "overage_price"],
        execution_intent="informational",
    )

    step = plan_turn(
        TiaTurnUnderstanding(operations=[operation], safety_signals=[]),
        _planner_context(),
    ).steps[0]

    assert step.disposition == "read"
    assert step.write_intent is None
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

def test_owned_pulse_pack_read_hides_financial_ledger_fields(monkeypatch) -> None:
    raw = {
        "device_key": "candela_gentle",
        "device_name": "Candela Gentle",
        "pulses_purchased": 2000,
        "pulses_consumed": 750,
        "pulses_remaining": 1250,
        "purchased_at": NOW.isoformat(),
        "expires_at": None,
        "status": "active",
        "effective_status": "active",
        "sale_price_minor": 250_000,
        "amount_paid_minor": 100_000,
        "balance_due_minor": 150_000,
        "purchase_transaction_id": str(uuid4()),
    }

    def model_dump(*, mode, include):
        assert mode == "json"
        return {key: raw[key] for key in include if key in raw}

    monkeypatch.setattr(
        "app.services.agent_v2.read_executor.list_patient_pulse_packs",
        lambda *_args, **kwargs: (
            [SimpleNamespace(model_dump=model_dump)]
            if kwargs.get("include_financials") is False
            else []
        ),
    )
    step = PlanStep(
        operation_index=0,
        operation_type="pulse_info",
        disposition="read",
        reads=[ReadRequest(kind="pulse_packs")],
        response_goal="pulse_information",
    )
    context = ReadExecutionContext(
        db=object(),
        workspace=SimpleNamespace(id=uuid4()),
        patient=SimpleNamespace(id=uuid4()),
        now=NOW,
    )

    bundle = execute_step_reads(step, context)
    pack = bundle.results[0].payload["packs"][0]

    assert pack["pulses_remaining"] == 1250
    assert pack["pulses_consumed"] == 750
    assert "amount_paid_minor" not in pack
    assert "balance_due_minor" not in pack
    assert "purchase_transaction_id" not in pack
    assert "sale_price_minor" not in pack


def test_counted_overage_uses_verified_unit_price_math(monkeypatch) -> None:
    row = SimpleNamespace(
        device_key="candela_gentle",
        device_name="Candela Gentle",
        overage_price_minor=150,
        currency="EGP",
        model_dump=lambda **_kwargs: {
            "device_key": "candela_gentle",
            "device_name": "Candela Gentle",
            "overage_price_minor": 150,
            "currency": "EGP",
        },
    )
    monkeypatch.setattr(
        "app.services.agent_v2.read_executor.list_pulse_billing_settings",
        lambda *_args, **_kwargs: [row],
    )
    step = PlanStep(
        operation_index=0,
        operation_type="pulse_info",
        disposition="read",
        reads=[
            ReadRequest(
                kind="pulse_billing_settings",
                parameters={"device_key": "candela_gentle", "pulse_count": 1000},
            )
        ],
        response_goal="pulse_information",
    )
    context = ReadExecutionContext(
        db=object(),
        workspace=SimpleNamespace(id=uuid4()),
        patient=SimpleNamespace(id=uuid4()),
        now=NOW,
    )

    bundle = execute_step_reads(step, context)
    payload = bundle.results[0].payload

    assert payload["requested_pulse_count"] == 1000
    assert payload["overage_total_minor"] == 150_000
    assert payload["currency"] == "EGP"

