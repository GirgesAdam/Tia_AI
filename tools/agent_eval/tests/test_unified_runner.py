from __future__ import annotations

import json
from pathlib import Path

from tools.agent_eval.registry import (
    failed_ids_from_report,
    scenarios_for_batch,
    select_scenarios,
)
from tools.agent_eval.reporting import summary_from_rows
from tools.agent_eval.run import main


def test_registry_loads_all_three_batches() -> None:
    assert len(scenarios_for_batch("batch_01")) == 15
    assert len(scenarios_for_batch("batch_02")) == 24
    assert len(scenarios_for_batch("batch_03")) == 22


def test_batch_and_scenario_filtering() -> None:
    rows = select_scenarios("batch_03", selectors={"S1", "S4", "S5"})
    assert [row.id for row in rows] == ["S1", "S4", "S5"]
    assert all(row.batch == "batch_03" for row in rows)


def test_tag_filtering() -> None:
    rows = select_scenarios("batch_03", tag="handoff")
    assert rows
    assert all("handoff" in row.tags for row in rows)


def test_failed_rerun_selection(tmp_path: Path, capsys) -> None:
    report = tmp_path / "report.json"
    report.write_text(
        json.dumps({
            "scenario_results": [
                {"id": "b3_01_handoff_during_active_booking", "issues": [{"severity": "P1"}]},
                {"id": "b3_05_two_appointments_explicit_date", "issues": []},
            ]
        }),
        encoding="utf-8",
    )
    assert main([
        "--batch", "batch_03", "--profile", "quick",
        "--rerun-failed", str(report),
    ]) == 0
    output = capsys.readouterr().out
    assert "Selected scenarios: 1" in output
    assert "b3_01_handoff_during_active_booking" in output


def test_failed_ids_from_report() -> None:
    payload = {"scenario_results": [
        {"id": "a", "issues": []},
        {"id": "b", "issues": [{"severity": "P2"}]},
        {"id": "c", "execution_error": "boom"},
    ]}
    assert failed_ids_from_report(payload) == {"b", "c"}


def test_summary_report_generation() -> None:
    rows = [
        {
            "issues": [],
            "token_usage": {"total_tokens": 10},
            "cost": {"actual_total_usd": 0.01},
        },
        {
            "issues": [{"severity": "P1"}],
            "token_usage": {"total_tokens": 20},
            "cost": {"actual_total_usd": 0.02},
        },
    ]
    result = summary_from_rows(rows, duration_seconds=1.25)
    assert result["Total scenarios"] == 2
    assert result["Passed"] == 1
    assert result["Failed"] == 1
    assert result["P1"] == 1
    assert result["Tokens"] == 30
    assert result["Cost"] == 0.03
    assert result["Duration"] == 1.25


def test_quick_profile_needs_no_runtime_config(capsys) -> None:
    assert main(["--batch", "batch_03", "--profile", "quick"]) == 0
    output = capsys.readouterr().out
    assert "Selected scenarios: 22" in output
    assert "no DB or LLM execution" in output


def test_default_profile_is_safe_quick(capsys) -> None:
    assert main(["--batch", "batch_03"]) == 0
    output = capsys.readouterr().out
    assert "Selected scenarios: 22" in output
    assert "no DB or LLM execution" in output


def test_legacy_batch_entrypoints_remain_present() -> None:
    root = Path(__file__).resolve().parents[1]
    for name in ("run_batch_01.py", "run_batch_02.py", "run_batch_03.py"):
        source = (root / name).read_text(encoding="utf-8")
        assert "def main()" in source
        assert "CASES" in source
