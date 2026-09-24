from __future__ import annotations

from tools.agent_eval.harness import ScenarioResult
from tools.agent_eval.run_batch_02 import (
    CASES,
    _apply_cost,
    _short_long_comparison,
    db_delta,
)


def _row(scenario_id: str, *, input_tokens: int, cached: int, uncached: int):
    return ScenarioResult(
        id=scenario_id,
        category="test",
        purpose="test",
        turns=[],
        state_before={},
        state_after={},
        db_verification={},
        evaluation={},
        issues=[],
        token_usage={
            "input_tokens": input_tokens,
            "output_tokens": 100,
            "cached_tokens": cached,
            "cache_write_tokens": 0,
            "uncached_input_tokens": uncached,
            "total_tokens": input_tokens + 100,
            "calls": 2,
            "metadata_missing_calls": 0,
        },
    )


def test_batch_02_has_24_ordered_scenarios() -> None:
    names = [case.__name__ for case in CASES]
    assert len(names) == 24
    assert names[0] == "case_01_compound_price_booking"
    assert names[-4:] == [
        "case_21_long_returning_customer",
        "case_22_long_db_wins_over_stale_chat",
        "case_23_long_old_context_no_leak",
        "case_24_short_control",
    ]


def test_db_delta_tracks_financial_and_balance_changes() -> None:
    before = {
        "appointments": [],
        "packages": [],
        "pulse_packs": [],
        "payments": [],
        "pulse_usages": [],
        "pulse_settlements": [],
        "pulse_balances": [{"device_key": "candela_gentle", "pulses_remaining": 100}],
    }
    after = {
        **before,
        "pulse_packs": [{"id": "p1"}],
        "pulse_balances": [{"device_key": "candela_gentle", "pulses_remaining": 600}],
    }
    delta = db_delta(before, after)
    assert delta["pulse_packs"]["created"] == ["p1"]
    assert delta["pulse_balance_delta"] == {"candela_gentle": 500}


def test_apply_cost_uses_cache_read_and_write_rates() -> None:
    row = _row("cost", input_tokens=1000, cached=400, uncached=400)
    row.token_usage["cache_write_tokens"] = 200
    _apply_cost(
        row,
        input_price=0.20,
        cached_price=0.02,
        output_price=1.20,
        cache_write_multiplier=1.25,
    )
    expected_input = (
        400 * 0.20 / 1_000_000
        + 400 * 0.02 / 1_000_000
        + 200 * 0.20 * 1.25 / 1_000_000
    )
    expected_output = 100 * 1.20 / 1_000_000
    assert row.cost["actual_input_usd"] == round(expected_input, 8)
    assert row.cost["actual_total_usd"] == round(expected_input + expected_output, 8)
    assert row.cost["without_explicit_cache_usd"] == round(
        1000 * 0.20 / 1_000_000 + expected_output,
        8,
    )


def test_short_long_comparison_reports_token_growth() -> None:
    short = _row("b2_24_short_control", input_tokens=1000, cached=800, uncached=200)
    long = _row("b2_23_long_old_context_no_leak", input_tokens=1200, cached=800, uncached=400)
    comparison = _short_long_comparison([short, long])
    assert comparison["short_deterministic_ok"] is True
    assert comparison["long_deterministic_ok"] is True
    assert comparison["input_growth_percent"] == 20.0
