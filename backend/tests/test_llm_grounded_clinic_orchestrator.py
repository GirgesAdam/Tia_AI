from pathlib import Path
from types import SimpleNamespace
from uuid import uuid4

from app.agents.capability_policy import resolve_capability_policy
from app.agents.clinic_grounding import grounded_catalog_facts, validate_grounded_entity_ids
from app.agents.semantic_router import SemanticCapabilityDecision, SemanticEntityHints
from app.services import agent_chat

SERVICE_UNDERARM = "11111111-1111-4111-8111-111111111111"
SERVICE_FULL = "22222222-2222-4222-8222-222222222222"
BRANCH_NASR = "33333333-3333-4333-8333-333333333333"
DOCTOR_AHMED = "44444444-4444-4444-8444-444444444444"
CATALOG = {
    "services": [
        {
            "id": SERVICE_UNDERARM,
            "name": "ليزر إزالة الشعر - إبط",
            "duration_minutes": 15,
            "price": "550 EGP",
        },
        {
            "id": SERVICE_FULL,
            "name": "ليزر إزالة الشعر - جسم كامل سيدات",
            "duration_minutes": 60,
            "price": "3,200 EGP",
        },
    ],
    "branches": [{"id": BRANCH_NASR, "name": "فرع مدينة نصر"}],
    "doctors": [
        {
            "id": DOCTOR_AHMED,
            "name": "أحمد محمود",
            "service_ids": [SERVICE_UNDERARM, SERVICE_FULL],
            "branch_ids": [BRANCH_NASR],
        }
    ],
}


def _decision(*, capabilities: list[str], hints: SemanticEntityHints) -> SemanticCapabilityDecision:
    return SemanticCapabilityDecision(
        domains=["booking"] if "availability_discovery" in capabilities else ["services"],
        capabilities=capabilities,
        risk_flags=[],
        flow_signal="start_booking" if "availability_discovery" in capabilities else "none",
        entity_hints=hints,
        missing_information=[],
        recommended_handoff_category="other",
        recommended_handoff_priority="normal",
        confidence=0.99,
        reason="grounded test",
    )


def test_catalog_validation_rejects_hallucinated_ids_without_text_matching() -> None:
    hints = SemanticEntityHints(
        service_query="ليزر ابط",
        branch_query="مدينة نصر",
        doctor_query="احمد",
        service_id="99999999-9999-4999-8999-999999999999",
        service_candidate_ids=[SERVICE_UNDERARM, "bad-id"],
        branch_id=BRANCH_NASR,
        doctor_id=DOCTOR_AHMED,
        requested_date="2026-08-25",
        requested_start_time="20:00",
        not_before_time=None,
        not_after_time=None,
        appointment_reference=None,
    )
    validated = validate_grounded_entity_ids(hints, CATALOG)

    assert validated.service_id is None
    assert validated.service_candidate_ids == [SERVICE_UNDERARM]
    assert validated.branch_id == BRANCH_NASR
    assert validated.doctor_id == DOCTOR_AHMED


def test_grounded_catalog_facts_preserve_all_llm_selected_service_candidates() -> None:
    hints = SemanticEntityHints(
        service_query="خدمات الليزر",
        branch_query=None,
        doctor_query=None,
        service_id=None,
        service_candidate_ids=[SERVICE_UNDERARM, SERVICE_FULL],
        requested_date=None,
        requested_start_time=None,
        not_before_time=None,
        not_after_time=None,
        appointment_reference=None,
    )
    payload = grounded_catalog_facts(
        catalog=CATALOG,
        entity_hints=hints,
        capabilities=["service_information"],
    )

    assert payload is not None
    assert [row["id"] for row in payload["services"]] == [SERVICE_UNDERARM, SERVICE_FULL]
    assert payload["needs_service_choice"] is True


def test_grounded_booking_prefetch_uses_only_canonical_ids(monkeypatch) -> None:
    hints = SemanticEntityHints(
        service_query="ليزر ابط",
        branch_query="مدينة نصر",
        doctor_query="احمد",
        service_id=SERVICE_UNDERARM,
        branch_id=BRANCH_NASR,
        doctor_id=DOCTOR_AHMED,
        requested_date="2026-08-25",
        requested_start_time="20:00",
        not_before_time=None,
        not_after_time=None,
        appointment_reference=None,
    )
    decision = _decision(
        capabilities=["availability_discovery", "appointment_creation"],
        hints=hints,
    )
    policy = resolve_capability_policy(decision)
    calls: list[tuple[str, dict]] = []

    def fake_invoke_authorized_tool(*, tool_context, policy, tool_name, arguments):
        calls.append((tool_name, arguments))
        return {"ok": True, "slots": []}

    monkeypatch.setattr(agent_chat, "_invoke_authorized_tool", fake_invoke_authorized_tool)

    _, prefetched_names = agent_chat._prefetch_read_tools(
        tool_context=SimpleNamespace(run_id=uuid4()),
        policy=policy,
        decision=decision,
        flow=None,
        grounded_mode=True,
        use_flow_state=False,
    )
    assert prefetched_names == {"get_booking_options"}
    assert calls == [
        (
            "get_booking_options",
            {
                "booking_date": "2026-08-25",
                "requested_start_time": "20:00",
                "not_before_time": "",
                "not_after_time": "",
                "service_id": SERVICE_UNDERARM,
                "branch_id": BRANCH_NASR,
                "doctor_id": DOCTOR_AHMED,
            },
        )
    ]
    arguments = calls[0][1]
    assert "service_search" not in arguments
    assert "branch_search" not in arguments
    assert "doctor_search" not in arguments


