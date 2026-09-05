from __future__ import annotations

from datetime import datetime
from types import SimpleNamespace
from uuid import uuid4

from langchain_core.messages import AIMessage, HumanMessage

from app.agents.capability_policy import resolve_capability_policy
from app.agents.flow_interpreter import FlowTurnDecision
from app.agents.semantic_router import (
    SemanticCapabilityDecision,
    SemanticEntityHints,
)
from app.agents.turn_interpreter import _history_excerpt as turn_history_excerpt
from app.services import agent_chat


def _hints(**overrides) -> SemanticEntityHints:
    values = dict(
        service_query=None,
        branch_query=None,
        doctor_query=None,
        service_id=None,
        service_candidate_ids=[],
        branch_id=None,
        branch_candidate_ids=[],
        doctor_id=None,
        doctor_candidate_ids=[],
        requested_date=None,
        requested_start_time=None,
        not_before_time=None,
        not_after_time=None,
        appointment_reference=None,
    )
    values.update(overrides)
    return SemanticEntityHints(**values)


def _decision(capabilities: list[str], *, hints: SemanticEntityHints | None = None):
    return SemanticCapabilityDecision(
        domains=["booking"] if "availability_discovery" in capabilities else ["patient"],
        capabilities=capabilities,
        risk_flags=[],
        flow_signal="start_booking" if "availability_discovery" in capabilities else "none",
        entity_hints=hints or _hints(),
        missing_information=[],
        recommended_handoff_category="other",
        recommended_handoff_priority="normal",
        confidence=1.0,
        reason="test",
    )


def test_unified_turn_interpreter_only_receives_latest_customer_turn() -> None:
    history = [
        HumanMessage(content="مش عايز رسائل عروض تاني"),
        AIMessage(content="تمام"),
        HumanMessage(content="عايز أحجز underarm بكرة"),
    ]

    assert turn_history_excerpt(history) == "عايز أحجز underarm بكرة"


def test_package_reads_are_deterministic_and_do_not_expose_write_or_handoff_tools() -> None:
    info = resolve_capability_policy(_decision(["package_information"]))
    quote = resolve_capability_policy(_decision(["package_refund_quote"]))

    assert info.requires_human is False
    assert info.allowed_tools == frozenset()
    assert quote.requires_human is False
    assert quote.allowed_tools == frozenset()


def test_capability_free_turn_is_local_while_flow_stays_alive() -> None:
    flow = SimpleNamespace(flow_type="booking")
    turn = FlowTurnDecision(
        action="continue",
        capabilities=[],
        risk_flags=[],
        entity_hints=_hints(),
        clear_entity_fields=[],
        selection_index=None,
        selection_time=None,
        missing_information=[],
        recommended_handoff_category="other",
        recommended_handoff_priority="normal",
        confidence=1.0,
        reason="language change",
    )

    assert agent_chat._turn_is_local_side_read(flow, turn) is True


def test_cross_date_prefetch_stops_on_first_verified_day(monkeypatch) -> None:
    workspace_id = uuid4()
    patient_id = uuid4()
    calls: list[dict] = []

    monkeypatch.setattr(agent_chat.settings, "agent_prefetch_reads_enabled", True)
    monkeypatch.setattr(
        agent_chat,
        "_workspace_clock",
        lambda _workspace: ("Africa/Cairo", datetime.fromisoformat("2026-09-02T15:00:00+03:00")),
    )

    def fake_invoke(*, tool_context, policy, tool_name, arguments):
        assert tool_name == "get_booking_options"
        calls.append(dict(arguments))
        if len(calls) == 1:
            return {"ok": True, "slots": [], "date": arguments["booking_date"]}
        return {
            "ok": True,
            "slots": [{"start_local": f'{arguments["booking_date"]}T18:00:00+03:00'}],
            "date": arguments["booking_date"],
        }

    monkeypatch.setattr(agent_chat, "_invoke_authorized_tool", fake_invoke)

    tool_context = SimpleNamespace(
        db=object(),
        workspace=SimpleNamespace(id=workspace_id, timezone="Africa/Cairo"),
        patient=SimpleNamespace(id=patient_id),
        conversation=None,
        run_id=None,
    )
    decision = _decision(
        ["availability_discovery", "appointment_creation"],
        hints=_hints(
            service_query="full body",
            service_id=str(uuid4()),
            not_before_time="17:00",
        ),
    )
    policy = resolve_capability_policy(decision)

    results, prefetched = agent_chat._prefetch_read_tools(
        tool_context=tool_context,
        policy=policy,
        decision=decision,
        flow=None,
        grounded_mode=True,
    )

    assert len(calls) == 2
    assert calls[0]["booking_date"] == "2026-09-02"
    assert calls[1]["booking_date"] == "2026-09-03"
    assert "get_booking_options" in prefetched
    assert results["get_booking_options"]["next_available_search"]["matched_date"] == "2026-09-03"


