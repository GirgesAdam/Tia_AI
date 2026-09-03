from __future__ import annotations

import ast
from pathlib import Path

import sqlalchemy as sa

BACKEND_ROOT = Path(__file__).resolve().parents[1]
PAYMENT_MIGRATIONS = (
    BACKEND_ROOT / "alembic" / "versions" / "0029_payment_ledger.py",
    BACKEND_ROOT / "alembic" / "versions" / "0031_payment_allocations.py",
)


def _raw_execute_sql(path: Path) -> list[str]:
    tree = ast.parse(path.read_text(encoding="utf-8"))
    statements: list[str] = []
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call) or not node.args:
            continue
        func = node.func
        if not (
            isinstance(func, ast.Attribute)
            and func.attr == "execute"
            and isinstance(func.value, ast.Name)
            and func.value.id == "op"
        ):
            continue
        sql_arg = node.args[0]
        if isinstance(sql_arg, ast.Constant) and isinstance(sql_arg.value, str):
            statements.append(sql_arg.value)
    return statements


def test_payment_migration_raw_sql_has_no_unbound_sqlalchemy_parameters() -> None:
    """Payment backfill SQL must not accidentally treat literal colons as binds."""

    for migration in PAYMENT_MIGRATIONS:
        statements = _raw_execute_sql(migration)
        assert statements, f"expected raw SQL statements in {migration.name}"
        for statement in statements:
            assert not sa.text(statement)._bindparams, (
                f"{migration.name} contains unintended SQLAlchemy bind parameters: "
                f"{sorted(sa.text(statement)._bindparams)}"
            )
