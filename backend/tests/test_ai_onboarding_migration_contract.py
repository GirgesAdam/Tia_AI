from pathlib import Path


def test_migration_follows_workflow_head_and_enables_rls() -> None:
    backend = Path(__file__).resolve().parent.parent
    source = (
        backend / "alembic/versions/0013_ai_onboarding_sessions.py"
    ).read_text(encoding="utf-8")

    assert 'revision: str = "0013_ai_onboarding_sessions"' in source
    assert '"0012_conversation_workflows"' in source
    assert "ENABLE ROW LEVEL SECURITY" in source
    assert "REVOKE ALL" in source
    assert "uq_onboarding_ai_sessions_active_admin" in source
