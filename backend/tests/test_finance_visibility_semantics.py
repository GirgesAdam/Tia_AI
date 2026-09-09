from __future__ import annotations

from datetime import date
from uuid import uuid4

from app.services.finance import outstanding_balances, payment_method_breakdown


class _Result:
    def all(self):
        return []


class _Db:
    def __init__(self):
        self.statements = []

    def execute(self, statement):
        self.statements.append(statement)
        return _Result()


def test_payment_method_breakdown_only_exposes_current_methods() -> None:
    db = _Db()
    result = payment_method_breakdown(
        db,
        workspace_id=uuid4(),
        timezone_name="Africa/Cairo",
        start_date=date(2026, 9, 1),
        end_date=date(2026, 9, 30),
    )

    assert result.rows == []
    params = db.statements[0].compile().params
    assert ("cash", "visa", "instapay") in params.values()


def test_outstanding_balances_only_include_completed_sessions() -> None:
    db = _Db()
    result = outstanding_balances(db, workspace_id=uuid4(), limit=50)

    assert result.rows == []
    params = db.statements[0].compile().params
    assert "completed" in params.values()
    assert "package_prepaid" in params.values()
