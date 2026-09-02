from types import SimpleNamespace

from app.agents.flow_interpreter import FlowTurnDecision
from app.agents.semantic_router import SemanticEntityHints
from app.services.agent_chat import _merge_flow_entity_state, _turn_is_local_side_read


def _hints(**overrides):
    values = {
        "service_query": None,
        "branch_query": None,
        "doctor_query": None,
        "service_id": None,
        "service_candidate_ids": [],
        "branch_id": None,
        "branch_candidate_ids": [],
        "doctor_id": None,
        "doctor_candidate_ids": [],
        "requested_date": None,
        "requested_start_time": None,
        "not_before_time": None,
        "not_after_time": None,
        "appointment_reference": None,
    }
    values.update(overrides)
    return SemanticEntityHints(**values)


def _turn(*, hints, clear_entity_fields=None, capabilities=None, action="continue"):
    return FlowTurnDecision(
        action=action,
        capabilities=capabilities or [],
        risk_flags=[],
        entity_hints=hints,
        clear_entity_fields=clear_entity_fields or [],
        selection_index=None,
        selection_time=None,
        missing_information=[],
        recommended_handoff_category="other",
        recommended_handoff_priority="normal",
        confidence=1.0,
        reason="test",
    )


def test_empty_candidate_defaults_do_not_mutate_existing_flow_state():
    existing = {
        "service_query": "ليزر إزالة الشعر",
        "requested_date": "2026-08-25",
        "not_before_time": "18:00",
        "not_after_time": "18:00",
    }

    merged = _merge_flow_entity_state(existing, _turn(hints=_hints()))

    assert merged == existing


def test_selected_catalog_id_removes_stale_candidates():
    existing = {"service_candidate_ids": ["service-a", "service-b"]}
    merged = _merge_flow_entity_state(
        existing,
        _turn(hints=_hints(service_id="service-a")),
    )

    assert merged["service_id"] == "service-a"
    assert "service_candidate_ids" not in merged


def test_nonempty_candidates_remove_stale_selected_id():
    existing = {"service_id": "service-old"}

    merged = _merge_flow_entity_state(
        existing,
        _turn(hints=_hints(service_candidate_ids=["service-a", "service-b"])),
    )
    assert merged["service_candidate_ids"] == ["service-a", "service-b"]
    assert "service_id" not in merged


def test_read_only_side_question_is_turn_local_during_booking() -> None:
    flow = SimpleNamespace(
        flow_type="booking",
        entity_state={
            "service_id": "underarm",
            "requested_date": "2026-09-03",
        },
    )

    turn = _turn(
        hints=_hints(
            service_id="prp",
            service_query="PRP للبشرة",
        ),
        capabilities=[
            "pricing",
            "service_information",
        ],
    )

    assert _turn_is_local_side_read(flow, turn) is True


def test_explicit_booking_change_is_not_treated_as_side_read() -> None:
    flow = SimpleNamespace(
        flow_type="booking",
    )

    turn = _turn(
        hints=_hints(
            service_id="full-body",
            service_query="full body",
        ),
        capabilities=[
            "availability_discovery",
            "appointment_creation",
        ],
        action="modify",
    )

    assert _turn_is_local_side_read(flow, turn) is False


def test_operational_booking_turn_inside_reschedule_is_not_side_read() -> None:
    flow = SimpleNamespace(
        flow_type="appointment_reschedule",
    )

    turn = _turn(
        hints=_hints(
            requested_date="2026-09-03",
        ),
        capabilities=[
            "availability_discovery",
            "appointment_creation",
        ],
        action="continue",
    )

    assert _turn_is_local_side_read(flow, turn) is False
