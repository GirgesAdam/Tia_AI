from pathlib import Path


BACKEND = Path(__file__).resolve().parent.parent


def test_model_contract_allows_requirement_selected() -> None:
    source = (BACKEND / "app/models/conversation_flow_event.py").read_text(
        encoding="utf-8"
    )

    assert '"requirement_selected"' in source
    assert "'requirement_selected', 'write_authorized'" in source


def test_migration_extends_current_head_without_dropping_existing_event_types() -> None:
    source = (
        BACKEND
        / "alembic/versions/0014_conversation_flow_requirement_selected.py"
    ).read_text(encoding="utf-8")

    assert 'revision: str = "0014_flow_requirement_selected"' in source
    assert '"0013_ai_onboarding_sessions"' in source
    assert '"requirement_selected"' in source

    for event_type in (
        "started",
        "updated",
        "options_presented",
        "write_authorized",
        "write_completed",
        "completed",
        "cancelled",
        "interrupted",
        "expired",
        "conflict",
    ):
        assert f'"{event_type}"' in source


def test_migration_targets_the_real_postgres_constraint_name() -> None:
    source = (
        BACKEND
        / "alembic/versions/0014_conversation_flow_requirement_selected.py"
    ).read_text(encoding="utf-8")

    assert (
        '"ck_conversation_flow_events_conversation_flow_event_type_valid"'
        in source
    )


def test_downgrade_preserves_requirement_selection_audit_meaning() -> None:
    source = (
        BACKEND
        / "alembic/versions/0014_conversation_flow_requirement_selected.py"
    ).read_text(encoding="utf-8")

    assert "downgraded_from_event_type" in source
    assert "WHERE event_type = 'requirement_selected'" in source


def test_revision_id_fits_existing_alembic_version_column() -> None:
    # The deployed alembic_version.version_num column is VARCHAR(32).
    # Keep revision identifiers within that limit so Alembic can persist head.
    revision = "0014_flow_requirement_selected"
    assert len(revision) <= 32
