from pathlib import Path

# One-shot helper; removed by the workflow after applying the prompt clarification.
path = Path("backend/app/agents/turn_interpreter.py")
text = path.read_text(encoding="utf-8")
old = '''        "CUSTOMER DATA: past visits/services/payments for the current customer use customer_history. "\n'''
new = '''        "APPOINTMENT CONFIRMATION: use appointment_confirmation only when the customer wants a pending "\n        "appointment's status changed to confirmed. A phrase like 'confirm/tell me that...' asking whether a "\n        "booking has certain service/date/doctor details is a read-only fact question, not confirmation write "\n        "authorization; use the appropriate appointment/customer read capability instead. "\n\n        "CUSTOMER DATA: past visits/services/payments for the current customer use customer_history. "\n'''
if old not in text:
    raise SystemExit("target anchor not found or already patched")
path.write_text(text.replace(old, new, 1), encoding="utf-8")
