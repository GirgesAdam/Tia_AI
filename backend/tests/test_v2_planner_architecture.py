from pathlib import Path


def test_v2_planner_has_no_raw_customer_language_or_lexical_routing() -> None:
    backend = Path(__file__).resolve().parent.parent
    source = (backend / "app/services/agent_v2/planner.py").read_text(encoding="utf-8").lower()

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
        'if "باكيدج" in',
        'if "حامل" in',
    )
    for token in forbidden:
        assert token not in source


def test_v2_planner_is_pure_business_logic_without_llm_or_database_runtime() -> None:
    backend = Path(__file__).resolve().parent.parent
    source = (backend / "app/services/agent_v2/planner.py").read_text(encoding="utf-8").lower()

    assert "langchain" not in source
    assert "openai" not in source
    assert "sqlalchemy" not in source
    assert "session" not in source
    assert "invoke_model" not in source
    assert "@tool" not in source


def test_v2_planner_receives_only_structured_turn_and_context() -> None:
    backend = Path(__file__).resolve().parent.parent
    source = (backend / "app/services/agent_v2/planner.py").read_text(encoding="utf-8")

    assert "def plan_turn(turn: TiaTurnUnderstanding, context: PlannerContext)" in source
    assert "SemanticContext" in source
    assert "ActiveTaskState" in source
