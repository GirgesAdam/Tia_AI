from types import SimpleNamespace

import pytest

from tools.agent_eval.harness import TokenUsage, assert_demo_only
from tools.agent_eval.run_batch_01 import _reschedule_relationships_moved


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