def test_grounded_service_information_does_not_call_lexical_search_tool(monkeypatch) -> None:
    hints = SemanticEntityHints(
        service_query="خدمات الليزر",
        branch_query=None,
        doctor_query=None,
        service_candidate_ids=[SERVICE_UNDERARM, SERVICE_FULL],
        requested_date=None,
        requested_start_time=None,
        not_before_time=None,
        not_after_time=None,
        appointment_reference=None,
    )
    decision = _decision(capabilities=["service_information"], hints=hints)
    policy = resolve_capability_policy(decision)
    calls: list[tuple[str, dict]] = []

    def fake_invoke_authorized_tool(*, tool_context, policy, tool_name, arguments):
        calls.append((tool_name, arguments))
        return {"ok": True}

    monkeypatch.setattr(agent_chat, "_invoke_authorized_tool", fake_invoke_authorized_tool)

    results, names = agent_chat._prefetch_read_tools(
        tool_context=SimpleNamespace(run_id=uuid4()),
        policy=policy,
        decision=decision,
        flow=None,
        grounded_mode=True,
        use_flow_state=False,
    )
    assert calls == []
    assert names == set()
    assert results == {}


def test_grounded_response_requires_matching_availability_evidence() -> None:
    hints = SemanticEntityHints(
        service_query="ليزر ابط",
        branch_query=None,
        doctor_query=None,
        service_id=SERVICE_UNDERARM,
        requested_date="2026-08-25",
        requested_start_time=None,
        not_before_time=None,
        not_after_time=None,
        appointment_reference=None,
    )

    decision = _decision(
        capabilities=[
            "availability_discovery",
            "appointment_creation",
        ],
        hints=hints,
    )

    policy = resolve_capability_policy(decision)

    assert agent_chat._grounded_response_can_cover(
        policy,
        {
            "clinic_catalog": {
                "ok": True,
                "services": [
                    {"id": SERVICE_UNDERARM},
                ],
            }
        },
    ) is False

    assert agent_chat._grounded_response_can_cover(
        policy,
        {
            "get_booking_options": {
                "ok": True,
                "slots": [],
            }
        },
    ) is True


def test_grounded_response_rejects_wrong_customer_read_evidence() -> None:
    decision = _decision(
        capabilities=["customer_history"],
        hints=SemanticEntityHints(
            service_query=None,
            branch_query=None,
            doctor_query=None,
            requested_date=None,
            requested_start_time=None,
            not_before_time=None,
            not_after_time=None,
            appointment_reference=None,
        ),
    )

    policy = resolve_capability_policy(decision)

    assert agent_chat._grounded_response_can_cover(
        policy,
        {
            "get_customer_profile": {
                "ok": True,
            }
        },
    ) is False

    assert agent_chat._grounded_response_can_cover(
        policy,
        {
            "get_customer_history": {
                "ok": True,
            }
        },
    ) is True


def test_grounded_runtime_source_has_no_lexical_entity_resolution() -> None:
    backend = Path(__file__).resolve().parent.parent
    grounding = (backend / "app/agents/clinic_grounding.py").read_text(encoding="utf-8").lower()
    turn = (backend / "app/agents/turn_interpreter.py").read_text(encoding="utf-8").lower()
    agent_chat_source = (backend / "app/services/agent_chat.py").read_text(encoding="utf-8")
    assert "re.compile" not in grounding
    assert "re.search" not in grounding
    assert "re.match" not in grounding
    assert "service_search\": service_query" in agent_chat_source  # legacy rollback path remains
    assert 'if grounded_mode:' in agent_chat_source
    assert '"service_id": service_id' in agent_chat_source
    assert "canonical ids" in turn


def test_grounded_interpreter_preserves_existing_conversation_flow_contract() -> None:
    backend = Path(__file__).resolve().parent.parent
    turn = (backend / "app/agents/turn_interpreter.py").read_text(encoding="utf-8")
    agent_chat_source = (backend / "app/services/agent_chat.py").read_text(encoding="utf-8")

    assert "context_scope" not in turn
    assert "turn_only" not in turn
    assert "context_scope" not in agent_chat_source
    assert "_turn_is_local_side_read" in agent_chat_source
    assert "use_flow_state=not turn_local_side_read" in agent_chat_source
