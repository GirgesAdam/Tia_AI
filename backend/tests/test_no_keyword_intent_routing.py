from pathlib import Path


FILES = (
    "app/agents/semantic_router.py",
    "app/agents/flow_interpreter.py",
    "app/agents/capability_policy.py",
    "app/agents/tool_selection.py",
)


def test_routing_architecture_has_no_legacy_lexical_rule_tables() -> None:
    backend = Path(__file__).resolve().parent.parent
    source = "\n".join(
        (backend / relative).read_text(encoding="utf-8")
        for relative in FILES
    )

    forbidden = (
        "_MEDICAL",
        "_BOOKING",
        "_CANCEL",
        "_CONFIRM",
        "_RESCHEDULE",
        "explicit_booking_intent",
        "select_offered_booking_slot",
        'if "حجز" in',
        "if 'حجز' in",
    )
    for token in forbidden:
        assert token not in source
