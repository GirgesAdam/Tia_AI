from pathlib import Path

EXPECTED_HARDENED_TABLES = {
    "activity_events",
    "clinic_integration_entity_links",
    "clinic_integration_sync_checkpoints",
    "clinic_integration_sync_failures",
    "clinic_integration_sync_runs",
    "clinic_integration_sync_schedules",
    "clinic_integrations",
    "crm_campaign_recipients",
    "crm_campaigns",
    "crm_cohort_members",
    "crm_cohorts",
    "crm_tasks",
    "payment_allocations",
    "payment_transactions",
}


def test_v04776_hardens_every_previously_exposed_backend_table() -> None:
    backend = Path(__file__).resolve().parent.parent
    migration = (
        backend / "alembic/versions/0045_public_table_rls_hardening.py"
    ).read_text(encoding="utf-8")

    assert 'revision: str = "0045_public_table_rls_hardening"' in migration
    assert 'down_revision: str | None = "0044_campaign_analytics_tracking"' in migration
    assert "ENABLE ROW LEVEL SECURITY" in migration
    assert "REVOKE ALL" in migration
    assert "FROM anon, authenticated" in migration

    for table in EXPECTED_HARDENED_TABLES:
        assert f'"{table}"' in migration


def test_v04776_operational_readiness_tracks_new_migration_head() -> None:
    backend = Path(__file__).resolve().parent.parent
    readiness = (backend / "app/services/operational_readiness.py").read_text(
        encoding="utf-8"
    )
    assert 'EXPECTED_MIGRATION_HEAD = "0054_cancel_recovery"' in readiness


def test_v04776_upgrade_emits_rls_and_revoke_for_each_target(monkeypatch) -> None:
    import importlib.util

    backend = Path(__file__).resolve().parent.parent
    path = backend / "alembic/versions/0045_public_table_rls_hardening.py"
    spec = importlib.util.spec_from_file_location("migration_0045_rls", path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)

    executed: list[str] = []
    monkeypatch.setattr(module.op, "execute", lambda statement: executed.append(str(statement)))

    module.upgrade()

    assert len(executed) == len(EXPECTED_HARDENED_TABLES) * 2
    for table in EXPECTED_HARDENED_TABLES:
        assert f'ALTER TABLE public."{table}" ENABLE ROW LEVEL SECURITY' in executed
        assert f'REVOKE ALL ON TABLE public."{table}" FROM anon, authenticated' in executed
