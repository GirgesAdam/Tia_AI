from pathlib import Path

from app.agents.semantic_router import SemanticEntityHints
from app.agents.turn_interpreter import UnifiedTurnDecision
from app.core.config import Settings

BASE = {
    "DATABASE_URL": "postgresql+psycopg://user:pass@localhost:5432/db",
    "MIGRATION_DATABASE_URL": "postgresql+psycopg://user:pass@localhost:5432/db",
    "SUPABASE_URL": "https://abcdefghijklmnop.supabase.co",
    "SUPABASE_PUBLISHABLE_KEY": "sb_publishable_test",
    "SUPABASE_SECRET_KEY": "sb_secret_test",
}


def _decision(**overrides):
    values = {
        "domains": ["booking"],
        "capabilities": ["availability_discovery", "appointment_creation"],
        "risk_flags": [],
        "flow_signal": "start_booking",
        "action": "continue",
        "entity_hints": SemanticEntityHints(
            service_query="ليزر إزالة الشعر",
            branch_query="مدينة نصر",
            doctor_query="احمد محمود",
            requested_date="2026-08-25",
            not_before_time="18:00",
            not_after_time="18:00",
            appointment_reference=None,
        ),
        "clear_entity_fields": [],
        "selection_index": None,
        "selection_time": None,
        "missing_information": [],
        "recommended_handoff_category": "other",
        "recommended_handoff_priority": "normal",
        "confidence": 0.98,
        "reason": "Booking availability request.",
    }
    values.update(overrides)
    return UnifiedTurnDecision(**values)


def test_unified_decision_adapts_to_existing_policy_contract() -> None:
    turn = _decision()
    semantic = turn.as_semantic_decision()

    assert semantic.capabilities == ["availability_discovery", "appointment_creation"]
    assert semantic.entity_hints.requested_date == "2026-08-25"
    assert semantic.flow_signal == "start_booking"


def test_unified_decision_adapts_to_existing_flow_contract() -> None:
    turn = _decision(
        action="modify",
        flow_signal="none",
        clear_entity_fields=["not_before_time", "not_after_time"],
    )
    flow_turn = turn.as_flow_turn_decision()

    assert flow_turn.action == "modify"
    assert flow_turn.clear_entity_fields == ["not_before_time", "not_after_time"]
    assert flow_turn.entity_hints.service_query == "ليزر إزالة الشعر"


def test_unified_interpreter_is_default_with_rollback_flag(monkeypatch) -> None:
    for key, value in BASE.items():
        monkeypatch.setenv(key, value)
    monkeypatch.delenv("AGENT_UNIFIED_TURN_INTERPRETER_ENABLED", raising=False)

    settings = Settings(_env_file=None)
    assert settings.agent_unified_turn_interpreter_enabled is True

    monkeypatch.setenv("AGENT_UNIFIED_TURN_INTERPRETER_ENABLED", "false")
    settings = Settings(_env_file=None)
    assert settings.agent_unified_turn_interpreter_enabled is False


def test_agent_chat_has_one_unified_semantic_stage() -> None:
    backend = Path(__file__).resolve().parent.parent
    source = (backend / "app/services/agent_chat.py").read_text(encoding="utf-8")

    assert 'semantic_stage = "unified-turn-interpreter"' in source
    assert "interpret_customer_turn(" in source


def test_unified_interpreter_contains_no_keyword_intent_shortcuts() -> None:
    backend = Path(__file__).resolve().parent.parent
    source = (backend / "app/agents/turn_interpreter.py").read_text(encoding="utf-8")

    forbidden = (
        'if "حجز" in',
        "if 'حجز' in",
        'if "الغاء" in',
        "if 'الغاء' in",
        "keyword",
        "regex",
    )
    for token in forbidden:
        assert token not in source.lower()
