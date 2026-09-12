from pathlib import Path


def test_v2_read_executor_has_no_customer_language_or_lexical_semantics() -> None:
    backend = Path(__file__).resolve().parent.parent
    source = (backend / "app/services/agent_v2/read_executor.py").read_text(
        encoding="utf-8"
    ).lower()

    forbidden = (
        "customer_message",
        "latest_customer_turn",
        "raw_message",
        "raw_text",
        "re.compile",
        "re.search",
        "re.match",
        "difflib.",
        "rapidfuzz",
        "fuzzywuzzy",
        'if "حجز" in',
        "if 'حجز' in",
        'if "الغاء" in',
        'if "إلغاء" in',
    )
    for token in forbidden:
        assert token not in source


def test_v2_read_executor_contains_no_write_execution_surface() -> None:
    backend = Path(__file__).resolve().parent.parent
    source = (backend / "app/services/agent_v2/read_executor.py").read_text(
        encoding="utf-8"
    ).lower()

    forbidden = (
        ".commit(",
        ".flush(",
        ".add(",
        "create_appointment(",
        "confirm_appointment(",
        "cancel_appointment(",
        "reschedule_appointment(",
        "purchase_package_offer(",
        "create_patient_package(",
        "cancel_patient_package_with_refund(",
        "update_marketing_consent",
        "create_follow_up_task",
    )
    for token in forbidden:
        assert token not in source


def test_v2_read_executor_does_not_call_llm_or_tool_runtime() -> None:
    backend = Path(__file__).resolve().parent.parent
    source = (backend / "app/services/agent_v2/read_executor.py").read_text(
        encoding="utf-8"
    ).lower()

    assert "langchain" not in source
    assert "openai" not in source
    assert "invoke_model" not in source
    assert "@tool" not in source
