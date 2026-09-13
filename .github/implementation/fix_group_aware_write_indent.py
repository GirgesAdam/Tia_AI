from pathlib import Path

path = Path("backend/app/services/agent_v2/write_executor.py")
text = path.read_text(encoding="utf-8")

blocks = (
    ('elif intent.kind == "cancel_appointment":\n', '\nelif intent.kind == "reschedule":\n'),
    ('elif intent.kind == "reschedule":\n', '\n            elif intent.kind == "buy_package":\n'),
)

for marker, end_marker in blocks:
    start = text.find("\n" + marker)
    if start < 0:
        raise SystemExit(f"missing generated marker: {marker!r}")
    start += 1
    end = text.find(end_marker, start)
    if end < 0:
        raise SystemExit(f"missing generated block end: {end_marker!r}")
    block = text[start:end]
    block = "\n".join(("            " + line) if line else line for line in block.split("\n"))
    text = text[:start] + block + text[end:]

path.write_text(text, encoding="utf-8")
