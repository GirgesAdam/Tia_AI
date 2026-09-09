from datetime import datetime
from types import SimpleNamespace

from langchain_core.messages import AIMessage, HumanMessage
import pytest

from app.agents.turn_interpreter import (
    _interpreter_system_prompt,
    _latest_customer_turn,
    _option_summary,
    _recent_conversation_excerpt,
    interpret_customer_turn,
)
from app.core.config import settings


SERVICE_ID = "22222222-2222-4222-8222-222222222222"
DOCTOR_ID = "11111111-1111-4111-8111-111111111111"
DATE = "2026-09-12"
PHRASE = "من ١ ونص"


def _catalog() -> dict[str, object]:
    return {
        "services": [
            {
                "id": SERVICE_ID,
                "name": "HydraFacial",
                "doctor_ids": [DOCTOR_ID],
            }
        ],
        "branches": [],
        "doctors": [
            {
                "id": DOCTOR_ID,
                "name": "د. سارة نبيل",
                "service_ids": [SERVICE_ID],
            }
        ],
    }


def _booking_flow(*, presented: bool) -> SimpleNamespace:
    option_snapshot: dict[str, object] = {}
    status = "collecting_requirements"
    if presented:
        status = "awaiting_option_selection"
        option_snapshot = {
            "date": DATE,
            "availability_windows": [
                {
                    "doctor_id": DOCTOR_ID,
                    "doctor_name": "د. سارة نبيل",
                    "start_time_24h": "13:30",
                    "end_time_24h": "15:00",
                },
                {
                    "doctor_id": DOCTOR_ID,
                    "doctor_name": "د. سارة نبيل",
                    "start_time_24h": "17:00",
                    "end_time_24h": "18:30",
                },
            ],
            "slots": [
                {
                    "doctor_id": DOCTOR_ID,
                    "doctor_name": "د. سارة نبيل",
                    "start_time_24h": "13:30",
                    "end_time_24h": "14:00",
                },
                {
                    "doctor_id": DOCTOR_ID,
                    "doctor_name": "د. سارة نبيل",
                    "start_time_24h": "14:00",
                    "end_time_24h": "14:30",
                },
            ],
        }
    return SimpleNamespace(
        is_active=True,
        flow_type="booking",
        status=status,
        capabilities=["availability_discovery", "appointment_creation"],
        entity_state={
            "service_id": SERVICE_ID,
            "doctor_id": DOCTOR_ID,
            "requested_date": DATE,
        },
        missing_information=[],
        option_snapshot=option_snapshot,
    )


def _selection_history() -> list:
    return [
        AIMessage(
            content=(
                "المتاح مع د. سارة نبيل من 1:30 م لـ3 م، ومن 5 م لـ6:30 م. "
                "قولي الوقت اللي يناسبك عشان أحجزه."
            )
        ),
        HumanMessage(content=PHRASE),
    ]


def _search_history() -> list:
    return [
        AIMessage(content="تمام، تحب المواعيد المتاحة تبدأ من الساعة كام؟"),
        HumanMessage(content=PHRASE),
    ]


def test_same_phrase_reaches_interpreter_with_different_verified_context() -> None:
    selection_history = _selection_history()
    search_history = _search_history()
    presented_flow = _booking_flow(presented=True)
    collecting_flow = _booking_flow(presented=False)

    # The customer wording is deliberately identical. Context, not the word "من",
    # is what distinguishes a slot choice from an availability lower bound.
    assert _latest_customer_turn(selection_history) == PHRASE
    assert _latest_customer_turn(search_history) == PHRASE

    selection_context = _recent_conversation_excerpt(selection_history)
    search_context = _recent_conversation_excerpt(search_history)
    assert "عشان أحجزه" in selection_context
    assert "تبدأ من الساعة كام" in search_context

    presented_options = _option_summary(presented_flow)
    collecting_options = _option_summary(collecting_flow)
    assert presented_options["availability_windows"][0]["start_time_24h"] == "13:30"
    assert collecting_options == {}


def test_semantic_contract_uses_conversation_context_not_a_time_phrase_rule() -> None:
    prompt = _interpreter_system_prompt(
        timezone_name="Africa/Cairo",
        local_now=datetime(2026, 9, 9, 13, 30),
        active_flow=True,
    )

    assert "assistant's immediately preceding question" in prompt
    assert "the customer does not need to repeat the word 'book'" in prompt
    assert "Use not_before_time/not_after_time only when the customer actually wants to search" in prompt
    assert "Never infer a time that cannot resolve against the verified presented options" in prompt


@pytest.mark.skipif(
    not settings.openai_api_key,
    reason="Live semantic regression requires OPENAI_API_KEY.",
)
def test_live_same_phrase_changes_meaning_with_conversation_context() -> None:
    local_now = datetime(2026, 9, 9, 13, 30)
    catalog = _catalog()

    selection = interpret_customer_turn(
        flow=_booking_flow(presented=True),
        history=_selection_history(),
        timezone_name="Africa/Cairo",
        local_now=local_now,
        clinic_catalog=catalog,
    )
    assert selection.action == "select_option"
    assert selection.selection_time == "13:30"
    assert selection.entity_hints.not_before_time is None
    assert "appointment_creation" in selection.capabilities

    search = interpret_customer_turn(
        flow=_booking_flow(presented=False),
        history=_search_history(),
        timezone_name="Africa/Cairo",
        local_now=local_now,
        clinic_catalog=catalog,
    )
    assert search.action == "modify"
    assert search.selection_time is None
    assert search.entity_hints.not_before_time == "13:30"
