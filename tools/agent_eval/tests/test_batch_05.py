from __future__ import annotations

from tools.agent_eval.registry import scenarios_for_batch, select_scenarios
from tools.agent_eval.run import main


def test_batch5_registry_has_fifteen_new_scenarios() -> None:
    rows = scenarios_for_batch("batch_05")
    assert len(rows) == 15
    assert [row.id for row in rows] == [f"S{index}" for index in range(1, 16)]
    assert len({row.canonical_id for row in rows}) == 15
    assert all(row.canonical_id.startswith("b5_") for row in rows)


def test_batch5_families_are_represented() -> None:
    ids = {row.canonical_id for row in scenarios_for_batch("batch_05")}
    expected_fragments = {
        "same_name",
        "schedule_changes",
        "incompatible_device",
        "doctor_change",
        "competing_laser",
        "rapid_customer_turns",
    }
    assert all(any(fragment in scenario_id for scenario_id in ids) for fragment in expected_fragments)
def test_batch5_scenario_filtering() -> None:
    rows = select_scenarios("batch_05", selectors={"S1", "S7", "S15"})
    assert [row.id for row in rows] == ["S1", "S7", "S15"]


def test_batch5_quick_profile_performs_no_live_execution(capsys) -> None:
    assert main(["--batch", "batch_05", "--profile", "quick"]) == 0
    output = capsys.readouterr().out
    assert "Selected scenarios: 15" in output
    assert "no DB or LLM execution" in output
