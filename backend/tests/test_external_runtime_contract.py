from pathlib import Path

from app.agents.capability_policy import (
    CAPABILITY_TOOL_POLICY,
    WRITE_TOOL_CAPABILITY,
)
from app.agents.semantic_router import SemanticCapabilityDecision


def test_customer_email_capability_is_not_exposed() -> None:
    assert "email_communication" not in CAPABILITY_TOOL_POLICY
    assert "send_email_to_customer" not in WRITE_TOOL_CAPABILITY
    assert CAPABILITY_TOOL_POLICY["follow_up_request"] == frozenset({"create_follow_up_task"})
    assert WRITE_TOOL_CAPABILITY["create_follow_up_task"] == "follow_up_request"


def test_semantic_schema_does_not_offer_customer_email_capability() -> None:
    raw = str(SemanticCapabilityDecision.model_json_schema())
    assert "email_communication" not in raw
    assert "follow_up_request" in raw


def test_agent_tools_do_not_include_customer_email_delivery() -> None:
    backend = Path(__file__).resolve().parent.parent
    source = (backend / "app/agents/tools/clinic_tools.py").read_text(encoding="utf-8")
    assert "send_email_to_customer" not in source
    assert "queue_patient_email" not in source
    assert "ctx.patient.email" not in source


def test_patient_email_outbound_service_is_retired() -> None:
    backend = Path(__file__).resolve().parent.parent
    source = (backend / "app/services/outbound_communications.py").read_text(encoding="utf-8")
    assert "queue_patient_email" not in source
    assert "Patient.email" not in source
    assert "patient/customer email addresses" in source


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
    source = (backend / "app/services/operational_readiness.py").read_text(encoding="utf-8")

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
