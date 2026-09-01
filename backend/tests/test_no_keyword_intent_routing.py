from pathlib import Path

FILES = (
    "app/agents/semantic_router.py",
    "app/agents/flow_interpreter.py",
    "app/agents/turn_interpreter.py",
    "app/agents/clinic_grounding.py",
    "app/agents/grounded_response.py",
    "app/agents/capability_policy.py",
    "app/agents/tool_selection.py",
)


def test_routing_architecture_has_no_legacy_lexical_rule_tables() -> None:
    backend = Path(__file__).resolve().parent.parent
    source = "\n".join((backend / relative).read_text(encoding="utf-8") for relative in FILES)

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


def test_grounded_runtime_does_not_use_regex_or_lexical_matching() -> None:
    backend = Path(__file__).resolve().parent.parent
    grounding = (backend / "app/agents/clinic_grounding.py").read_text(encoding="utf-8").lower()
    response = (backend / "app/agents/grounded_response.py").read_text(encoding="utf-8").lower()
    agent_chat = (backend / "app/services/agent_chat.py").read_text(encoding="utf-8")

    for token in ("re.compile", "re.search", "re.match", "difflib."):
        assert token not in grounding
        assert token not in response

    # Grounded booking calls are exact-ID based. Legacy *_search arguments remain
    # only behind grounded_mode=False for rollback compatibility.
    assert 'if grounded_mode:' in agent_chat
    assert '"service_id": service_id' in agent_chat
    assert '"branch_id": branch_id' in agent_chat
    assert '"doctor_id": doctor_id' in agent_chat
