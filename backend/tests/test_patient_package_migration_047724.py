from pathlib import Path


def test_patient_package_migration_contract_and_readiness_head() -> None:
    migration = Path("alembic/versions/0048_patient_packages.py").read_text(encoding="utf-8")
    readiness = Path("app/services/operational_readiness.py").read_text(encoding="utf-8")

    assert 'revision: str = "0048_patient_packages"' in migration
    assert 'down_revision: str | None = "0047_appointment_billing_context"' in migration
    assert 'op.create_table(\n        "patient_packages"' in migration
    assert 'op.create_table(\n        "package_usages"' in migration
    assert 'op.add_column("appointments", sa.Column("patient_package_id"' in migration
    assert '"fk_appointments_patient_package"' in migration
    assert '["workspace_id", "patient_package_id"]' in migration
    assert '["workspace_id", "id"]' in migration
    assert 'ENABLE ROW LEVEL SECURITY' in migration
    assert 'REVOKE ALL ON TABLE' in migration
    assert 'EXPECTED_MIGRATION_HEAD = "0054_cancel_recovery"' in readiness
