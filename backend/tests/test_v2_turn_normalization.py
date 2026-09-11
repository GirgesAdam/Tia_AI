from app.agents.v2.turn_contract import (
    DateConstraint,
    EntityReference,
    TiaTurnUnderstanding,
    TimeConstraint,
    TurnEntities,
    TurnOperation,
)
from app.agents.v2.turn_normalization import dedupe_exact_operations


def _book_operation(*, start_time: str = "20:00", doctor_ref: str = "D1") -> TurnOperation:
    return TurnOperation(
        type="book",
        entities=TurnEntities(
            service=EntityReference(text="ليزر الإبط", ref="S1"),
            doctor=EntityReference(text="د. مريم", ref=doctor_ref),
            date=DateConstraint(mode="exact", start_date="2026-09-12"),
            time=TimeConstraint(mode="exact", start_time=start_time),
        ),
    )


def test_exact_duplicate_booking_is_kept_once() -> None:
    operation = _book_operation()
    turn = TiaTurnUnderstanding(
        operations=[operation, operation.model_copy(deep=True)],
        safety_signals=[],
    )

    normalized = dedupe_exact_operations(turn)

    assert normalized.operations == [operation]


def test_same_grounded_entities_ignore_cosmetic_entity_text_difference() -> None:
    first = _book_operation()
    second = first.model_copy(deep=True)
    second.entities.service.text = "الإبط"
    second.entities.doctor.text = "د مريم"
    turn = TiaTurnUnderstanding(operations=[first, second], safety_signals=[])

    normalized = dedupe_exact_operations(turn)

    assert normalized.operations == [first]


def test_distinct_booking_constraints_are_never_merged() -> None:
    first = _book_operation(start_time="19:00")
    second = _book_operation(start_time="20:00")
    third = _book_operation(start_time="20:00", doctor_ref="D2")
    turn = TiaTurnUnderstanding(operations=[first, second, third], safety_signals=[])

    normalized = dedupe_exact_operations(turn)

    assert normalized.operations == [first, second, third]


def test_compound_turn_preserves_reads_and_one_identical_write() -> None:
    pricing = TurnOperation(
        type="pricing",
        entities=TurnEntities(service=EntityReference(text="الإبط", ref="S1")),
        requested_service_details=["price"],
    )
    availability = TurnOperation(
        type="availability",
        entities=TurnEntities(
            service=EntityReference(text="الإبط", ref="S1"),
            doctor=EntityReference(text="د مريم", ref="D1"),
            date=DateConstraint(mode="exact", start_date="2026-09-12"),
        ),
    )
    booking = _book_operation()
    turn = TiaTurnUnderstanding(
        operations=[pricing, availability, booking, booking.model_copy(deep=True)],
        safety_signals=[],
    )

    normalized = dedupe_exact_operations(turn)

    assert [operation.type for operation in normalized.operations] == [
        "pricing",
        "availability",
        "book",
    ]
