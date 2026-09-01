from types import SimpleNamespace
from uuid import uuid4

from app.agents.capability_policy import resolve_capability_policy
from app.agents.semantic_router import SemanticCapabilityDecision, SemanticEntityHints
from app.services import agent_chat


def _decision(*, capabilities: list[str], **hints: str | None) -> SemanticCapabilityDecision:
    return SemanticCapabilityDecision(
        domains=["booking"] if "availability_discovery" in capabilities else ["services"],
        capabilities=capabilities,
        risk_flags=[],
        flow_signal="start_booking" if "availability_discovery" in capabilities else "none",
        entity_hints=SemanticEntityHints(
            service_query=hints.get("service_query"),
            branch_query=hints.get("branch_query"),
            doctor_query=hints.get("doctor_query"),
            requested_date=hints.get("requested_date"),
            requested_start_time=hints.get("requested_start_time"),
            not_before_time=hints.get("not_before_time"),
            not_after_time=hints.get("not_after_time"),
            appointment_reference=hints.get("appointment_reference"),
        ),
        missing_information=[],
        recommended_handoff_category="other",
        recommended_handoff_priority="normal",
        confidence=0.99,
        reason="test",
    )


def test_service_read_is_prefetched_without_an_agent_tool_round(monkeypatch) -> None:
    decision = _decision(capabilities=["service_information"], service_query="ليزر")
    policy = resolve_capability_policy(decision)
    calls: list[tuple[str, dict]] = []

    def fake_invoke_authorized_tool(*, tool_context, policy, tool_name, arguments):
        calls.append((tool_name, arguments))
        return {"ok": True, "services": [{"name": "ليزر"}]}

    monkeypatch.setattr(agent_chat, "_invoke_authorized_tool", fake_invoke_authorized_tool)

    results, names = agent_chat._prefetch_read_tools(
        tool_context=SimpleNamespace(run_id=uuid4()),
        policy=policy,
        decision=decision,
        flow=None,
    )

    assert calls == [("search_services", {"search": "ليزر"})]
    assert names == {"search_services"}
    assert results["search_services"]["ok"] is True


def test_booking_prefetch_uses_high_level_read_and_never_executes_write(monkeypatch) -> None:
    decision = _decision(
        capabilities=["availability_discovery", "appointment_creation"],
        service_query="ليزر",
        branch_query="New Cairo",
        doctor_query="أحمد محمود",
        requested_date="2026-08-18",
        not_before_time="18:00",
    )
    policy = resolve_capability_policy(decision)
    calls: list[tuple[str, dict]] = []

    def fake_invoke_authorized_tool(*, tool_context, policy, tool_name, arguments):
        calls.append((tool_name, arguments))
        return {
            "ok": True,
            "needs_doctor_choice": False,
            "doctor": {"doctor_name": "أحمد محمود"},
            "slots": [],
        }

    monkeypatch.setattr(agent_chat, "_invoke_authorized_tool", fake_invoke_authorized_tool)

    _, names = agent_chat._prefetch_read_tools(
        tool_context=SimpleNamespace(run_id=uuid4()),
        policy=policy,
        decision=decision,
        flow=None,
    )

    assert names == {"get_booking_options"}
    assert calls == [
        (
            "get_booking_options",
            {
                "service_search": "ليزر",
                "booking_date": "2026-08-18",
                "requested_start_time": "",
                "not_before_time": "18:00",
                "not_after_time": "",
                "branch_search": "New Cairo",
                "doctor_search": "أحمد محمود",
            },
        )
    ]
    assert all(tool_name != "book_appointment" for tool_name, _ in calls)


def test_successful_booking_prefetch_covers_lower_level_booking_reads(monkeypatch) -> None:
    decision = _decision(
        capabilities=[
            "availability_discovery",
            "appointment_creation",
            "doctor_discovery",
            "branch_discovery",
            "pricing",
        ],
        service_query="ليزر",
        branch_query="مدينة نصر",
        requested_date="2026-08-19",
    )
    policy = resolve_capability_policy(decision)
    calls: list[tuple[str, dict]] = []

    def fake_invoke_authorized_tool(*, tool_context, policy, tool_name, arguments):
        calls.append((tool_name, arguments))
        return {
            "ok": True,
            "service": {"service_name": "ليزر"},
            "branch": {"branch_name": "مدينة نصر"},
            "slots": [{"doctor_name": "أحمد محمود"}],
        }

    monkeypatch.setattr(agent_chat, "_invoke_authorized_tool", fake_invoke_authorized_tool)

    _, names = agent_chat._prefetch_read_tools(
        tool_context=SimpleNamespace(run_id=uuid4()),
        policy=policy,
        decision=decision,
        flow=None,
    )

    assert calls[0][0] == "get_booking_options"
    assert {"get_booking_options", "search_services", "list_branches", "list_doctors"} <= names
    assert len(calls) == 1


def test_persistent_booking_flow_capabilities_drop_turn_local_reads() -> None:
    assert agent_chat._persistent_flow_capabilities(
        "booking",
        [
            "availability_discovery",
            "appointment_creation",
            "doctor_discovery",
            "pricing",
            "branch_discovery",
        ],
    ) == ["appointment_creation", "availability_discovery"]


def test_persistent_reschedule_flow_capabilities_drop_turn_local_reads() -> None:
    assert agent_chat._persistent_flow_capabilities(
        "appointment_reschedule",
        ["appointment_reschedule", "doctor_discovery", "appointment_list"],
    ) == ["appointment_reschedule"]


def test_exact_start_prefetch_is_not_encoded_as_zero_width_window(monkeypatch) -> None:
    decision = _decision(
        capabilities=["availability_discovery", "appointment_creation"],
        service_query="ليزر إزالة الشعر",
        branch_query="مدينة نصر",
        doctor_query="أحمد محمود",
        requested_date="2026-08-25",
        requested_start_time="18:00",
    )
    policy = resolve_capability_policy(decision)
    calls: list[tuple[str, dict]] = []

    def fake_invoke_authorized_tool(*, tool_context, policy, tool_name, arguments):
        calls.append((tool_name, arguments))
        return {"ok": True, "slots": []}

    monkeypatch.setattr(agent_chat, "_invoke_authorized_tool", fake_invoke_authorized_tool)
    agent_chat._prefetch_read_tools(
        tool_context=SimpleNamespace(run_id=uuid4()),
        policy=policy,
        decision=decision,
        flow=None,
    )

    args = calls[0][1]
    assert args["requested_start_time"] == "18:00"
    assert args["not_before_time"] == ""
    assert args["not_after_time"] == ""
