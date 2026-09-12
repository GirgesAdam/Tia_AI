from app.services.agent_v2.outcome import TurnOutcome


def test_completed_package_purchase_gets_explicit_action_receipt() -> None:
    outcome = TurnOutcome(
        status="completed",
        response_goal="package_purchased",
        action_result={"ok": True},
    )

    assert outcome.action_result == {
        "ok": True,
        "completed": True,
        "action": "buy_package",
    }


def test_completed_booking_gets_same_generic_action_receipt_shape() -> None:
    outcome = TurnOutcome(
        status="completed",
        response_goal="booking_completed",
        action_result={"ok": True},
    )

    assert outcome.action_result["completed"] is True
    assert outcome.action_result["action"] == "booking"


def test_non_completed_outcome_does_not_get_action_receipt() -> None:
    outcome = TurnOutcome(
        status="answered",
        response_goal="package_information",
        action_result={},
    )

    assert "completed" not in outcome.action_result
    assert "action" not in outcome.action_result