def test_refund_quote_reprices_consumed_sessions_at_standalone_price(monkeypatch) -> None:
    package_id = uuid4()
    workspace_id = uuid4()
    patient_id = uuid4()
    selected = {
        "id": str(package_id),
        "effective_status": "active",
        "sessions_consumed": 1,
        "sessions_remaining": 3,
    }
    monkeypatch.setattr(
        agent_chat,
        "_customer_package_payload",
        lambda **_: {"ok": True, "packages": [selected], "usable_packages": [selected]},
    )
    package = SimpleNamespace(
        id=package_id,
        patient_id=patient_id,
        name="Full Body Package",
        currency="EGP",
        opening_sessions_remaining=None,
        sessions_total_known=True,
        sessions_purchased=4,
        standalone_session_price_minor_at_purchase=250_000,
    )
    db = SimpleNamespace(scalar=lambda _stmt: package)
    monkeypatch.setattr(
        agent_chat,
        "_package_financial_rows",
        lambda *args, **kwargs: ([SimpleNamespace(amount_minor=800_000)], []),
    )

    result = agent_chat._package_refund_quote_payload(
        db=db,
        workspace_id=workspace_id,
        patient_id=patient_id,
    )

    assert result["ok"] is True
    assert result["quote"]["consumed_value_minor"] == 250_000
    assert result["quote"]["refundable_minor"] == 550_000


def test_single_verified_slot_selection_defaults_to_first_option() -> None:
    flow = SimpleNamespace(
        flow_type="booking",
        option_snapshot={
            "slots": [
                {
                    "start_local": "2026-09-03T16:00:00+03:00",
                    "service_id": str(uuid4()),
                    "branch_id": str(uuid4()),
                    "doctor_id": str(uuid4()),
                }
            ]
        },
    )
    turn = FlowTurnDecision(
        action="select_option",
        capabilities=["appointment_creation"],
        risk_flags=[],
        entity_hints=_hints(),
        clear_entity_fields=[],
        selection_index=None,
        selection_time=None,
        missing_information=[],
        recommended_handoff_category="other",
        recommended_handoff_priority="normal",
        confidence=1.0,
        reason="customer confirmed booking",
    )

    normalized = agent_chat._normalize_unambiguous_slot_selection(flow, turn)

    assert normalized.action == "select_option"
    assert normalized.selection_index == 1


def test_single_verified_slot_does_not_autobook_non_selection_turn() -> None:
    flow = SimpleNamespace(
        flow_type="booking",
        option_snapshot={"slots": [{"start_local": "2026-09-03T16:00:00+03:00"}]},
    )
    turn = FlowTurnDecision(
        action="continue",
        capabilities=["pricing"],
        risk_flags=[],
        entity_hints=_hints(),
        clear_entity_fields=[],
        selection_index=None,
        selection_time=None,
        missing_information=[],
        recommended_handoff_category="other",
        recommended_handoff_priority="normal",
        confidence=1.0,
        reason="price question",
    )

    normalized = agent_chat._normalize_unambiguous_slot_selection(flow, turn)

    assert normalized.action == "continue"
    assert normalized.selection_index is None
