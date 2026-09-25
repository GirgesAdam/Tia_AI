from __future__ import annotations

from tools.agent_eval.registry import scenarios_for_batch, select_scenarios
from tools.agent_eval.run import main


def test_batch4_registry_has_seventeen_new_scenarios() -> None:
    rows = scenarios_for_batch("batch_04")
    assert len(rows) == 17
    assert [row.id for row in rows] == [f"S{index}" for index in range(1, 18)]
    assert len({row.canonical_id for row in rows}) == 17
    assert all(row.canonical_id.startswith("b4_") for row in rows)


def test_batch4_families_are_represented() -> None:
    ids = {row.canonical_id for row in scenarios_for_batch("batch_04")}
    expected_fragments = {
        "after_gap",
        "human_owns",
        "package_reschedule_cancel",
        "two_appointments",
        "price_availability",
        "repeat_reschedule",
        "repeat_package",
    }
    assert all(any(fragment in scenario_id for scenario_id in ids) for fragment in expected_fragments)


def test_batch4_scenario_filtering() -> None:
    rows = select_scenarios("batch_04", selectors={"S1", "S7", "S17"})
    assert [row.id for row in rows] == ["S1", "S7", "S17"]


def test_batch4_quick_profile_performs_no_live_execution(capsys) -> None:
    assert main(["--batch", "batch_04", "--profile", "quick"]) == 0
    output = capsys.readouterr().out
    assert "Selected scenarios: 17" in output
    assert "no DB or LLM execution" in output
