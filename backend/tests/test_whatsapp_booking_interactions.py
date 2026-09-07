import json
from pathlib import Path
from types import SimpleNamespace
from uuid import uuid4

from app.services.whatsapp_interactions import (
    parse_whatsapp_booking_action,
    whatsapp_booking_dispatch_metadata,
)


def test_plain_customer_text_is_not_treated_as_a_button_action() -> None:
    assert parse_whatsapp_booking_action({"text": "تأكيد الحجز"}) is None
    assert parse_whatsapp_booking_action({"interactive_reply": {"title": "تغيير الميعاد"}}) is None


def test_structured_button_id_selects_exact_booking_action() -> None:
    appointment_id = "BK-991"
    action = parse_whatsapp_booking_action(
        {
            "interactive_reply": {
                "type": "button_reply",
                "id": f"tia.booking.reschedule:{appointment_id}",
                "title": "تغيير الميعاد",
            }
        }
    )
    assert action is not None
    assert action.action == "reschedule"
    assert action.appointment_id == appointment_id


def test_pending_booking_dispatch_gets_confirm_and_reschedule_buttons() -> None:
    run_id = uuid4()
    appointment_id = str(uuid4())
    db = SimpleNamespace(
        scalar=lambda _statement: SimpleNamespace(
            output_json={
                "ok": True,
                "appointment": {
                    "appointment_id": appointment_id,
                    "status": "pending",
                },
            }
        )
    )
    message = SimpleNamespace(
        workspace_id=uuid4(),
        conversation_id=uuid4(),
        sender_type="ai",
        metadata_json={"agent_run_id": str(run_id)},
    )

    metadata = whatsapp_booking_dispatch_metadata(db, message=message)
    buttons = metadata["whatsapp_interactive"]["buttons"]

    assert buttons == [
        {
            "id": f"tia.booking.confirm:{appointment_id}",
            "title": "تأكيد الحجز",
        },
        {
            "id": f"tia.booking.reschedule:{appointment_id}",
            "title": "تغيير الميعاد",
        },
    ]


def test_reschedule_discovery_is_pinned_to_structured_appointment_id() -> None:
    backend = Path(__file__).resolve().parent.parent
    agent_chat = (backend / "app/services/agent_chat.py").read_text(encoding="utf-8")
    tools = (backend / "app/agents/tools/clinic_tools.py").read_text(encoding="utf-8")

    assert 'appointment_id = text_value("appointment_id")' in agent_chat
    assert '"appointment_id": appointment_id' in agent_chat
    assert 'appointment_id: str = ""' in tools
    assert 'appointment.appointment_id == appointment_id' in tools


def test_completed_booking_uses_grounded_language_layer_with_deterministic_fallback() -> None:
    backend = Path(__file__).resolve().parent.parent
    source = (backend / "app/services/agent_chat.py").read_text(encoding="utf-8")

    assert '"flow-interpreter:verified-booking"' in source
    assert "compose_grounded_customer_reply(" in source
    assert "_package_booking_success_reply(appointment, package_result)" in source


def test_n8n_whatsapp_workflows_support_structured_reply_buttons() -> None:
    root = Path(__file__).resolve().parents[2] / "n8n" / "workflows"
    inbound = json.loads((root / "tia_whatsapp_inbound_status.json").read_text(encoding="utf-8"))
    outbox = json.loads((root / "tia_whatsapp_outbox_worker.json").read_text(encoding="utf-8"))

    inbound_nodes = {node["name"]: node for node in inbound["nodes"]}
    normalize_code = inbound_nodes["Normalize WhatsApp Event"]["parameters"]["jsCode"]
    assert "button_reply" in normalize_code
    assert "interactive_reply" in normalize_code

    outbox_nodes = {node["name"]: node for node in outbox["nodes"]}
    assert "Interactive Message?" in outbox_nodes
    interactive = outbox_nodes["WhatsApp Send Interactive"]
    assert interactive["type"] == "n8n-nodes-base.httpRequest"
    assert interactive["parameters"]["authentication"] == "predefinedCredentialType"
    assert interactive["parameters"]["nodeCredentialType"] == "whatsAppApi"
    assert "graph.facebook.com" in interactive["parameters"]["url"]
    assert "whatsapp_interactive" in interactive["parameters"]["jsonBody"]
