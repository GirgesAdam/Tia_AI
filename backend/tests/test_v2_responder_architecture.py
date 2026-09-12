from pathlib import Path


def test_v2_responder_is_language_only_and_has_no_execution_dependencies() -> None:
    backend = Path(__file__).resolve().parent.parent
    source = (backend / "app/agents/v2/responder.py").read_text(encoding="utf-8").lower()

    forbidden = (
        "sqlalchemy",
        "session",
        "clinic_tools",
        "toolmessage",
        "get_clinic_adapter",
        "create_appointment",
        "cancel_appointment",
        "reschedule_appointment",
        "purchase_package",
        "db.commit",
        "db.flush",
        "db.add",
    )
    for token in forbidden:
        assert token not in source


def test_v2_responder_uses_customer_visible_outcome_boundary() -> None:
    backend = Path(__file__).resolve().parent.parent
    source = (backend / "app/agents/v2/responder.py").read_text(encoding="utf-8")

    assert "customer_visible_outcome" in source
    assert "TURN_OUTCOMES" in source
    assert "_native_recent_messages" in source
