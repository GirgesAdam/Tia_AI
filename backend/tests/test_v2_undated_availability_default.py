from __future__ import annotations

from app.agents.v2.turn_contract import TiaTurnUnderstanding, TurnEntities, TurnOperation
from app.agents.v2.turn_normalization import dedupe_exact_operations


def _operation(operation_type: str) -> TurnOperation:
    return TurnOperation(
        type=operation_type,
        entities=TurnEntities(),
        selection=None,
        package_usage="unspecified",
        requested_service_details=[],
        execution_intent="informational",
        continues_previous=False,
    )


def test_undated_availability_read_defaults_to_next_available() -> None:
    normalized = dedupe_exact_operations(
        TiaTurnUnderstanding(operations=[_operation("availability")], safety_signals=[])
    )

    date = normalized.operations[0].entities.date
    assert date is not None
    assert date.mode == "next_available"
    assert date.start_date is None
    assert date.end_date is None


def test_undated_booking_is_not_given_an_implicit_date() -> None:
    normalized = dedupe_exact_operations(
        TiaTurnUnderstanding(operations=[_operation("book")], safety_signals=[])
    )

    assert normalized.operations[0].entities.date is None
