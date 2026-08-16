from pathlib import Path

from app.agents.capability_policy import (
    CAPABILITY_TOOL_POLICY,
    WRITE_TOOL_CAPABILITY,
)
from app.agents.semantic_router import SemanticCapabilityDecision


def test_email_is_semantic_capability_and_authorized_write() -> None:
    assert CAPABILITY_TOOL_POLICY["email_communication"] == frozenset(
        {"send_email_to_customer"}
    )
    assert WRITE_TOOL_CAPABILITY["send_email_to_customer"] == "email_communication"


def test_semantic_schema_accepts_email_communication() -> None:
    schema = SemanticCapabilityDecision.model_json_schema()
    raw = str(schema)
    assert "email_communication" in raw
    assert "communications" in raw


def test_email_tool_cannot_accept_arbitrary_recipient_argument() -> None:
    backend = Path(__file__).resolve().parent.parent
    source = (
        backend / "app/agents/tools/clinic_tools.py"
    ).read_text(encoding="utf-8")
    start = source.index("def send_email_to_customer")
    end = source.index("def escalate_to_human", start)
    tool_source = source[start:end]
    assert "subject: str, body: str" in tool_source
    assert "recipient" not in tool_source.split("-> str", 1)[0]
    assert "queue_patient_email" in tool_source


def test_outbound_email_is_durable_outbox_not_direct_gmail_api() -> None:
    backend = Path(__file__).resolve().parent.parent
    source = (
        backend / "app/services/outbound_communications.py"
    ).read_text(encoding="utf-8")
    assert "MessageDispatch(" in source
    assert 'status="queued"' in source
    assert 'provider == "n8n_gmail"' in source
    assert 'external_conversation_id = f"email:{patient.id}"' in source
    assert "len(email) > 254" in source
    assert "requests." not in source
    assert "httpx." not in source


def test_real_runtime_provisioners_do_not_store_provider_secrets() -> None:
    backend = Path(__file__).resolve().parent.parent
    gmail = (backend / "scripts/provision_gmail_channel.py").read_text(encoding="utf-8")
    whatsapp = (backend / "scripts/provision_whatsapp_channel.py").read_text(encoding="utf-8")
    for source in (gmail, whatsapp):
        assert "access_token" not in source.lower()
        assert "client_secret" not in source.lower()
        assert '"runtime_kind": "real"' in source


def test_readiness_ignores_staging_mock_channels() -> None:
    backend = Path(__file__).resolve().parent.parent
    source = (
        backend / "app/services/operational_readiness.py"
    ).read_text(encoding="utf-8")

    # Assert behavior-bearing predicates, not the exact formatting of a
    # human-readable message split across adjacent Python string literals.
    assert 'row.provider != "staging_mock"' in source
    assert 'not bool((row.config_json or {}).get("mock"))' in source
    assert 'not bool((row.config_json or {}).get("do_not_send"))' in source
    assert '(row.config_json or {}).get("runtime_kind") == "real"' in source

    # Keep a lightweight message contract without depending on source-line
    # concatenation/formatting.
    assert "No real external channel connection is active" in source
    assert "connections do not count as production runtime." in source
