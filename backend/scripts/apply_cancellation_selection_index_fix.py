from __future__ import annotations

from pathlib import Path


AGENT_PATH = Path("app/services/agent_chat.py")
TEST_PATH = Path("tests/test_verified_cancellation_execution.py")


def main() -> None:
    source = AGENT_PATH.read_text(encoding="utf-8")

    old_signature = '''def _verified_cancellation_action(
    *,
    tool_context: AgentToolContext,
    policy: CapabilityPolicyDecision,
    decision: SemanticCapabilityDecision,
    clinic_catalog: dict[str, object],
) -> tuple[str, str] | None:
'''
    new_signature = '''def _verified_cancellation_action(
    *,
    tool_context: AgentToolContext,
    policy: CapabilityPolicyDecision,
    decision: SemanticCapabilityDecision,
    clinic_catalog: dict[str, object],
    selection_index: int | None = None,
) -> tuple[str, str] | None:
'''
    if old_signature not in source:
        raise RuntimeError("cancellation helper signature anchor not found")
    source = source.replace(old_signature, new_signature, 1)

    old_else = '''    else:
        filters_applied = 0
        service_ids: list[str] = []
'''
    new_else = '''    else:
        filters_applied = 0
        if selection_index is not None:
            try:
                selected_index = int(selection_index) - 1
            except (TypeError, ValueError):
                return None
            if selected_index < 0 or selected_index >= len(candidates):
                return None
            candidates = [candidates[selected_index]]
            filters_applied += 1

        service_ids: list[str] = []
'''
    if old_else not in source:
        raise RuntimeError("cancellation resolver body anchor not found")
    source = source.replace(old_else, new_else, 1)

    old_call = '''            prefetch_direct = _verified_cancellation_action(
                tool_context=tool_context,
                policy=policy,
                decision=semantic_decision,
                clinic_catalog=clinic_catalog,
            )
'''
    new_call = '''            prefetch_direct = _verified_cancellation_action(
                tool_context=tool_context,
                policy=policy,
                decision=semantic_decision,
                clinic_catalog=clinic_catalog,
                selection_index=unified_turn.selection_index,
            )
'''
    if old_call not in source:
        raise RuntimeError("cancellation orchestration call anchor not found")
    source = source.replace(old_call, new_call, 1)
    AGENT_PATH.write_text(source, encoding="utf-8")

    tests = TEST_PATH.read_text(encoding="utf-8")
    addition = '''

def test_structured_selection_index_executes_verified_option(monkeypatch):
    calls = _capture(monkeypatch)
    result = agent_chat._verified_cancellation_action(
        tool_context=object(),
        policy=_policy(),
        decision=_decision(),
        clinic_catalog=_catalog(),
        selection_index=2,
    )
    assert result is not None
    assert calls[0]["arguments"]["appointment_id"] == "appt-laser"
    assert len(calls) == 1


def test_invalid_selection_index_never_writes(monkeypatch):
    calls = _capture(monkeypatch)
    result = agent_chat._verified_cancellation_action(
        tool_context=object(),
        policy=_policy(),
        decision=_decision(),
        clinic_catalog=_catalog(),
        selection_index=99,
    )
    assert result is None
    assert calls == []


def test_selection_index_must_agree_with_canonical_service(monkeypatch):
    calls = _capture(monkeypatch)
    result = agent_chat._verified_cancellation_action(
        tool_context=object(),
        policy=_policy(),
        decision=_decision(service_id=HYDRA_SERVICE),
        clinic_catalog=_catalog(),
        selection_index=2,
    )
    assert result is None
    assert calls == []
'''
    if "test_structured_selection_index_executes_verified_option" in tests:
        raise RuntimeError("selection index tests already present")
    TEST_PATH.write_text(tests.rstrip() + addition + "\n", encoding="utf-8")


if __name__ == "__main__":
    main()
