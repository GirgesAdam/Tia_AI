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
        "full_booking_grounding",
        "service_information",
        "pricing",
        "doctor_discovery",
        "branch_discovery",
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


def test_e2e_matrix_has_no_runtime_keyword_or_regex_routing() -> None:
    backend = Path(__file__).resolve().parent.parent
    source = (backend / "scripts/run_agent_e2e_matrix.py").read_text(encoding="utf-8").lower()

    # Natural-language test messages are data; the runner must not implement lexical routing.
    assert "re.compile" not in source
    assert "re.search" not in source
    assert "re.match" not in source
    assert "keyword" not in source
