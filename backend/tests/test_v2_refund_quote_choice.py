from app.agents.v2.semantic_context import build_semantic_context
from app.agents.v2.turn_contract import TiaTurnUnderstanding, TurnEntities, TurnOperation
from app.services.agent_v2.outcome_builder import build_step_outcome, customer_visible_outcome
from app.services.agent_v2.planner import PlanStep, ReadRequest
from app.services.agent_v2.read_executor import ReadExecutionBundle, ReadResult


def test_multiple_safe_refund_quotes_require_package_choice() -> None:
    context = build_semantic_context({"services": [], "doctors": []})
    operation = TurnOperation(type="refund_quote", entities=TurnEntities())
    turn = TiaTurnUnderstanding(operations=[operation], safety_signals=[])
    step = PlanStep(
        operation_index=0,
        operation_type="refund_quote",
        disposition="read",
        reads=[ReadRequest(kind="package_refund_quote")],
        response_goal="package_refund_quote",
    )
    reads = ReadExecutionBundle(
        results=[
            ReadResult(
                kind="package_refund_quote",
                ok=True,
                payload={
                    "quotes": [
                        {
                            "patient_package_id": "secret-package-1",
                            "package_name": "باكيدج إبط 6 جلسات",
                            "remaining_sessions": 4,
                            "refund_amount_minor": 180000,
                            "currency": "EGP",
                        },
                        {
                            "patient_package_id": "secret-package-2",
                            "package_name": "باكيدج إبط 8 جلسات",
                            "remaining_sessions": 7,
                            "refund_amount_minor": 260000,
                            "currency": "EGP",
                        },
                    ],
                    "unsafe_package_ids": [],
                    "needs_package_choice": True,
                },
            )
        ]
    )

    outcome = build_step_outcome(
        step,
        turn=turn,
        semantic_context=context,
        reads=reads,
    )
    visible = customer_visible_outcome(outcome)

    assert outcome.status == "needs_input"
    assert outcome.response_goal == "ask_package_choice"
    assert outcome.facts == {"needed": "package", "available_quote_count": 2}
    assert [choice.label for choice in outcome.choices] == [
        "باكيدج إبط 6 جلسات",
        "باكيدج إبط 8 جلسات",
    ]
    assert visible["choices"][0]["facts"]["refund_amount"] == "1800.00 EGP"
    assert visible["choices"][1]["facts"]["refund_amount"] == "2600.00 EGP"
    assert "secret-package-1" not in str(visible)
    assert "secret-package-2" not in str(visible)


def test_single_safe_refund_quote_stays_answered() -> None:
    context = build_semantic_context({"services": [], "doctors": []})
    operation = TurnOperation(type="refund_quote", entities=TurnEntities())
    turn = TiaTurnUnderstanding(operations=[operation], safety_signals=[])
    step = PlanStep(
        operation_index=0,
        operation_type="refund_quote",
        disposition="read",
        reads=[ReadRequest(kind="package_refund_quote")],
        response_goal="package_refund_quote",
    )
    reads = ReadExecutionBundle(
        results=[
            ReadResult(
                kind="package_refund_quote",
                ok=True,
                payload={
                    "quotes": [
                        {
                            "patient_package_id": "secret-package-1",
                            "package_name": "باكيدج إبط 6 جلسات",
                            "refund_amount_minor": 180000,
                            "currency": "EGP",
                        }
                    ],
                    "unsafe_package_ids": [],
                    "needs_package_choice": False,
                },
            )
        ]
    )

    outcome = build_step_outcome(
        step,
        turn=turn,
        semantic_context=context,
        reads=reads,
    )

    assert outcome.status == "answered"
    assert outcome.response_goal == "package_refund_quote"
