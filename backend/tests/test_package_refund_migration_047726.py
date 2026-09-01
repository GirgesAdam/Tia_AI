from pathlib import Path


def test_package_refund_migration_adds_price_snapshot_and_package_finance_link() -> None:
    backend = Path(__file__).resolve().parent.parent
    source = (backend / "alembic/versions/0049_package_refund_pricing.py").read_text(
        encoding="utf-8"
    )
    assert 'revision: str = "0049_package_refund_pricing"' in source
    assert 'down_revision: str | None = "0048_patient_packages"' in source
    assert "standalone_session_price_minor_at_purchase" in source
    assert "patient_package_id" in source
    assert "fk_payment_transactions_patient_package" in source
    assert "UPDATE payment_transactions AS pt" in source
    assert "UPDATE payment_transactions AS refund" in source
