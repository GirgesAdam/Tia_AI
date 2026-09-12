from __future__ import annotations

from pathlib import Path

BACKEND = Path(__file__).resolve().parents[1]


def test_v2_persistence_is_separate_from_semantic_and_write_execution() -> None:
    source = (BACKEND / "app/services/agent_v2/state_persistence.py").read_text(encoding="utf-8")

    assert "start_flow(" not in source
    assert ".commit(" not in source
    assert "agent_chat" not in source
    assert "openai" not in source.lower()
    assert "langchain" not in source.lower()
    assert "raw_customer" not in source
    assert "customer_message" not in source
    assert "re.compile" not in source
    assert "difflib" not in source


def test_pure_v2_state_executor_stays_persistence_free() -> None:
    source = (BACKEND / "app/services/agent_v2/state_executor.py").read_text(encoding="utf-8")

    assert "state_persistence" not in source
    assert "conversation_flow" not in source
    assert "sqlalchemy" not in source.lower()
    assert ".commit(" not in source
