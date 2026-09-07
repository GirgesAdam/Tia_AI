from __future__ import annotations

from pathlib import Path

path = Path(__file__).with_name("apply_daily_review_product_fixes.py")
text = path.read_text(encoding="utf-8")

text = text.replace(
    '''    if text.count(old) != 1:\n        raise RuntimeError(f"Expected exactly one anchor in {path}, found {text.count(old)}")\n    target.write_text(text.replace(old, new, 1), encoding="utf-8")\n''',
    '''    target.write_text(text.replace(old, new, 1), encoding="utf-8")\n''',
)

old_block = '''    replace_once(\n        "backend/app/agents/turn_interpreter.py",\n        ''' + "'''" + '''        "For an active reschedule flow, select_option is only for a replacement slot that the assistant already presented. "\\n        "If the customer instead supplies a new exact target date/time in their own words and clearly commands "\\n        "the change now, action=modify, keep appointment_reschedule, and put the exact target in requested_date "\\n''' + "'''" + ''',\n        ''' + "'''" + '''        "For an active reschedule flow, select_option is only for a replacement slot that the assistant already presented. "\\n        "If the customer instead supplies a new exact target date/time in their own words and clearly commands "\\n        "the change now, action MUST be modify (never continue and never ask for a second confirmation), keep "\\n        "appointment_reschedule, and put the exact target in requested_date "\\n''' + "'''" + ''',\n    )\n'''

new_block = '''    replace_once(\n        "backend/app/agents/turn_interpreter.py",\n        '        "the change now, action=modify, keep appointment_reschedule, and put the exact target in requested_date "\\n',\n        '        "the change now, action MUST be modify (never continue and never ask for a second confirmation), keep "\\n'\n        '        "appointment_reschedule, and put the exact target in requested_date "\\n',\n    )\n'''

if old_block not in text:
    raise RuntimeError("Could not find reschedule patch block to repair")
text = text.replace(old_block, new_block, 1)
path.write_text(text, encoding="utf-8")
compile(text, str(path), "exec")
print("Repaired daily review patcher.")
