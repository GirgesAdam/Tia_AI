from types import SimpleNamespace

import pytest

from app.core.config import Settings
from app.services.agent_v2 import live_chat


def test_agent_v2_live_cutover_defaults_off() -> None:
    assert Settings.model_fields["agent_v2_live_enabled"].default is False


def test_live_facade_uses_v1_for_http_and_channels_when_cutover_is_off(monkeypatch) -> None:
    monkeypatch.setattr(live_chat.settings, "agent_v2_live_enabled", False)

    http_result = object()
    channel_result = object()
    calls: list[str] = []

    def fake_http_v1(**kwargs):
        calls.append("http-v1")
        assert kwargs["db"] == "db"
        assert kwargs["workspace"] == "workspace"
        assert kwargs["payload"] == "payload"
        return http_result

    def fake_channel_v1(**kwargs):
        calls.append("channel-v1")
        assert kwargs["source"] == "test-channel"
        return channel_result

    monkeypatch.setattr(live_chat, "run_agent_chat_v1", fake_http_v1)
    monkeypatch.setattr(
        live_chat,
        "run_agent_for_existing_inbound_v1",
        fake_channel_v1,
    )

    assert (
        live_chat.run_agent_chat(
            db="db",
            workspace="workspace",
            payload="payload",
        )
        is http_result
    )
    assert (
        live_chat.run_agent_for_existing_inbound(
            db="db",
            workspace="workspace",
            patient="patient",
            conversation="conversation",
            inbound="inbound",
            source="test-channel",
        )
        is channel_result
    )
    assert calls == ["http-v1", "channel-v1"]


def test_started_v2_turn_never_falls_back_to_v1(monkeypatch) -> None:
    monkeypatch.setattr(live_chat.settings, "agent_v2_live_enabled", True)
    v1_calls = 0

    def fake_http_v1(**kwargs):
        nonlocal v1_calls
        v1_calls += 1
        return object()

    def fail_after_v2_selection(*args, **kwargs):
        raise RuntimeError("v2-started")

    monkeypatch.setattr(live_chat, "run_agent_chat_v1", fake_http_v1)
    monkeypatch.setattr(live_chat, "_get_patient_v2", fail_after_v2_selection)

    with pytest.raises(RuntimeError, match="v2-started"):
        live_chat.run_agent_chat(
            db="db",
            workspace=SimpleNamespace(id="workspace-id"),
            payload=SimpleNamespace(patient_id="patient-id"),
        )

    assert v1_calls == 0
