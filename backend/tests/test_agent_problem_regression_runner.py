from pathlib import Path


def test_focused_problem_runner_contains_only_current_problem_surface() -> None:
    backend = Path(__file__).resolve().parent.parent
    source = (backend / "scripts/run_agent_problem_regression.py").read_text(encoding="utf-8")

    required = (
        "nearest_availability_question",
        "price_and_availability_question",
        "package_comparison_reply_quality",
        "price_and_nearest_availability",
        "availability_then_decide",
        "doctor_availability_then_decide",
        "explicit_conditional_booking",
        "price_plus_explicit_booking",
        "time_window_inquiry_with_service",
        "time_window_booking_with_service",
        "availability_without_service",
    )
    for case in required:
        assert case in source

    for clean_case in (
        "doctor_short_name_booking",
        "booking_after_time",
        "booking_before_time",
        "package_avoid_existing_keeps_booking",
        "mixed_language_booking_no_price_inference",
        "explicit_booking_after_time",
        "nearest_booking_request",
        "doctor_availability_question_no_booking",
        "time_range_booking",
        "time_range_availability_question",
    ):
        assert clean_case not in source


def test_focused_problem_runner_records_real_agent_reply() -> None:
    backend = Path(__file__).resolve().parent.parent
    source = (backend / "scripts/run_agent_problem_regression.py").read_text(encoding="utf-8")

    assert "run_agent_chat" in source
    assert '"reply": reply_text' in source
    assert '"reply_model": reply_model' in source
    assert '"no_unexpected_write": no_unexpected_write' in source


def test_focused_problem_runner_has_no_runtime_lexical_routing() -> None:
    backend = Path(__file__).resolve().parent.parent
    source = (backend / "scripts/run_agent_problem_regression.py").read_text(encoding="utf-8").lower()

    assert "re.compile" not in source
    assert "re.search" not in source
    assert "re.match" not in source
    assert "keyword" not in source
