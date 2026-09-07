from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
TARGET = ROOT / "backend/app/agents/turn_interpreter.py"

OLD = '''            "Latest-turn consistency reminder: if presented booking/reschedule options exist and "\n            "the latest customer turn explicitly chooses one option or exact clock time and authorizes "\n            "the action, capture that choice in selection_index/selection_time or requested_start_time "\n            "and include the matching write capability. Never infer a choice the customer did not state.\\n\\n"\n'''

NEW = '''            "Latest-turn authority reminder: before inheriting any service, doctor, date, or time from "\n            "persisted workflow state, first ground every such entity explicitly stated in the latest "\n            "customer turn. Persisted values may fill only fields the latest turn leaves unchanged. In a "\n            "reschedule flow, appointment_reference identifies the existing appointment being changed, while "\n            "requested_date and requested_start_time are the replacement target.\\n\\n"\n            "Latest-turn consistency reminder: if presented booking/reschedule options exist and "\n            "the latest customer turn explicitly chooses one option or exact clock time and authorizes "\n            "the action, capture that choice in selection_index/selection_time or requested_start_time "\n            "and include the matching write capability. Never infer a choice the customer did not state.\\n\\n"\n'''


def main() -> int:
    text = TARGET.read_text(encoding="utf-8")
    count = text.count(OLD)
    if count != 1:
        raise RuntimeError(f"Expected one latest-turn reminder anchor, found {count}")
    TARGET.write_text(text.replace(OLD, NEW, 1), encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
