from __future__ import annotations

from app.services.agent_v2.compound_turn_policy import normalize_compound_turn_plan
from app.services.agent_v2.planner import PlanStep, ReadRequest, TurnPlan, WriteIntent


def _booking(index: int, service_id: str, *, device_key: str | None = None) -> PlanStep:
    params: dict[str, object] = {
        "service_id": service_id,
        "doctor_id": f"doctor-{index}",
        "date": {
            "mode": "exact",
            "start_date": "2026-09-20",
            "end_date": None,
        },
        "time": {
            "mode": "exact",
            "start_time": "12:00",
            "end_time": None,
            "start_time_ambiguity": "none",
            "end_time_ambiguity": "none",
        },
        "package_usage": "unspecified",
    }
    if device_key is not None:
        params["device_key"] = device_key
    return PlanStep(
        operation_index=index,
        operation_type="book",
        disposition="read",
        reads=[ReadRequest(kind="availability", parameters=dict(params))],
        write_intent=WriteIntent(
            kind="booking",
            authorized=True,
            parameters=dict(params),
        ),
        state_action="start_booking",
        response_goal="present_availability",
        facts={**params, "exact_time_requested": True},
    )


def _purchase(index: int, service_id: str, *, device_key: str | None = None) -> PlanStep:
    params: dict[str, object] = {
        "service_id": service_id,
        "package_sessions": 3,
        "package_usage": "unspecified",
    }
    if device_key is not None:
        params["device_key"] = device_key
    return PlanStep(
        operation_index=index,
        operation_type="buy_package",
        disposition="read",
        reads=[ReadRequest(kind="package_offers", parameters=dict(params))],
        write_intent=WriteIntent(kind="buy_package", authorized=True, parameters=dict(params)),
        response_goal="package_purchased",
        facts=params,
    )


def _catalog() -> dict[str, object]:
    return {
        "services": [
            {"id": "service-a", "duration_minutes": 30},
            {"id": "service-b", "duration_minutes": 45},
            {"id": "service-c", "duration_minutes": 20},
        ]
    }


def _start(step: PlanStep) -> str:
    assert step.write_intent is not None
    raw = step.write_intent.parameters["time"]
    assert isinstance(raw, dict)
    return str(raw["start_time"])


def _read_start(step: PlanStep) -> str:
    raw = step.reads[0].parameters["time"]
    assert isinstance(raw, dict)
    return str(raw["start_time"])


def test_same_anchor_bookings_are_scheduled_back_to_back_in_customer_order() -> None:
    plan = TurnPlan(
        steps=[
            _booking(0, "service-a"),
            _booking(1, "service-b"),
            _booking(2, "service-c"),
        ]
    )

    normalized = normalize_compound_turn_plan(plan, catalog=_catalog())

    assert [_start(step) for step in normalized.steps] == ["12:00", "12:30", "13:15"]
    assert [_read_start(step) for step in normalized.steps] == ["12:00", "12:30", "13:15"]
    assert all(step.facts["compound_visit_sequenced"] is True for step in normalized.steps)


def test_booking_before_same_package_purchase_is_reordered_and_made_package_required() -> None:
    plan = TurnPlan(
        steps=[
            _booking(0, "service-a", device_key="prime"),
            _purchase(1, "service-a", device_key="prime"),
        ]
    )

    normalized = normalize_compound_turn_plan(plan, catalog=_catalog())

    assert [step.operation_index for step in normalized.steps] == [1, 0]
    booking = normalized.steps[1]
    assert booking.write_intent is not None
    assert booking.write_intent.parameters["package_usage"] == "use_existing"
    assert booking.facts["depends_on_package_purchase_operation_index"] == 1


def test_package_for_different_service_does_not_become_booking_dependency() -> None:
    plan = TurnPlan(
        steps=[
            _booking(0, "service-a", device_key="prime"),
            _purchase(1, "service-b", device_key="prime"),
        ]
    )

    normalized = normalize_compound_turn_plan(plan, catalog=_catalog())

    assert [step.operation_index for step in normalized.steps] == [0, 1]
    booking = normalized.steps[0]
    assert booking.write_intent is not None
    assert booking.write_intent.parameters["package_usage"] == "unspecified"
    assert "depends_on_package_purchase_operation_index" not in booking.facts


def test_package_for_different_device_does_not_become_booking_dependency() -> None:
    plan = TurnPlan(
        steps=[
            _booking(0, "service-a", device_key="prime"),
            _purchase(1, "service-a", device_key="candela"),
        ]
    )

    normalized = normalize_compound_turn_plan(plan, catalog=_catalog())

    assert [step.operation_index for step in normalized.steps] == [0, 1]
    booking = normalized.steps[0]
    assert booking.write_intent is not None
    assert booking.write_intent.parameters["package_usage"] == "unspecified"


def test_different_requested_anchors_are_not_retimed() -> None:
    first = _booking(0, "service-a")
    second = _booking(1, "service-b")
    assert second.write_intent is not None
    second_time = {
        **second.write_intent.parameters["time"],
        "start_time": "14:00",
    }
    second = second.model_copy(
        update={
            "reads": [
                second.reads[0].model_copy(
                    update={
                        "parameters": {
                            **second.reads[0].parameters,
                            "time": second_time,
                        }
                    }
                )
            ],
            "write_intent": second.write_intent.model_copy(
                update={
                    "parameters": {
                        **second.write_intent.parameters,
                        "time": second_time,
                    }
                }
            ),
            "facts": {**second.facts, "time": second_time},
        }
    )

    normalized = normalize_compound_turn_plan(
        TurnPlan(steps=[first, second]),
        catalog=_catalog(),
    )

    assert [_start(step) for step in normalized.steps] == ["12:00", "14:00"]
    assert all("compound_visit_sequenced" not in step.facts for step in normalized.steps)
