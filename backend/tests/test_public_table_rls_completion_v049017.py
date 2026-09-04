from pathlib import Path


def test_v049017_hardens_remaining_public_tables() -> None:
    backend = Path(__file__).resolve().parent.parent
    migration = (backend / "alembic/versions/0053_public_table_rls_completion.py").read_text(encoding="utf-8")

    assert 'revision: str = "0053_public_table_rls_completion"' in migration
    assert '"0052_payment_reference_constraint_repair"' in migration
    for table in ("alembic_version", "clinic_data_issues", "doctor_availability_windows"):
        assert f'"{table}"' in migration
    assert "ENABLE ROW LEVEL SECURITY" in migration
    assert "REVOKE ALL" in migration


def test_v049017_updates_operational_readiness_head() -> None:
    backend = Path(__file__).resolve().parent.parent
    readiness = (backend / "app/services/operational_readiness.py").read_text(encoding="utf-8")
    assert 'EXPECTED_MIGRATION_HEAD = "0054_cancel_recovery"' in readiness
