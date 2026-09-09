from pathlib import Path

path = Path("backend/app/agents/turn_interpreter.py")
source = path.read_text(encoding="utf-8")
old = (
    '        "comparison; purchase when the customer wants to obtain/start a multi-session package; use_existing "\n'
    '        "when they explicitly want this appointment deducted from an existing package; avoid_existing when "\n'
    '        "they explicitly want a normal paid appointment instead. An existing package for one service must "\n'
)
new = (
    '        "comparison; purchase when the customer wants to obtain/start a multi-session package; use_existing "\n'
    '        "when they explicitly want this appointment deducted from an existing package; avoid_existing when "\n'
    '        "they explicitly want a normal paid appointment instead. For package_intent=purchase, capture "\n'
    '        "package_sessions_count only when the customer clearly chose 3, 6, or 9 sessions, and capture "\n'
    '        "laser_device_key only when they clearly chose a configured device. Include package_purchase for "\n'
    '        "a clear instruction to start/buy the package; package inquiry stays read-only. An existing package for one service must "\n'
)
count = source.count(old)
if count != 1:
    raise RuntimeError(f"Expected one package prompt marker, found {count}")
path.write_text(source.replace(old, new, 1), encoding="utf-8")
