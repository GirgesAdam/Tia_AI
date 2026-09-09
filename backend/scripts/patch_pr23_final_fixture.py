from __future__ import annotations

from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
TARGET = ROOT / "backend/tests/test_external_sync_engine_phase62c.py"


def main() -> None:
    source = TARGET.read_text(encoding="utf-8")
    marker = '''        """
        CREATE TABLE payment_transactions (
'''
    table = '''        """
        CREATE TABLE appointment_product_lines (
            id CHAR(32) PRIMARY KEY, workspace_id CHAR(32) NOT NULL,
            appointment_id CHAR(32) NOT NULL, product_id CHAR(32) NOT NULL,
            product_name VARCHAR(180) NOT NULL, quantity INTEGER NOT NULL DEFAULT 1,
            unit_price_minor INTEGER NOT NULL, currency VARCHAR(3) NOT NULL DEFAULT 'EGP',
            created_by_user_id CHAR(32), created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
            updated_at DATETIME DEFAULT CURRENT_TIMESTAMP
        )
        """,
'''
    if "CREATE TABLE appointment_product_lines" in source:
        print("appointment_product_lines fixture already present")
        return
    if marker not in source:
        raise SystemExit("Could not locate payment_transactions fixture marker")
    TARGET.write_text(source.replace(marker, table + marker, 1), encoding="utf-8")
    print("Added appointment_product_lines to external sync SQLite fixture")


if __name__ == "__main__":
    main()
