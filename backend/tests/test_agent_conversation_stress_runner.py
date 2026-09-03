from datetime import datetime
from zoneinfo import ZoneInfo

from scripts.run_agent_conversation_stress import (
    _conversation_specs,
    _semantic_specs,
    _static_architecture_findings,
)


def test_stress_catalog_is_within_requested_turn_range() -> None:
    now = datetime(2026, 9, 2, 2, 30, tzinfo=ZoneInfo("Africa/Cairo"))
    semantic = _semantic_specs(now)
    values = {
        "underarm_date": "2026-09-03",
        "underarm_time": "18:00",
        "botox_date": "2026-09-04",
        "botox_time": "19:00",
    }
    conversations = _conversation_specs(values)
    e2e_turns = sum(len(case.turns) for case in conversations)
    total = len(semantic) + e2e_turns

    assert 180 <= total <= 300
    assert len(semantic) >= 100
    assert len(conversations) >= 30


def test_stress_catalog_covers_known_high_risk_agent_failures() -> None:
    values = {
        "underarm_date": "2026-09-03",
        "underarm_time": "18:00",
        "botox_date": "2026-09-04",
        "botox_time": "19:00",
    }
    names = {case.name for case in _conversation_specs(values)}
    assert {
        "nearest_available_after_5",
        "stale_reschedule_must_not_poison_booking",
        "package_remaining_sessions",
        "package_refund_quote",
        "privacy_other_customer",
        "prompt_injection",
        "long_context_topic_churn",
    }.issubset(names)


def test_static_audit_documents_architecture_gaps() -> None:
    ids = {row["id"] for row in _static_architecture_findings()}
    assert {
        "NEXT_AVAILABLE_CROSS_DATE",
        "PACKAGE_CAPABILITY_UNREACHABLE",
        "HANDOFF_ALWAYS_EXPOSED",
        "GROUNDED_COVERAGE_TOO_BROAD",
        "STALE_FLOW_CAPABILITY_INHERITANCE",
        "PACKAGE_REFUND_QUOTE_GAP",
        "INTERPRETER_MODEL_QUALITY",
    }.issubset(ids)
