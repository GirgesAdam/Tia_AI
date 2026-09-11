from pathlib import Path


STATE_FILES = (
    "app/services/agent_v2/state.py",
    "app/services/agent_v2/state_rules.py",
    "app/services/agent_v2/outcome.py",
)


def test_v2_business_state_layer_has_no_customer_language_routing_surface() -> None:
    backend = Path(__file__).resolve().parent.parent
    source = "\n".join(
        (backend / relative).read_text(encoding="utf-8").lower()
        for relative in STATE_FILES
    )

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


def test_v2_state_layer_does_not_import_llm_or_langchain_runtime() -> None:
    backend = Path(__file__).resolve().parent.parent
    source = "\n".join(
        (backend / relative).read_text(encoding="utf-8").lower()
        for relative in STATE_FILES
    )

    assert "langchain" not in source
    assert "openai" not in source
    assert "invoke_model" not in source
    assert "structured_output" not in source


def test_v2_outcome_is_not_a_customer_copy_container() -> None:
    backend = Path(__file__).resolve().parent.parent
    source = (backend / "app/services/agent_v2/outcome.py").read_text(encoding="utf-8")

    assert "customer_reply" not in source
    assert "response_text" not in source
    assert "reply_text" not in source
