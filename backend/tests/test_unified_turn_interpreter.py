from datetime import datetime
from pathlib import Path
from types import SimpleNamespace

from langchain_core.messages import AIMessage, HumanMessage

from app.agents.semantic_router import SemanticEntityHints
from app.agents.turn_interpreter import (
    UnifiedTurnDecision,
    _interpreter_system_prompt,
    _latest_customer_turn,
    _normalize_active_booking_decision,
    _recent_conversation_excerpt,
)
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
        "package_intent": "none",
        "action": "continue",
        "entity_hints": SemanticEntityHints(
            service_query="ليزر إزالة الشعر",
            branch_query="مدينة نصر",
            doctor_query="احمد محمود",
            requested_date="2026-08-25",
            requested_start_time="18:00",
            not_before_time=None,
            not_after_time=None,
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
    assert semantic.entity_hints.requested_start_time == "18:00"
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


def test_unified_interpreter_remains_default(monkeypatch) -> None:
    for key, value in BASE.items():
        monkeypatch.setenv(key, value)
    monkeypatch.delenv("AGENT_UNIFIED_TURN_INTERPRETER_ENABLED", raising=False)

    settings = Settings(_env_file=None)
    assert settings.agent_unified_turn_interpreter_enabled is True


def test_recent_context_is_bounded_and_latest_turn_is_authoritative() -> None:
    history = [
        HumanMessage(content="عايز أعرف سعر الليزر"),
        AIMessage(content="أي منطقة؟"),
        HumanMessage(content="full body"),
        AIMessage(content="السعر كذا"),
        HumanMessage(content="طب عندي باكدج قديمة؟"),
        AIMessage(content="هراجعها"),
        HumanMessage(content="لا أنا عايز أشتري باكدج للوش"),
    ]

    excerpt = _recent_conversation_excerpt(history, max_messages=4)
    assert "عايز أعرف سعر الليزر" not in excerpt
    assert "طب عندي باكدج قديمة؟" in excerpt
    assert "لا أنا عايز أشتري باكدج للوش" not in excerpt
    assert excerpt.count("customer:") + excerpt.count("assistant:") == 4
    assert _latest_customer_turn(history) == "لا أنا عايز أشتري باكدج للوش"


def test_slot_selection_contract_distinguishes_booking_choice_from_search_filter() -> None:
    prompt = _interpreter_system_prompt(
        timezone_name="Africa/Cairo",
        local_now=datetime(2026, 9, 9, 12, 0),
        active_flow=True,
    )

    assert "distinguish semantically between selecting an appointment start and changing the availability search" in prompt
    assert "including by referring to the start or beginning of a presented period" in prompt
    assert "Use not_before_time/not_after_time only when the customer actually wants to search" in prompt
    assert "the customer does not need to repeat the word 'book'" in prompt


def test_presented_window_start_choice_normalizes_to_exact_slot() -> None:
    doctor_id = "11111111-1111-1111-1111-111111111111"
    flow = SimpleNamespace(
        is_active=True,
        flow_type="booking",
        entity_state={"service_id": "22222222-2222-2222-2222-222222222222"},
        option_snapshot={
            "date": "2026-09-12",
            "availability_windows": [
                {
                    "doctor_id": doctor_id,
                    "doctor_name": "د. سارة نبيل",
                    "start_time_24h": "13:30",
                    "end_time_24h": "15:00",
                },
                {
                    "doctor_id": doctor_id,
                    "doctor_name": "د. سارة نبيل",
                    "start_time_24h": "17:00",
                    "end_time_24h": "18:30",
                },
            ],
            "slots": [
                {
                    "doctor_id": doctor_id,
                    "doctor_name": "د. سارة نبيل",
                    "start_time_24h": "13:30",
                    "end_time_24h": "14:00",
                },
                {
                    "doctor_id": doctor_id,
                    "doctor_name": "د. سارة نبيل",
                    "start_time_24h": "14:00",
                    "end_time_24h": "14:30",
                },
            ],
        },
    )
    hints = SemanticEntityHints(
        service_query="HydraFacial",
        service_id="22222222-2222-2222-2222-222222222222",
        branch_query=None,
        doctor_query="د. سارة نبيل",
        doctor_id=doctor_id,
        requested_date="2026-09-12",
        requested_start_time=None,
        not_before_time=None,
        not_after_time=None,
        appointment_reference=None,
    )
    decision = _decision(
        action="select_option",
        flow_signal="none",
        entity_hints=hints,
        selection_time="13:30",
        reason="Customer chose the beginning of the presented period as the appointment start.",
    )

    normalized = _normalize_active_booking_decision(decision, flow)

    assert normalized.action == "select_option"
    assert normalized.selection_time == "13:30"
    assert normalized.entity_hints.not_before_time is None
    assert "appointment_creation" in normalized.capabilities


def test_search_from_time_remains_a_filter_not_a_slot_choice() -> None:
    flow = SimpleNamespace(
        is_active=True,
        flow_type="booking",
        entity_state={"service_id": "33333333-3333-3333-3333-333333333333"},
        option_snapshot={
            "date": "2026-09-15",
            "availability_windows": [
                {
                    "doctor_id": "44444444-4444-4444-4444-444444444444",
                    "doctor_name": "د. يوسف فؤاد",
                    "start_time_24h": "11:00",
                    "end_time_24h": "12:30",
                },
                {
                    "doctor_id": "44444444-4444-4444-4444-444444444444",
                    "doctor_name": "د. يوسف فؤاد",
                    "start_time_24h": "16:00",
                    "end_time_24h": "18:00",
                },
            ],
            "slots": [],
        },
    )
    hints = SemanticEntityHints(
        service_query="تنظيف بشرة عميق",
        service_id="33333333-3333-3333-3333-333333333333",
        branch_query=None,
        doctor_query="د. يوسف فؤاد",
        doctor_id="44444444-4444-4444-4444-444444444444",
        requested_date="2026-09-15",
        requested_start_time=None,
        not_before_time="11:00",
        not_after_time=None,
        appointment_reference=None,
    )
    decision = _decision(
        action="modify",
        flow_signal="none",
        capabilities=["availability_discovery"],
        entity_hints=hints,
        selection_time=None,
        reason="Customer wants availability from 11:00 onward rather than selecting 11:00.",
    )

    normalized = _normalize_active_booking_decision(decision, flow)

    assert normalized.action == "modify"
    assert normalized.selection_time is None
    assert normalized.entity_hints.not_before_time == "11:00"
    assert "appointment_creation" not in normalized.capabilities


def test_agent_chat_has_one_unified_semantic_stage() -> None:
    backend = Path(__file__).resolve().parent.parent
    source = (backend / "app/services/agent_chat.py").read_text(encoding="utf-8")

    assert 'semantic_stage = "unified-turn-interpreter"' in source
    assert "interpret_customer_turn(" in source


def test_unified_interpreter_contains_no_lexical_intent_shortcuts() -> None:
    backend = Path(__file__).resolve().parent.parent
    source = (backend / "app/agents/turn_interpreter.py").read_text(encoding="utf-8").lower()

    forbidden = (
        'if "حجز" in',
        "if 'حجز' in",
        'if "الغاء" in',
        "if 'الغاء' in",
        "key" + "word",
        "reg" + "ex",
    )
    for token in forbidden:
        assert token not in source
