from __future__ import annotations

from datetime import UTC, date, datetime
from types import SimpleNamespace
from uuid import uuid4

from app.schemas.inventory import ClinicProductCreate, InventoryItemCreate, InventoryUsageCreate
from app.services.finance_dashboard import _financial_period_buckets, financial_dashboard_trend
from app.services.inventory import (
    add_appointment_product,
    delete_appointment_product,
    is_laser_service,
)


def test_laser_device_pricing_uses_explicit_service_flag_not_name() -> None:
    assert is_laser_service(SimpleNamespace(name="Full Body", category="Other", requires_laser_device=True))
    assert not is_laser_service(SimpleNamespace(name="Laser sounding name", category="Laser", requires_laser_device=False))


def test_new_inventory_contract_is_ml_only_and_products_have_stock_quantity() -> None:
    item = InventoryItemCreate(name="Injectable", quantity_ml="12.5")
    usage = InventoryUsageCreate(used_ml="0.75")
    product = ClinicProductCreate(name="Skin Protector", quantity_on_hand=18)

    assert item.model_dump() == {
        "name": "Injectable",
        "quantity_ml": item.quantity_ml,
        "low_stock_threshold_ml": None,
        "notes": None,
    }
    assert usage.model_dump() == {"used_ml": usage.used_ml, "note": None}
    assert product.quantity_on_hand == 18
    assert "concentration_mg_per_ml" not in InventoryItemCreate.model_fields
    assert "appointment_id" not in InventoryUsageCreate.model_fields


def test_product_sale_decrements_stock_and_removal_restores_it() -> None:
    workspace_id = uuid4()
    appointment_id = uuid4()
    product_id = uuid4()
    line_id = uuid4()
    appointment = SimpleNamespace(
        id=appointment_id,
        workspace_id=workspace_id,
        status="confirmed",
        currency="EGP",
    )
    product = SimpleNamespace(
        id=product_id,
        workspace_id=workspace_id,
        name="Skin Protector",
        quantity_on_hand=5,
        is_active=True,
    )

    class _Db:
        def __init__(self):
            self.scalar_values = [appointment, product]
            self.added = None
            self.deleted = None

        def scalar(self, _stmt):
            return self.scalar_values.pop(0)

        def add(self, value):
            self.added = value
            value.id = line_id

        def delete(self, value):
            self.deleted = value

        def flush(self):
            return None

    db = _Db()
    line = add_appointment_product(
        db,
        workspace_id=workspace_id,
        appointment_id=appointment_id,
        product_id=product_id,
        quantity=2,
        unit_price_minor=15000,
        created_by_user_id=None,
    )
    assert product.quantity_on_hand == 3
    assert line.quantity == 2

    db.scalar_values = [line, product]
    delete_appointment_product(
        db,
        workspace_id=workspace_id,
        appointment_id=appointment_id,
        line_id=line_id,
    )
    assert product.quantity_on_hand == 5
    assert db.deleted is line


def test_month_dashboard_has_four_full_calendar_buckets() -> None:
    buckets = _financial_period_buckets(
        start_date=date(2026, 9, 1),
        end_date=date(2026, 9, 30),
        mode="month",
    )
    assert [(start.day, end.day) for _, start, end in buckets] == [(1, 7), (8, 14), (15, 21), (22, 30)]


def test_year_dashboard_has_twelve_calendar_month_buckets() -> None:
    buckets = _financial_period_buckets(
        start_date=date(2026, 1, 1),
        end_date=date(2026, 12, 31),
        mode="year",
    )
    assert len(buckets) == 12
    assert buckets[0][1:] == (date(2026, 1, 1), date(2026, 1, 31))
    assert buckets[-1][1:] == (date(2026, 12, 1), date(2026, 12, 31))


def test_dashboard_finance_uses_cairo_local_date_and_same_profit_formula() -> None:
    class _Result:
        def __init__(self, rows):
            self.rows = rows

        def all(self):
            return self.rows

    class _Db:
        def __init__(self):
            self.calls = 0

        def execute(self, _stmt):
            self.calls += 1
            if self.calls == 1:
                return _Result([
                    # 2026-09-01 01:30 Cairo: must land in September week 1.
                    (datetime(2026, 8, 31, 22, 30, tzinfo=UTC), "payment", 10000),
                    (datetime(2026, 9, 8, 9, 0, tzinfo=UTC), "refund", 2000),
                ])
            return _Result([(date(2026, 9, 22), 3000)])

    result = financial_dashboard_trend(
        _Db(),
        workspace_id=uuid4(),
        timezone_name="Africa/Cairo",
        start_date=date(2026, 9, 1),
        end_date=date(2026, 9, 30),
        mode="month",
        currency="EGP",
    )

    assert len(result.points) == 4
    assert result.points[0].gross_payments_minor == 10000
    assert result.points[1].refunds_minor == 2000
    assert result.points[3].expenses_minor == 3000
    assert sum(point.net_revenue_minor for point in result.points) == 8000
    assert sum(point.profit_minor for point in result.points) == 5000
