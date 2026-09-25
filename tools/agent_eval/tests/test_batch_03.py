from __future__ import annotations

from tools.agent_eval.harness import ScenarioResult, TurnCapture
from tools.agent_eval.run_batch_03 import CASES, _stage_metrics, db_delta


def test_batch_03_has_22_ordered_scenarios() -> None:
    names = [case.__name__ for case in CASES]
    assert len(names) == 22
    assert len(set(names)) == len(names)
    assert names[:4] == [
        "case_01_handoff_during_active_booking",
        "case_02_staff_takeover_then_handback",
        "case_03_financial_handoff_then_new_booking",
        "case_04_lifecycle_while_human_owns",
    ]
    assert names[4:9] == [
        "case_05_two_appointments_explicit_date",
        "case_06_two_same_service_explicit_date",
        "case_07_real_appointment_ambiguity",
        "case_08_candidate_selection_followup",
        "case_09_cancel_one_of_multiple",
    ]
    assert names[9:15] == [
        "case_10_one_session_remaining",
        "case_11_exhausted_package",
        "case_12_expired_package",
        "case_13_two_eligible_packages",
        "case_14_package_booking_then_cancel",
        "case_15_package_booking_then_reschedule",
    ]
    assert names[-4:] == [
        "case_19_price_package_booking",
        "case_20_side_query_during_reschedule",
        "case_21_repeated_corrections",
        "case_22_abandon_then_different_booking",
    ]


def test_db_delta_tracks_package_usage_handoff_and_pulse_balance() -> None:
    before = {
        "appointments": [{"id": "a1", "status": "confirmed"}],
        "packages": [{"id": "p1", "remaining": 2}],
        "package_usages": [],
        "pulse_packs": [],
        "payments": [],
        "pulse_usages": [],
        "pulse_settlements": [],
        "handoffs": [],
        "pulse_balances": [
            {"device_key": "candela_gentle", "pulses_remaining": 100}
        ],
    }
    after = {
        **before,
        "appointments": [{"id": "a1", "status": "cancelled"}],
        "packages": [{"id": "p1", "remaining": 1}],
        "package_usages": [
            {
                "id": "u1",
                "patient_package_id": "p1",
                "appointment_id": "a1",
                "status": "released",
            }
        ],
        "handoffs": [{"id": "h1", "status": "pending"}],
        "pulse_balances": [
            {"device_key": "candela_gentle", "pulses_remaining": 150}
        ],
    }
    delta = db_delta(before, after)
    assert delta["appointments"]["changed"] == ["a1"]
    assert delta["packages"]["changed"] == ["p1"]
    assert delta["package_usages"]["created"] == ["u1"]
    assert delta["handoffs"]["created"] == ["h1"]
    assert delta["pulse_balance_delta"] == {"candela_gentle": 50}


def _turn(operation: str) -> TurnCapture:
    return TurnCapture(
        scenario_id="test",
        turn_number=1,
        user_message="x",
        agent_response="y",
        model="gpt",
        latency_ms=10,
        token_usage={
            "input_tokens": 10,
            "output_tokens": 2,
            "cached_tokens": 4,
            "cache_write_tokens": 3,
            "uncached_input_tokens": 3,
            "total_tokens": 12,
            "calls": 1,
            "metadata_missing_calls": 0,
        },
        runtime_state={},
        verified_reads=[],
        actions=[],
        write_attempted=False,
        write_result=None,
        handoff_state=None,
        llm_calls=[
            {
                "operation": operation,
                "input_tokens_actual": 10,
                "cached_tokens_actual": 4,
                "cache_write_tokens_actual": 3,
                "uncached_input_tokens_actual": 3,
                "output_tokens_actual": 2,
                "latency_ms": 10,
                "retry_count": 0,
                "fallback_used": False,
            }
        ],
    )


def _row(turns: list[TurnCapture]) -> ScenarioResult:
    return ScenarioResult(
        id="test",
        category="test",
        purpose="test",
        turns=turns,
        state_before={},
        state_after={},
        db_verification={},
        evaluation={},
        issues=[],
        token_usage={},
    )


def test_stage_metrics_counts_current_responder_operation_name() -> None:
    metrics = _stage_metrics(
        [_row([_turn("v2-turn-interpreter"), _turn("v2-customer-responder")])]
    )
    assert metrics["interpreter"]["calls"] == 1
    assert metrics["responder"]["calls"] == 1
    assert metrics["all"]["calls"] == 2
    assert metrics["all"]["input_tokens"] == 20
