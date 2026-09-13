from datetime import datetime, timezone
from pathlib import Path

from app.agents.v2.semantic_context import SemanticContext
from app.agents.v2.turn_contract import TiaTurnUnderstanding, TurnEntities, TurnOperation
from app.agents.v2.turn_interpreter import _interpreter_system_prompt
from app.services.agent_v2.planner import PlannerContext, plan_turn


def test_semantic_matrix_covers_package_session_intent_contract() -> None:
    backend = Path(__file__).resolve().parent.parent
    source = (backend / "scripts/run_agent_e2e_matrix.py").read_text(encoding="utf-8")

    required_cases = (
        "package_purchase_explicit",
        "package_purchase_multisession_plan",
        "package_inquiry_compare",
        "package_use_existing",
        "package_avoid_existing",
        "single_session_no_package_intent",
    )
    for case in required_cases:
        assert case in source

    for intent in ("purchase", "inquire", "use_existing", "avoid_existing", "none"):
        assert f'_package_intent("{intent}")' in source


def test_package_semantic_matrix_does_not_use_runtime_lexical_routing() -> None:
    backend = Path(__file__).resolve().parent.parent
    source = (backend / "scripts/run_agent_e2e_matrix.py").read_text(encoding="utf-8").lower()

    assert "re.compile" not in source
    assert "re.search" not in source
    assert "re.match" not in source


def test_history_package_impact_prompt_preserves_both_semantic_domains() -> None:
    prompt = _interpreter_system_prompt(
        timezone_name="Africa/Cairo",
        local_now=datetime(2026, 9, 13, 12, 0, tzinfo=timezone.utc),
    ).lower()

    assert "past appointment outcome" in prompt
    assert "owned-package balance" in prompt
    assert "customer_history" in prompt
    assert "package_info" in prompt


def test_history_package_impact_plans_both_verified_reads_without_writes() -> None:
    turn = TiaTurnUnderstanding(
        operations=[
            TurnOperation(
                type="customer_history",
                entities=TurnEntities(),
                execution_intent="informational",
            ),
            TurnOperation(
                type="package_info",
                entities=TurnEntities(),
                execution_intent="informational",
            ),
        ]
    )
    context = PlannerContext(
        semantic_context=SemanticContext(model_input={}, reference_map={}),
        active_task=None,
        now=datetime(2026, 9, 13, 12, 0, tzinfo=timezone.utc),
    )

    plan = plan_turn(turn, context)

    assert [read.kind for step in plan.steps for read in step.reads] == [
        "customer_history",
        "customer_packages",
    ]
    assert all(step.disposition == "read" for step in plan.steps)
    assert all(step.write_intent is None for step in plan.steps)
