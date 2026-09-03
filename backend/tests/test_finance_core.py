from __future__ import annotations

from datetime import date
from uuid import uuid4

import pytest
from pydantic import ValidationError

from app.schemas.finance import ExpenseCreate, ExpenseUpdate
from app.services.finance import FinanceOperationError, _utc_bounds, profitability_summary


def test_expense_payload_normalizes_currency_and_text() -> None:
    payload = ExpenseCreate(
        title="  Clinic rent  ",
        category="rent",
        amount_minor=250000,
        currency=" egp ",
        incurred_on=date(2026, 9, 1),
        note="  September rent  ",
    )

    assert payload.title == "Clinic rent"
    assert payload.currency == "EGP"
    assert payload.note == "September rent"


def test_expense_update_rejects_null_for_non_nullable_columns() -> None:
    with pytest.raises(ValidationError):
        ExpenseUpdate(amount_minor=None)

    assert ExpenseUpdate(note=None).note is None


def test_profitability_bounds_use_workspace_timezone() -> None:
    start_at, end_at = _utc_bounds(
        start_date=date(2026, 9, 1),
        end_date=date(2026, 9, 1),
        timezone_name="Africa/Cairo",
    )

    assert start_at.isoformat() == "2026-08-31T21:00:00+00:00"
    assert end_at.isoformat() == "2026-09-01T21:00:00+00:00"


def test_profitability_rejects_inverted_date_range() -> None:
    with pytest.raises(FinanceOperationError):
        _utc_bounds(
            start_date=date(2026, 9, 2),
            end_date=date(2026, 9, 1),
            timezone_name="Africa/Cairo",
        )


def test_profitability_uses_real_payments_minus_refunds_and_expenses() -> None:
    class _Result:
        def __init__(self, rows):
            self._rows = rows

        def all(self):
            return self._rows

    class _Db:
        def __init__(self):
            self.calls = 0

        def execute(self, _stmt):
            self.calls += 1
            if self.calls == 1:
                return _Result([
                    ("EGP", 10000, 2000),
                    ("USD", 500, 0),
                ])
            return _Result([
                ("EGP", 3000),
                ("USD", 100),
                ("EUR", 250),
            ])

    result = profitability_summary(
        _Db(),
        workspace_id=uuid4(),
        timezone_name="Africa/Cairo",
        start_date=date(2026, 9, 1),
        end_date=date(2026, 9, 30),
    )

    by_currency = {row.currency: row for row in result.currencies}
    assert by_currency["EGP"].net_revenue_minor == 8000
    assert by_currency["EGP"].expenses_minor == 3000
    assert by_currency["EGP"].profit_minor == 5000
    assert by_currency["USD"].net_revenue_minor == 500
    assert by_currency["USD"].expenses_minor == 100
    assert by_currency["USD"].profit_minor == 400
    assert by_currency["EUR"].net_revenue_minor == 0
    assert by_currency["EUR"].expenses_minor == 250
    assert by_currency["EUR"].profit_minor == -250
