from __future__ import annotations

from types import SimpleNamespace
from uuid import uuid4

from app.agents import clinic_grounding
from app.agents.structured_output import _cached_provider_schema
from app.services import agent_chat
from app.services.booking import calculate_availability
from pydantic import BaseModel


class _TinySchema(BaseModel):
    value: str


def test_catalog_cache_is_signature_guarded_and_copy_safe() -> None:
    workspace_id = uuid4()
    signature = (1, "v1")
    catalog = {"services": [{"id": "service-1"}], "branches": [], "doctors": []}

    with clinic_grounding._catalog_cache_lock:
        clinic_grounding._catalog_cache.clear()

    clinic_grounding._catalog_cache_put(workspace_id, signature, catalog)
    first = clinic_grounding._catalog_cache_get(workspace_id, signature)
    assert first == catalog
    assert first is not catalog

    first["services"][0]["id"] = "mutated"
    second = clinic_grounding._catalog_cache_get(workspace_id, signature)
    assert second["services"][0]["id"] == "service-1"
    assert clinic_grounding._catalog_cache_get(workspace_id, (2, "v2")) is None


def test_availability_accepts_verified_preloaded_rows() -> None:
    names = calculate_availability.__code__.co_varnames
    assert "preloaded_branch" in names
    assert "preloaded_service" in names


def test_verified_prefetch_flow_sync_uses_in_memory_result(monkeypatch) -> None:
    payload = {
        "ok": True,
        "date": "2026-08-25",
        "service": {"service_id": "service-1"},
        "branch": {"branch_id": "branch-1"},
        "slots": [{"start_time_24h": "20:15"}],
    }
    flow = SimpleNamespace(
        is_active=True,
        flow_type="booking",
        entity_state={"service_id": "service-1"},
    )
    captured: dict[str, object] = {}
    sentinel = object()

    def fake_transition(db, current_flow, **kwargs):
        captured.update(kwargs)
        return sentinel

    monkeypatch.setattr(agent_chat, "transition_flow", fake_transition)
    result = agent_chat._sync_flow_from_verified_prefetch(
        db=object(),
        flow=flow,
        prefetched_results={"get_booking_options": payload},
        run_id=uuid4(),
    )

    assert result is sentinel
    assert captured["status"] == "awaiting_option_selection"
    assert captured["option_snapshot"] == payload
    assert captured["entity_state"]["date"] == "2026-08-25"


def test_structured_schema_compilation_is_cached() -> None:
    _cached_provider_schema.cache_clear()
    first = _cached_provider_schema(_TinySchema)
    second = _cached_provider_schema(_TinySchema)
    assert first is second
    info = _cached_provider_schema.cache_info()
    assert info.misses == 1
    assert info.hits == 1
