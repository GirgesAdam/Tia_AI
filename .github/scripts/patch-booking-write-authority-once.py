from pathlib import Path

path = Path("backend/app/services/agent_chat.py")
text = path.read_text(encoding="utf-8")
old = '''    if turn.action != "select_option":
        return None
    selected_doctor_id = getattr(turn.entity_hints, "doctor_id", None) or (
'''
new = '''    if turn.action != "select_option":
        return None
    # Persisted flow capability is workflow context, not fresh write consent.
    # A booking write requires the latest semantic turn itself to authorize
    # appointment creation. This prevents choosing a service/variant from being
    # mistaken for choosing a time from an older availability snapshot.
    if flow.flow_type == "booking" and "appointment_creation" not in {
        str(capability) for capability in turn.capabilities
    }:
        return None
    selected_doctor_id = getattr(turn.entity_hints, "doctor_id", None) or (
'''
if old not in text:
    raise SystemExit("target anchor not found or already patched")
path.write_text(text.replace(old, new, 1), encoding="utf-8")
