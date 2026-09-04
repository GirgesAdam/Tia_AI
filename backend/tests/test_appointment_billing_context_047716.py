from pathlib import Path

from app.services.operational_readiness import EXPECTED_MIGRATION_HEAD


def _backend() -> Path:
    return Path(__file__).resolve().parent.parent


def test_billing_context_migration_is_head_and_reversible() -> None:
    migration = (_backend() / "alembic/versions/0047_appointment_billing_context.py").read_text(
        encoding="utf-8"
    )
    assert EXPECTED_MIGRATION_HEAD == "0054_cancel_recovery"
    assert 'revision: str = "0047_appointment_billing_context"' in migration
    assert 'down_revision: str | None = "0046_sparse_appointment_context"' in migration
    assert '"billing_context"' in migration
    assert '"package_external_id"' in migration
    assert '"appointment_billing_context_valid"' in migration
    assert 'type_="check"' in migration


def test_appointment_model_persists_package_coverage_without_payment_fact() -> None:
    model = (_backend() / "app/models/appointment.py").read_text(encoding="utf-8")
    assert 'billing_context: Mapped[str]' in model
    assert 'package_external_id: Mapped[str | None]' in model
    assert "billing_context IN ('standard', 'package_prepaid')" in model


def test_billing_context_migration_compiles_for_postgresql_without_live_db(monkeypatch) -> None:
    import importlib.util
    import io

    from alembic.migration import MigrationContext
    from alembic.operations import Operations

    path = _backend() / "alembic/versions/0047_appointment_billing_context.py"
    spec = importlib.util.spec_from_file_location("migration_0047_test", path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)

    output = io.StringIO()
    context = MigrationContext.configure(
        dialect_name="postgresql",
        opts={"as_sql": True, "output_buffer": output},
    )
    monkeypatch.setattr(module, "op", Operations(context))
    module.upgrade()
    module.downgrade()

    sql = output.getvalue().lower()
    assert "add column billing_context" in sql
    assert "add column package_external_id" in sql
    assert "appointment_billing_context_valid" in sql
    assert "drop constraint appointment_billing_context_valid" in sql
