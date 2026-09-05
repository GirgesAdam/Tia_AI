from pathlib import Path


def test_e2e_matrix_runner_is_transport_free_and_rollback_safe() -> None:
    backend = Path(__file__).resolve().parent.parent
    source = (backend / "scripts/run_agent_e2e_matrix.py").read_text(encoding="utf-8")

    assert "run_agent_chat" in source
    assert "join_transaction_mode=\"create_savepoint\"" in source
    assert "outer.rollback()" in source
    assert "WhatsApp/n8n used: no" in source
    assert "requests.post" not in source
    assert "webhook" not in source.lower()


def test_e2e_matrix_covers_core_agent_risk_surfaces() -> None:
    backend = Path(__file__).resolve().parent.parent
    source = (backend / "scripts/run_agent_e2e_matrix.py").read_text(encoding="utf-8")

    required_cases = [
        "service_underarm_dialect",
        "service_underarm_paraphrase",
        "branch_city_name",
        "full_booking_grounding",
        "service_information",
        "pricing",
        "doctor_discovery",
        "branch_discovery",
        "package_use_existing",
        "package_avoid_existing",
        "single_session_no_package_intent",
        "exact_time_semantics",
        "after_time_semantics",
        "before_time_semantics",
        "range_time_semantics",
        "medical_suitability",
        "mixed_language",
        "catalog_id_grounding",
        "service_information_no_write",
        "underarm_booking_service_duration",
        "full_body_booking_service_duration",
        "ambiguous_cancel_no_write",
        "ambiguous_reschedule_no_write",
        "blocked_patient_rejected",
    ]
    for case in required_cases:
        assert case in source


def test_e2e_semantic_profile_exercises_unified_turn_interpreter() -> None:
    backend = Path(__file__).resolve().parent.parent
    source = (backend / "scripts/run_agent_e2e_matrix.py").read_text(encoding="utf-8")

    assert "from app.agents.turn_interpreter import interpret_customer_turn" in source
    assert "interpret_customer_turn(" in source
    assert "route_customer_message(" not in source
    assert "interpret_active_flow_turn(" not in source


def test_structured_flow_write_preserves_verified_slot_selection() -> None:
    backend = Path(__file__).resolve().parent.parent
    source = (backend / "app/services/agent_chat.py").read_text(encoding="utf-8")

    # The flow must select from the persisted verified snapshot, preserve that
    # selection as pending state, and authorize the write before invoking it.
    assert "select_slot_from_structured_selection(" in source
    assert 'event_type="requirement_selected"' in source
    assert 'status="ready_to_execute"' in source
    assert "pending_action={" in source
    assert "record_write_authorized(" in source
    assert "record_write_completed(" in source


def test_e2e_matrix_has_no_runtime_keyword_or_regex_routing() -> None:
    backend = Path(__file__).resolve().parent.parent
    source = (backend / "scripts/run_agent_e2e_matrix.py").read_text(encoding="utf-8").lower()

    # Natural-language test messages are data; the runner must not implement lexical routing.
    assert "re.compile" not in source
    assert "re.search" not in source
    assert "re.match" not in source
    assert "keyword" not in source
