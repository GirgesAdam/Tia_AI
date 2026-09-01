import ast
from pathlib import Path

from app.services.operational_readiness import (
    AUTOMATION_WORKER_HEARTBEAT_MINUTES,
    STALE_LOCK_MINUTES,
    TEST_DEDUPE_PREFIXES,
    TEST_RULE_KEY_PREFIXES,
)


def test_worker_heartbeat_threshold_matches_minute_scheduler() -> None:
    assert 2 <= AUTOMATION_WORKER_HEARTBEAT_MINUTES <= 5


def test_readiness_waits_longer_than_engine_reclaim_window() -> None:
    assert STALE_LOCK_MINUTES > 10


def test_regression_artifacts_are_explicitly_classified() -> None:
    assert "staging_regression_" in TEST_RULE_KEY_PREFIXES
    assert "staging-regression:" in TEST_DEDUPE_PREFIXES


def test_readiness_reports_runtime_worker_heartbeat_separately() -> None:
    backend = Path(__file__).resolve().parent.parent
    source = (backend / "app/services/operational_readiness.py").read_text(encoding="utf-8")

    assert 'key="automation_worker_heartbeat"' in source
    assert "runtime_enabled_rules" in source
    assert "explicit_test_rules" in source
    assert "explicit_test_workers" in source
    assert "Verify the n8n automation scheduler is active." in source


def test_test_only_stale_jobs_are_warning_not_runtime_failure() -> None:
    backend = Path(__file__).resolve().parent.parent
    source = (backend / "app/services/operational_readiness.py").read_text(encoding="utf-8")

    assert 'stale_severity = "warn"' in source
    assert "no runtime stale job exists" in source
    assert 'stale_severity = "fail"' in source


def test_diagnostic_has_no_database_mutation_calls() -> None:
    backend = Path(__file__).resolve().parent.parent
    source = (backend / "scripts/inspect_automation_runtime.py").read_text(encoding="utf-8")
    tree = ast.parse(source)

    forbidden_db_methods = {"commit", "flush", "add", "add_all", "delete"}
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue
        func = node.func
        if isinstance(func, ast.Attribute):
            assert func.attr not in forbidden_db_methods

    assert "from sqlalchemy import select" in source
    assert "from sqlalchemy import delete" not in source
    assert "from sqlalchemy import update" not in source
    assert "from sqlalchemy import insert" not in source


def test_cleanup_targets_only_explicit_test_artifacts() -> None:
    backend = Path(__file__).resolve().parent.parent
    source = (backend / "scripts/cleanup_test_automation_artifacts.py").read_text(encoding="utf-8")

    assert "settings.is_production" in source
    assert 'like("final-gate-%")' in source
    assert 'like("staging-regression:%")' in source
    assert '"final-gate-stale"' in source
    assert '"tia-full-staging-regression"' in source
    assert 'AutomationJob.status == "processing"' not in source
