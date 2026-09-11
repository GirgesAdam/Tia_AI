from types import SimpleNamespace
from uuid import uuid4

from app.api.routes import doctor_admin
from app.schemas.clinic import WorkingHoursReplace


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


class _HoursSession:
    """Tracks delete/flush/insert ordering for a no-autoflush replacement."""

    def __init__(self, existing_rows):
        self.existing_rows = list(existing_rows)
        self.deleted = []
        self.added = []
        self.events = []

    def scalars(self, _statement):
        return list(self.existing_rows)

    def delete(self, row):
        self.deleted.append(row)
        self.events.append(("delete", row))

    def flush(self):
        self.events.append(("flush", tuple(self.deleted)))
        self.existing_rows = [row for row in self.existing_rows if row not in self.deleted]
        self.deleted.clear()

    def add_all(self, rows):
        rows = list(rows)
        self.added.extend(rows)
        self.events.append(("add_all", tuple(rows)))


def test_replace_hours_flushes_deletes_before_inserting_unchanged_intervals(monkeypatch) -> None:
    workspace = SimpleNamespace(id=uuid4(), name="Regression Clinic")
    branch = SimpleNamespace(id=uuid4())
    doctor_id = uuid4()
    unchanged = SimpleNamespace(weekday=5, start_time="09:00", end_time="17:00")
    changed = SimpleNamespace(weekday=6, start_time="16:00", end_time="22:00")
    db = _HoursSession([unchanged, changed])

    monkeypatch.setattr(
        doctor_admin,
        "_doctor_operational_branch",
        lambda _db, *, workspace, doctor_id: branch,
    )

    payload = WorkingHoursReplace.model_validate(
        {
            "intervals": [
                {"weekday": 5, "start_time": "09:00", "end_time": "17:00"},
                {"weekday": 6, "start_time": "16:00", "end_time": "21:00"},
            ]
        }
    )

    replacements = doctor_admin._replace_doctor_hours(
        db,
        workspace=workspace,
        doctor_id=doctor_id,
        payload=payload,
    )

    event_names = [event[0] for event in db.events]
    assert event_names == ["delete", "delete", "flush", "add_all"]
    assert db.existing_rows == []
    assert len(replacements) == 2
    assert len(db.added) == 2
    assert db.added[0].weekday == 5
    assert str(db.added[0].start_time) == "09:00:00"
    assert str(db.added[0].end_time) == "17:00:00"
    assert db.added[1].weekday == 6
    assert str(db.added[1].end_time) == "21:00:00"
