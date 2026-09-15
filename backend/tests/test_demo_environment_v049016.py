from types import SimpleNamespace

import pytest
from fastapi import HTTPException

from app.api.routes import agent as agent_route
from app.core.config import settings
from app.services.workspace_runtime_policy import workspace_runtime_policy


class FakeSession:
    def __init__(self, count: int):
        self.count = count

    def scalar(self, _statement):
        return self.count


def workspace(*, is_demo: bool, slug: str = "workspace"):
    return SimpleNamespace(id="workspace-id", is_demo=is_demo, slug=slug, name=slug)


def test_production_workspace_never_inherits_demo_budget_from_legacy_env(monkeypatch) -> None:
    monkeypatch.setattr(settings, "demo_mode", True)
    monkeypatch.setattr(settings, "demo_agent_hourly_turn_limit", 1)
    agent_route._enforce_demo_agent_budget(
        FakeSession(10_000), workspace=workspace(is_demo=False)
    )


def test_demo_budget_allows_turns_below_limit(monkeypatch) -> None:
    monkeypatch.setattr(settings, "demo_agent_hourly_turn_limit", 60)
    agent_route._enforce_demo_agent_budget(
        FakeSession(59), workspace=workspace(is_demo=True)
    )


def test_demo_budget_rejects_turns_at_limit(monkeypatch) -> None:
    monkeypatch.setattr(settings, "demo_agent_hourly_turn_limit", 60)
    with pytest.raises(HTTPException) as exc_info:
        agent_route._enforce_demo_agent_budget(
            FakeSession(60), workspace=workspace(is_demo=True)
        )
    assert exc_info.value.status_code == 429


def test_demo_identity_survives_workspace_rename() -> None:
    demo = workspace(is_demo=True, slug="tia")
    before = workspace_runtime_policy(demo)
    demo.slug = "renamed-demo"
    demo.name = "Renamed Demo"
    after = workspace_runtime_policy(demo)
    assert before.is_demo is True
    assert after.is_demo is True
    assert after.allow_external_dispatch is False


def test_runtime_policy_never_uses_workspace_name_or_slug() -> None:
    source = __import__("inspect").getsource(workspace_runtime_policy)
    assert "workspace.slug" not in source
    assert "workspace.name" not in source
    assert "settings.demo_mode" not in source
    assert "settings.demo_allow_external_dispatch" not in source
