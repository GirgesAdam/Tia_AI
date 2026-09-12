from __future__ import annotations

from types import SimpleNamespace

from app.agents.v2.semantic_context import build_semantic_context
from app.agents.v2.semantic_state_view import with_safe_read_context
from app.services.agent_v2.live_chat import _availability_option_count_for_step


def test_safe_read_context_exposes_only_verified_availability_summary() -> None:
    context = build_semantic_context(
        {
            "services": [{"id": "service-1", "name": "استشارة"}],
            "doctors": [],
            "branches": [],
        }
    )
    safe = with_safe_read_context(
        context,
        read_context={
            "operation_type": "availability",
            "service_id": "service-1",
            "availability_option_count": 4,
            "internal_note": "never expose",
        },
    )

    recent = safe.model_input["recent_verified_read"]
    assert recent["service_ref"] == "S1"
    assert recent["availability_option_count"] == 4
    assert recent["availability_found"] is True
    assert "internal_note" not in recent


def test_zero_verified_options_is_exposed_as_false_condition() -> None:
    context = build_semantic_context(
        {"services": [{"id": "service-1", "name": "استشارة"}], "doctors": [], "branches": []}
    )
    safe = with_safe_read_context(
        context,
        read_context={
            "operation_type": "availability",
            "service_id": "service-1",
            "availability_option_count": 0,
        },
    )

    recent = safe.model_input["recent_verified_read"]
    assert recent["availability_option_count"] == 0
    assert recent["availability_found"] is False


def test_live_context_reads_option_count_from_matching_outcome_only() -> None:
    turn = SimpleNamespace(
        traces=(
            SimpleNamespace(
                operation_index=0,
                outcome=SimpleNamespace(
                    facts={"availability": {"available_option_count": 7}}
                ),
            ),
        )
    )

    assert _availability_option_count_for_step(turn, operation_index=0) == 7
    assert _availability_option_count_for_step(turn, operation_index=1) is None
