from __future__ import annotations

import json
from datetime import datetime

from langchain_core.messages import AIMessage, HumanMessage, SystemMessage

from app.agents.v2.semantic_context import (
    SemanticContext,
    build_semantic_context,
    ground_turn_references,
)
from app.agents.v2.turn_contract import (
    DateConstraint,
    EntityReference,
    TiaTurnUnderstanding,
    TurnEntities,
    TurnOperation,
)
from app.agents.v2.turn_interpreter import (
    _build_interpreter_messages,
    merge_verified_read_context,
)


def _catalog() -> dict[str, object]:
    return {
        "services": [
            {
                "id": "11111111-1111-4111-8111-111111111111",
                "name": "ليزر إبط",
                "category": "laser",
                "requires_laser_device": True,
                "laser_devices": [
                    {"device_key": "candela_gentle", "device_name": "Candela Gentle"}
                ],
            }
        ],
        "doctors": [
            {
                "id": "22222222-2222-4222-8222-222222222222",
                "name": "مريم",
                "service_ids": ["11111111-1111-4111-8111-111111111111"],
            }
        ],
        "appointments": [
            {
                "appointment_id": "33333333-3333-4333-8333-333333333333",
                "service_id": "11111111-1111-4111-8111-111111111111",
                "doctor_id": "22222222-2222-4222-8222-222222222222",
                "status": "confirmed",
                "start_local": "2026-09-17T19:00:00+03:00",
            }
        ],
    }


def _context_with_verified_availability(*, option_count: int) -> SemanticContext:
    context = build_semantic_context(_catalog())
    return SemanticContext(
        model_input={
            **context.model_input,
            "recent_verified_read": {
                "operation_type": "availability",
                "service_ref": "S1",
                "date": {
                    "mode": "range",
                    "start_date": "2026-09-12",
                    "end_date": "2026-09-14",
                },
                "availability_option_count": option_count,
                "availability_found": option_count > 0,
            },
        },
        reference_map=context.reference_map,
    )


def _next_available_turn(*, condition: str) -> TiaTurnUnderstanding:
    return TiaTurnUnderstanding(
        operations=[
            TurnOperation(
                type="availability",
                entities=TurnEntities(date=DateConstraint(mode="next_available")),
                selection=None,
                package_usage="unspecified",
                continues_previous=True,
                continuation_condition=condition,
            )
        ],
        safety_signals=[],
    )


def test_semantic_context_hides_canonical_ids_and_keeps_ephemeral_refs() -> None:
    context = build_semantic_context(_catalog())
    serialized = json.dumps(context.model_input, ensure_ascii=False)

    assert "11111111-1111-4111-8111-111111111111" not in serialized
    assert "22222222-2222-4222-8222-222222222222" not in serialized
    assert "33333333-3333-4333-8333-333333333333" not in serialized
    assert context.resolve("S1", expected_kind="service") == (
        "11111111-1111-4111-8111-111111111111"
    )
    assert context.resolve("D1", expected_kind="doctor") == (
        "22222222-2222-4222-8222-222222222222"
    )
    assert context.resolve("A1", expected_kind="appointment") == (
        "33333333-3333-4333-8333-333333333333"
    )


def test_interpreter_messages_preserve_native_conversation_roles() -> None:
    context = build_semantic_context(_catalog(), active_task={"type": "booking"})
    history = [
        HumanMessage(content="عايزة أحجز جلسة"),
        AIMessage(content="تمام، أنهي خدمة؟"),
        HumanMessage(content="ليزر الإبط"),
    ]
    messages = _build_interpreter_messages(
        history=history,
        semantic_context=context,
        timezone_name="Africa/Cairo",
        local_now=datetime.fromisoformat("2026-09-11T15:00:00+03:00"),
    )

    assert isinstance(messages[0], SystemMessage)
    assert isinstance(messages[1], SystemMessage)
    assert isinstance(messages[2], HumanMessage)
    assert isinstance(messages[3], AIMessage)
    assert isinstance(messages[4], HumanMessage)
    assert messages[4].content == "ليزر الإبط"


def test_invented_or_wrong_kind_refs_are_removed_without_text_recovery() -> None:
    context = build_semantic_context(_catalog())
    turn = TiaTurnUnderstanding(
        operations=[
            TurnOperation(
                type="book",
                entities=TurnEntities(
                    service=EntityReference(text="ليزر الإبط", ref="D1", candidate_refs=["S99"])
                ),
                selection=None,
                package_usage="unspecified",
            )
        ],
        safety_signals=[],
    )

    grounded = ground_turn_references(turn, context)
    entity = grounded.operations[0].entities.service
    assert entity is not None
    assert entity.text == "ليزر الإبط"
    assert entity.ref is None
    assert entity.candidate_refs == []


def test_conditional_fallback_keeps_verified_date_when_previous_availability_succeeded() -> None:
    merged = merge_verified_read_context(
        _next_available_turn(condition="if_previous_no_availability"),
        _context_with_verified_availability(option_count=2),
    )

    date = merged.operations[0].entities.date
    assert date is not None
    assert date.mode == "range"
    assert date.start_date == "2026-09-12"
    assert date.end_date == "2026-09-14"


def test_conditional_fallback_activates_when_previous_availability_was_empty() -> None:
    merged = merge_verified_read_context(
        _next_available_turn(condition="if_previous_no_availability"),
        _context_with_verified_availability(option_count=0),
    )

    date = merged.operations[0].entities.date
    assert date is not None
    assert date.mode == "next_available"


def test_unconditional_nearest_request_is_not_suppressed_by_previous_success() -> None:
    merged = merge_verified_read_context(
        _next_available_turn(condition="always"),
        _context_with_verified_availability(option_count=2),
    )

    date = merged.operations[0].entities.date
    assert date is not None
    assert date.mode == "next_available"
