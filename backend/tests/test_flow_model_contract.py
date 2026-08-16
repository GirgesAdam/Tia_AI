from app.models.conversation_flow_state import (
    FLOW_STATUSES,
    FLOW_TYPES,
)


def test_flow_types_are_explicit_and_small() -> None:
    assert FLOW_TYPES == ("booking", "appointment_reschedule")


def test_flow_terminal_statuses_exist() -> None:
    for status in ("completed", "cancelled", "interrupted", "expired"):
        assert status in FLOW_STATUSES
