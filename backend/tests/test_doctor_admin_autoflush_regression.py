from types import SimpleNamespace
from uuid import uuid4

from app.api.routes import doctor_admin


class _Result:
    def __init__(self, row):
        self._row = row

    def first(self):
        return self._row


class _NoAutoflushSession:
    """Minimal session double that only exposes rows after an explicit flush."""

    def __init__(self, branch):
        self.branch = branch
        self.pending = []
        self.persisted = []
        self.flush_calls = 0

    def execute(self, _statement):
        if self.persisted:
            return _Result((self.persisted[0], self.branch))
        return _Result(None)

    def add(self, value):
        self.pending.append(value)

    def flush(self):
        self.flush_calls += 1
        self.persisted.extend(self.pending)
        self.pending.clear()


def test_operational_branch_is_visible_to_second_lookup_without_autoflush(monkeypatch) -> None:
    workspace = SimpleNamespace(id=uuid4(), name="Regression Clinic")
    branch = SimpleNamespace(id=uuid4())
    doctor_id = uuid4()
    db = _NoAutoflushSession(branch)

    def resolve_branch(_db, _workspace):
        return branch

    monkeypatch.setattr(doctor_admin, "_operational_branch", resolve_branch)

    first = doctor_admin._doctor_operational_branch(
        db,
        workspace=workspace,
        doctor_id=doctor_id,
    )
    second = doctor_admin._doctor_operational_branch(
        db,
        workspace=workspace,
        doctor_id=doctor_id,
    )

    assert first is branch
    assert second is branch
    assert db.flush_calls == 1
    assert len(db.persisted) == 1
    assert db.pending == []
