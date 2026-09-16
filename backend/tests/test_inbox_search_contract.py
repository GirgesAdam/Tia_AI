from pathlib import Path


INBOX_ROUTE = Path(__file__).parents[1] / "app" / "api" / "routes" / "inbox.py"


def test_inbox_conversation_list_supports_workspace_scoped_patient_search() -> None:
    source = INBOX_ROUTE.read_text(encoding="utf-8")

    assert "q: Annotated[str | None, Query(max_length=120)] = None" in source
    assert "Patient.first_name.ilike(pattern, escape=\\\"\\\\\\\")" in source
    assert "Patient.last_name.ilike(pattern, escape=\\\"\\\\\\\")" in source
    assert "Patient.phone.ilike(pattern, escape=\\\"\\\\\\\")" in source
    assert "Patient.phone_normalized.ilike(phone_pattern, escape=\\\"\\\\\\\")" in source
    assert "Conversation.workspace_id == access.workspace.id" in source
