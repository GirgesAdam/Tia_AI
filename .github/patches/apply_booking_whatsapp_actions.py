from __future__ import annotations

import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]


def replace_once(path: str, old: str, new: str) -> None:
    file = ROOT / path
    text = file.read_text(encoding="utf-8")
    count = text.count(old)
    if count != 1:
        raise RuntimeError(f"Expected exactly one match in {path}, found {count}: {old[:120]!r}")
    file.write_text(text.replace(old, new, 1), encoding="utf-8")


# A completed booking remains a deterministic write, but its verified success facts
# are now allowed through the existing grounded language-only composer. Provider
# failure still leaves the deterministic formatter as the reply.
replace_once(
    "backend/app/services/agent_chat.py",
    '            "flow-interpreter:deterministic-booking",\n',
    '            "flow-interpreter:verified-booking",\n',
)

# Persist an exact appointment target supplied by a structured WhatsApp action so a
# later reschedule date/time does not re-ask which appointment the patient means.
replace_once(
    "backend/app/services/agent_chat.py",
    '    doctor_id = text_value("doctor_id")\n    requested_date = text_value("requested_date") or text_value("date")\n',
    '    doctor_id = text_value("doctor_id")\n    appointment_id = text_value("appointment_id")\n    requested_date = text_value("requested_date") or text_value("date")\n',
)
replace_once(
    "backend/app/services/agent_chat.py",
    '        reschedule_arguments = {\n            "booking_date": requested_date,\n',
    '        reschedule_arguments = {\n            "booking_date": requested_date,\n            "appointment_id": appointment_id,\n',
)

replace_once(
    "backend/app/agents/tools/clinic_tools.py",
    '    def get_reschedule_options(\n        booking_date: str,\n        service_id: str = "",\n',
    '    def get_reschedule_options(\n        booking_date: str,\n        appointment_id: str = "",\n        service_id: str = "",\n',
)
replace_once(
    "backend/app/agents/tools/clinic_tools.py",
    '        inputs = {\n            "booking_date": booking_date,\n            "service_id": service_id,\n',
    '        inputs = {\n            "booking_date": booking_date,\n            "appointment_id": appointment_id or None,\n            "service_id": service_id,\n',
)
replace_once(
    "backend/app/agents/tools/clinic_tools.py",
    '            appointments = [\n                appointment\n                for appointment in appointment_result.appointments\n                if appointment.status in {"pending", "confirmed"}\n            ]\n\n            if service_id:\n',
    '            appointments = [\n                appointment\n                for appointment in appointment_result.appointments\n                if appointment.status in {"pending", "confirmed"}\n            ]\n            if appointment_id:\n                appointments = [\n                    appointment\n                    for appointment in appointments\n                    if appointment.appointment_id == appointment_id\n                ]\n\n            if service_id:\n',
)

replace_once(
    "backend/app/services/channels.py",
    'from app.services.agent_chat import run_agent_for_existing_inbound\n',
    'from app.services.agent_chat import run_agent_for_existing_inbound\nfrom app.services.whatsapp_interactions import (\n    process_whatsapp_booking_action,\n    whatsapp_booking_dispatch_metadata,\n)\n',
)
replace_once(
    "backend/app/services/channels.py",
    '        agent_response = run_agent_for_existing_inbound(\n            db=db,\n            workspace=workspace,\n            patient=patient,\n            conversation=conversation,\n            inbound=inbound,\n        )\n',
    '        agent_response = (\n            process_whatsapp_booking_action(\n                db,\n                workspace=workspace,\n                patient=patient,\n                conversation=conversation,\n                inbound=inbound,\n            )\n            if connection.channel == "whatsapp"\n            else None\n        )\n        if agent_response is None:\n            agent_response = run_agent_for_existing_inbound(\n                db=db,\n                workspace=workspace,\n                patient=patient,\n                conversation=conversation,\n                inbound=inbound,\n            )\n',
)
replace_once(
    "backend/app/services/channels.py",
    '                metadata=message.metadata_json or {},\n                attempt=dispatch.attempts,\n',
    '                metadata=(\n                    whatsapp_booking_dispatch_metadata(db, message=message)\n                    if connection.channel == "whatsapp"\n                    else (message.metadata_json or {})\n                ),\n                attempt=dispatch.attempts,\n',
)

# Normalize Meta interactive button replies into the adapter envelope. The visible
# title is stored as message text for history only; routing trusts the opaque ID.
inbound_path = ROOT / "n8n/workflows/tia_whatsapp_inbound_status.json"
inbound = json.loads(inbound_path.read_text(encoding="utf-8"))
normalize = next(node for node in inbound["nodes"] if node["name"] == "Normalize WhatsApp Event")
code = normalize["parameters"]["jsCode"]
old = """  for (const message of messages) {\n    if (message?.type !== 'text' || !message?.text?.body || !message?.id || !message?.from) {\n      continue;\n    }\n\n    const contact = contacts.find((item) => item?.wa_id === message.from) ?? contacts[0] ?? {};"""
new = """  for (const message of messages) {\n    const buttonReply = message?.type === 'interactive' && message?.interactive?.type === 'button_reply'\n      ? message.interactive.button_reply\n      : null;\n    const text = message?.type === 'text' ? message?.text?.body : buttonReply?.title;\n    if (!text || !message?.id || !message?.from || (buttonReply && !buttonReply.id)) {\n      continue;\n    }\n\n    const contact = contacts.find((item) => item?.wa_id === message.from) ?? contacts[0] ?? {};"""
if code.count(old) != 1:
    raise RuntimeError("Inbound WhatsApp normalizer shape changed")
