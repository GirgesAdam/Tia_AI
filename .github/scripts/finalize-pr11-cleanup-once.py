from pathlib import Path

agent_chat = Path("backend/app/services/agent_chat.py")
text = agent_chat.read_text(encoding="utf-8")
old = 'if not appointment_id and flow is not None and flow.flow_type == "appointment_reschedule":'
new = 'if not appointment_id and flow is not None and getattr(flow, "flow_type", None) == "appointment_reschedule":'
if old not in text:
    raise SystemExit("agent_chat flow_type anchor not found or already patched")
agent_chat.write_text(text.replace(old, new, 1), encoding="utf-8")

extended = Path("backend/scripts/run_extended_booking_conversation_review.py")
text = extended.read_text(encoding="utf-8")
case_line = '    "reschedule_two_appointments_choose_one",\n'
if case_line not in text:
    raise SystemExit("unwanted conversation case not found or already removed")
extended.write_text(text.replace(case_line, "", 1), encoding="utf-8")

obsolete = [
    ".github/workflows/apply-extended-flow-followup-fix.yml",
    ".github/workflows/apply-extended-flow-followup-fix-v2.yml",
    ".github/workflows/booking-followup-diagnostic.yml",
    "backend/scripts/apply_extended_flow_followup_fix.py",
    "backend/scripts/apply_extended_flow_followup_fix_v2.py",
    "backend/scripts/apply_single_active_package_rule.py",
    "backend/scripts/apply_single_active_package_rule_v2.py",
    "backend/scripts/run_booking_followup_diagnostic.py",
]
for name in obsolete:
    path = Path(name)
    if path.exists():
        path.unlink()
