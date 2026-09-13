from datetime import UTC, datetime

from app.agents.v2.semantic_context import SemanticContext, SemanticReferenceTarget
from app.agents.v2.turn_contract import (
    EntityReference,
    TiaTurnUnderstanding,
    TurnEntities,
    TurnOperation,
)
from app.services.agent_v2.planner import PlannerContext, plan_turn


def _context() -> PlannerContext:
    semantic = SemanticContext(
        model_input={},
        reference_map={
            "S1": SemanticReferenceTarget(kind="service", canonical_id="svc-underarm"),
            "V1": SemanticReferenceTarget(kind="device", canonical_id="prime-lase"),
            "V2": SemanticReferenceTarget(kind="device", canonical_id="candela"),
            "P1": SemanticReferenceTarget(kind="package", canonical_id="pkg-prime-6"),
        },
    )
    return PlannerContext(
        semantic_context=semantic,
        active_task=None,
        now=datetime(2026, 9, 13, 9, 0, tzinfo=UTC),
    )


def _pricing(*, device_ref: str | None = None, sessions: int | None = None) -> TurnOperation:
    return TurnOperation(
        type="pricing",
        entities=TurnEntities(
            service=EntityReference(ref="S1"),
            device=EntityReference(ref=device_ref) if device_ref else None,
            package_sessions=sessions,
        ),
        execution_intent="informational",
    )


def test_plain_session_pricing_stays_on_service_catalog() -> None:
    plan = plan_turn(TiaTurnUnderstanding(operations=[_pricing(device_ref="V1")]), _context())

    step = plan.steps[0]
    assert step.response_goal == "answer_price"
    assert [request.kind for request in step.reads] == ["service_catalog"]
    assert step.reads[0].parameters == {"service_id": "svc-underarm"}


def test_package_session_count_routes_pricing_to_package_offers() -> None:
    plan = plan_turn(
        TiaTurnUnderstanding(operations=[_pricing(device_ref="V1", sessions=6)]),
        _context(),
    )

    step = plan.steps[0]
    assert step.response_goal == "answer_price"
    assert [request.kind for request in step.reads] == ["package_offers"]
    assert step.reads[0].parameters["service_id"] == "svc-underarm"
    assert step.reads[0].parameters["device_key"] == "prime-lase"
    assert step.reads[0].parameters["package_sessions"] == 6


def test_concrete_package_target_routes_pricing_to_package_offers() -> None:
    operation = TurnOperation(
        type="pricing",
        entities=TurnEntities(package=EntityReference(ref="P1")),
        execution_intent="informational",
    )
    plan = plan_turn(TiaTurnUnderstanding(operations=[operation]), _context())

    step = plan.steps[0]
    assert [request.kind for request in step.reads] == ["package_offers"]
    assert step.reads[0].parameters["package_id"] == "pkg-prime-6"
    assert step.clarification_field is None


def test_two_device_package_prices_keep_independent_offer_filters() -> None:
    turn = TiaTurnUnderstanding(
        operations=[
            _pricing(device_ref="V1", sessions=6),
            _pricing(device_ref="V2", sessions=6),
        ]
    )
    plan = plan_turn(turn, _context())

    assert [step.reads[0].kind for step in plan.steps] == [
        "package_offers",
        "package_offers",
    ]
    assert [step.reads[0].parameters["device_key"] for step in plan.steps] == [
        "prime-lase",
        "candela",
    ]
    assert all(step.reads[0].parameters["package_sessions"] == 6 for step in plan.steps)
