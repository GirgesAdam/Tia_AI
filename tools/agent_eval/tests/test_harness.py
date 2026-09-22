from types import SimpleNamespace

import pytest
from langchain_core.messages import AIMessage, HumanMessage, SystemMessage

from tools.agent_eval.harness import TokenUsage, assert_demo_only
from tools.agent_eval.run_batch_01 import _reschedule_relationships_moved
from tools.agent_eval.run_token_attribution_baseline import CASES as ATTRIBUTION_CASES
from tools.agent_eval.token_attribution import (
    attach_actual_usage,
    interpreter_attribution,
    responder_attribution,
)


def test_token_usage_aggregates_actual_metadata():
    usage = TokenUsage()
    usage.add(
        {
            "input_tokens": 100,
            "output_tokens": 20,
            "total_tokens": 120,
            "input_token_details": {"cache_read": 40},
        }
    )
    assert usage.input_tokens == 100
    assert usage.output_tokens == 20
    assert usage.cached_tokens == 40
    assert usage.total_tokens == 120
    assert usage.metadata_missing_calls == 0


def test_demo_guard_fails_closed(monkeypatch):
    monkeypatch.setattr(
        "tools.agent_eval.harness.workspace_runtime_policy",
        lambda ws: SimpleNamespace(
            is_demo=False,
            allow_external_dispatch=False,
            allow_external_configuration=False,
            allow_external_ingress=False,
            allow_external_sync=False,
        ),
    )
    with pytest.raises(RuntimeError):
        assert_demo_only(SimpleNamespace(is_active=True))


def test_demo_guard_rejects_external_side_effects(monkeypatch):
    monkeypatch.setattr(
        "tools.agent_eval.harness.workspace_runtime_policy",
        lambda ws: SimpleNamespace(
            is_demo=True,
            allow_external_dispatch=True,
            allow_external_configuration=False,
            allow_external_ingress=False,
            allow_external_sync=False,
        ),
    )
    with pytest.raises(RuntimeError):
        assert_demo_only(SimpleNamespace(is_active=True))


def test_reschedule_relationship_contract_requires_exact_transfer():
    before = {
        "payment_allocation_ids": ["allocation-1"],
        "payment_transaction_ids": ["payment-1"],
        "package_usage_ids": ["usage-1"],
    }
    empty = {
        "payment_allocation_ids": [],
        "payment_transaction_ids": [],
        "package_usage_ids": [],
    }
    assert _reschedule_relationships_moved(before, empty, before) is True

    retained_on_original = {
        **empty,
        "payment_allocation_ids": ["allocation-1"],
    }
    assert (
        _reschedule_relationships_moved(
            before,
            retained_on_original,
            before,
        )
        is False
    )

    duplicated_on_replacement = {
        **before,
        "package_usage_ids": ["usage-1", "usage-2"],
    }
    assert (
        _reschedule_relationships_moved(
            before,
            empty,
            duplicated_on_replacement,
        )
        is False
    )


def test_interpreter_token_attribution_separates_verified_state_components():
    messages = [
        SystemMessage(content="system rules"),
        SystemMessage(content='SEMANTIC_CONTEXT:{"services":[{"ref":"S1","name":"Laser"}]}'),
        AIMessage(content="previous assistant"),
        HumanMessage(content="latest user"),
    ]
    model_input = {
        "services": [{"ref": "S1", "name": "Laser"}],
        "doctors": [{"ref": "D1", "name": "Doctor"}],
        "active_task": {"task_type": "booking", "service_ref": "S1"},
        "pending_choice": {"choice_type": "device", "refs": ["V1", "V2"]},
        "recent_verified_read": {"operation_type": "pricing", "service_ref": "S1"},
    }

    result = interpreter_attribution(messages=messages, model_input=model_input)

    assert result["system_tokens_estimated"] > 0
    assert result["semantic_context_tokens_estimated"] > 0
    assert result["semantic_catalog_tokens_estimated"] > 0
    assert result["conversation_history_tokens_estimated"] > 0
    assert result["latest_user_tokens_estimated"] > 0
    assert result["active_task_tokens_estimated"] > 0
    assert result["pending_choice_tokens_estimated"] > 0
    assert result["recent_verified_read_tokens_estimated"] > 0
    assert result["structured_schema_tokens_estimated"] > 0


def test_responder_token_attribution_tracks_grounded_outcome():
    messages = [
        SystemMessage(content="responder system"),
        AIMessage(content="previous assistant"),
        SystemMessage(content='TURN_OUTCOMES:[{"status":"answered"}]'),
        HumanMessage(content="latest user"),
    ]

    result = responder_attribution(messages=messages)

    assert result["system_tokens_estimated"] > 0
    assert result["grounded_outcome_tokens_estimated"] > 0
    assert result["conversation_history_tokens_estimated"] > 0
    assert result["semantic_context_tokens_estimated"] == 0
    assert result["structured_schema_tokens_estimated"] > 0


def test_attach_actual_usage_keeps_provider_total_authoritative():
    attributed = attach_actual_usage(
        {
            "operation": "v2-turn-interpreter",
            "message_plus_schema_tokens_estimated": 90,
        },
        input_tokens=100,
        output_tokens=20,
        cached_tokens=10,
        total_tokens=120,
        model="test-model",
        latency_ms=123,
        attempt_index=2,
        fallback_used=False,
    )

    assert attributed["input_tokens_actual"] == 100
    assert attributed["total_tokens_actual"] == 120
    assert attributed["provider_input_minus_estimate"] == 10
    assert attributed["retry_count"] == 1


def test_token_attribution_baseline_is_exactly_three_requested_scenarios():
    assert [case.__name__ for case in ATTRIBUTION_CASES] == [
        "case_price",
        "case_device_price",
        "case_full_booking",
    ]
