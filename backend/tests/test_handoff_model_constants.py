from app.models.handoff_request import (
    HANDOFF_CATEGORIES,
    HANDOFF_PRIORITIES,
    HANDOFF_STATUSES,
)


def test_handoff_state_machine_values_are_stable() -> None:
    assert HANDOFF_STATUSES == ("pending", "claimed", "resolved")
    assert "medical" in HANDOFF_CATEGORIES
    assert "customer_request" in HANDOFF_CATEGORIES
    assert HANDOFF_PRIORITIES == ("low", "normal", "high", "urgent")
