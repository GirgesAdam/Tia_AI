from app.agents.v2.semantic_context import build_semantic_context


def test_raw_active_task_and_pending_choice_are_never_copied_to_model_input() -> None:
    canonical_service_id = "3a672050-8f8f-49b1-942a-very-internal-service-id"
    raw_active_task = {
        "constraints": {"service_id": canonical_service_id},
        "write_authorization": {
            "authorized": True,
            "operation": "booking",
            "source_turn_id": "private-turn-id",
        },
    }
    raw_pending_choice = {
        "purpose": "booking_slot",
        "option_snapshot_id": "internal-snapshot-id",
        "options": [{"appointment_id": "private-appointment-id"}],
    }

    context = build_semantic_context(
        {
            "services": [{"id": canonical_service_id, "name": "ليزر إبط"}],
            "doctors": [],
            "appointments": [],
            "packages": [],
        },
        active_task=raw_active_task,
        pending_choice=raw_pending_choice,
    )

    assert context.model_input["active_task"] == {}
    assert context.model_input["pending_choice"] == {}
    encoded = repr(context.model_input)
    assert canonical_service_id not in encoded
    assert "private-turn-id" not in encoded
    assert "internal-snapshot-id" not in encoded
    assert "private-appointment-id" not in encoded
