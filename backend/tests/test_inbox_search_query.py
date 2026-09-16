from types import SimpleNamespace
from uuid import uuid4

from sqlalchemy.dialects import postgresql

from app.api.routes.inbox import list_inbox_conversations


class _EmptyResult:
    def all(self):
        return []


class _CaptureSession:
    def __init__(self) -> None:
        self.statement = None

    def execute(self, statement):
        self.statement = statement
        return _EmptyResult()


def test_inbox_search_filters_name_phone_and_normalized_phone() -> None:
    workspace_id = uuid4()
    access = SimpleNamespace(
        workspace=SimpleNamespace(id=workspace_id),
        user=SimpleNamespace(id=uuid4()),
    )
    db = _CaptureSession()

    result = list_inbox_conversations(
        access=access,
        db=db,
        owner_type=None,
        conversation_status=None,
        assigned_to_me=False,
        unread_only=False,
        q="Adam 0155-111",
        limit=50,
        offset=0,
    )

    assert result == []
    assert db.statement is not None
    compiled = db.statement.compile(dialect=postgresql.dialect())
    sql = str(compiled)
    assert "patients.first_name ILIKE" in sql
    assert "patients.last_name ILIKE" in sql
    assert "patients.phone ILIKE" in sql
    assert "patients.phone_normalized ILIKE" in sql
    assert "conversations.workspace_id" in sql
    assert "%0155111%" in compiled.params.values()


def test_inbox_search_escapes_like_wildcards() -> None:
    access = SimpleNamespace(
        workspace=SimpleNamespace(id=uuid4()),
        user=SimpleNamespace(id=uuid4()),
    )
    db = _CaptureSession()

    list_inbox_conversations(
        access=access,
        db=db,
        owner_type=None,
        conversation_status=None,
        assigned_to_me=False,
        unread_only=False,
        q=r"A%_\\B",
        limit=50,
        offset=0,
    )

    assert db.statement is not None
    compiled = db.statement.compile(dialect=postgresql.dialect())
    values = [value for value in compiled.params.values() if isinstance(value, str)]
    assert any(r"\%" in value and r"\_" in value for value in values)
