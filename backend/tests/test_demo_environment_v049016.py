from types import SimpleNamespace

import pytest
from fastapi import HTTPException

from app.api.routes import agent as agent_route
from app.core.config import settings


class FakeSession:
    def __init__(self, count: int):
        self.count = count

    def scalar(self, _statement):
        return self.count


def test_demo_budget_is_disabled_outside_demo(monkeypatch) -> None:
    monkeypatch.setattr(settings, "demo_mode", False)
    agent_route._enforce_demo_agent_budget(FakeSession(10_000), workspace_id="workspace")


def test_demo_budget_allows_turns_below_limit(monkeypatch) -> None:
    monkeypatch.setattr(settings, "demo_mode", True)
    monkeypatch.setattr(settings, "demo_agent_hourly_turn_limit", 60)
    agent_route._enforce_demo_agent_budget(FakeSession(59), workspace_id="workspace")


def test_demo_budget_rejects_turns_at_limit(monkeypatch) -> None:
    monkeypatch.setattr(settings, "demo_mode", True)
    monkeypatch.setattr(settings, "demo_agent_hourly_turn_limit", 60)
    with pytest.raises(HTTPException) as exc_info:
        agent_route._enforce_demo_agent_budget(FakeSession(60), workspace_id="workspace")
    assert exc_info.value.status_code == 429


def test_public_demo_outbox_guard_is_present() -> None:
    source = __import__("pathlib").Path(agent_route.__file__).parent.joinpath("channels.py").read_text(encoding="utf-8")
    assert "settings.demo_mode and not settings.demo_allow_external_dispatch" in source
    assert "return []" in source