code = code.replace(old, new, 1)
code = code.replace("          text: message.text.body,", "          text,", 1)
code = code.replace(
    "            whatsapp_type: message.type,\n            context_message_id: message.context?.id ?? null,",
    "            whatsapp_type: message.type,\n            interactive_reply: buttonReply ? { type: 'button_reply', id: buttonReply.id, title: buttonReply.title ?? null } : null,\n            context_message_id: message.context?.id ?? null,",
    1,
)
normalize["parameters"]["jsCode"] = code
inbound_path.write_text(json.dumps(inbound, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

# The stock n8n WhatsApp send node does not expose Meta interactive messages, so use
# HTTP Request with the existing WhatsApp API credential type. No token is embedded.
outbox_path = ROOT / "n8n/workflows/tia_whatsapp_outbox_worker.json"
outbox = json.loads(outbox_path.read_text(encoding="utf-8"))
by_name = {node["name"]: node for node in outbox["nodes"]}
if "Interactive Message?" in by_name:
    raise RuntimeError("Interactive outbox nodes already exist")

interactive_if = {
    "parameters": {
        "conditions": {
            "options": {"caseSensitive": True, "leftValue": "", "typeValidation": "strict", "version": 2},
            "conditions": [{
                "id": "7c08ce3b-f613-48b7-bb27-70fdb8aeb201",
                "leftValue": "={{ String(($json.metadata && $json.metadata.whatsapp_interactive && $json.metadata.whatsapp_interactive.type) || '') }}",
                "rightValue": "button",
                "operator": {"type": "string", "operation": "equals"},
            }],
            "combinator": "and",
        },
        "options": {},
    },
    "type": "n8n-nodes-base.if",
    "typeVersion": 2.2,
    "position": [-180, 260],
    "id": "9ea9ea44-711f-448c-9a31-6bc2b4606a15",
    "name": "Interactive Message?",
}
interactive_send = {
    "parameters": {
        "method": "POST",
        "url": "={{ 'https://graph.facebook.com/' + $json.external_account_id + '/messages' }}",
        "authentication": "predefinedCredentialType",
        "nodeCredentialType": "whatsAppApi",
        "sendBody": True,
        "specifyBody": "json",
        "jsonBody": "={{ JSON.stringify({messaging_product:'whatsapp',to:$json.external_user_id,type:'interactive',interactive:{type:'button',body:{text:$json.content},action:{buttons:[($json.metadata.whatsapp_interactive.buttons[0] ? {type:'reply',reply:$json.metadata.whatsapp_interactive.buttons[0]} : null),($json.metadata.whatsapp_interactive.buttons[1] ? {type:'reply',reply:$json.metadata.whatsapp_interactive.buttons[1]} : null),($json.metadata.whatsapp_interactive.buttons[2] ? {type:'reply',reply:$json.metadata.whatsapp_interactive.buttons[2]} : null)].filter(Boolean)}}}) }}",
        "options": {"timeout": 30000},
    },
    "type": "n8n-nodes-base.httpRequest",
    "typeVersion": 4.2,
    "position": [120, 300],
    "id": "8dc89fe0-444d-4dde-bf4b-a41d82f26cb7",
    "name": "WhatsApp Send Interactive",
    "onError": "continueRegularOutput",
}
result_body = "={{ JSON.stringify({status: ((($json.messages && $json.messages[0] && $json.messages[0].id) || $json.id) ? 'sent' : 'failed'), provider_message_id: (($json.messages && $json.messages[0] && $json.messages[0].id) || $json.id || null), error: (((($json.messages && $json.messages[0] && $json.messages[0].id) || $json.id)) ? null : (($json.error && ($json.error.message || $json.error.description || $json.error.toString())) || $json.message || $json.errorDescription || 'WhatsApp interactive send failed in n8n')), retry_after_seconds: ((($json.messages && $json.messages[0] && $json.messages[0].id) || $json.id) ? null : 30), metadata: {transport:'n8n', provider:'meta_cloud', message_type:'interactive', attempt:$('Expand Dispatches').item.json.attempt}}) }}"
interactive_result = {
    "parameters": {
        "method": "POST",
        "url": "={{ ($env.TIA_API_BASE_URL || 'http://host.docker.internal:8000') + '/api/v1/channels/adapter/outbox/' + $('Expand Dispatches').item.json.dispatch_id + '/result' }}",
        "authentication": "genericCredentialType",
        "genericAuthType": "httpHeaderAuth",
        "sendBody": True,
        "specifyBody": "json",
        "jsonBody": result_body,
        "options": {"timeout": 30000},
    },
    "type": "n8n-nodes-base.httpRequest",
    "typeVersion": 4.2,
    "position": [500, 300],
    "id": "f71836ce-99ad-40ed-9668-807b927cc7ef",
    "name": "Tia Record Interactive Result",
    "retryOnFail": True,
    "maxTries": 3,
    "waitBetweenTries": 2000,
}
outbox["nodes"].extend([interactive_if, interactive_send, interactive_result])

connections = outbox["connections"]
connections["Expand Dispatches"] = {"main": [[{"node": "Interactive Message?", "type": "main", "index": 0}]]}
connections["Interactive Message?"] = {
    "main": [
        [{"node": "WhatsApp Send Interactive", "type": "main", "index": 0}],
        [{"node": "Template Message?", "type": "main", "index": 0}],
    ]
}
connections["WhatsApp Send Interactive"] = {"main": [[{"node": "Tia Record Interactive Result", "type": "main", "index": 0}]]}
outbox_path.write_text(json.dumps(outbox, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
