from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]


def replace_once(path: str, old: str, new: str) -> None:
    target = ROOT / path
    text = target.read_text(encoding="utf-8")
    count = text.count(old)
    if count != 1:
        raise RuntimeError(f"Expected one anchor in {path}, found {count}: {old[:160]!r}")
    target.write_text(text.replace(old, new, 1), encoding="utf-8")


def main() -> int:
    replace_once(
        "backend/app/agents/turn_interpreter.py",
        '''            "Recent conversation for reference resolution only:\\n"\n            f"{_recent_conversation_excerpt(history)}\\n\\n"\n            "Latest customer turn (authoritative):\\n"\n            f"{_latest_customer_turn(history)}"\n''',
        '''            "Recent conversation for reference resolution only:\\n"\n            f"{_recent_conversation_excerpt(history)}\\n\\n"\n            "Latest-turn consistency reminder: if presented booking/reschedule options exist and "\n            "the latest customer turn explicitly chooses one option or exact clock time and authorizes "\n            "the action, capture that choice in selection_index/selection_time or requested_start_time "\n            "and include the matching write capability. Never infer a choice the customer did not state.\\n\\n"\n            "Latest customer turn (authoritative):\\n"\n            f"{_latest_customer_turn(history)}"\n''',
    )

    replace_once(
        "backend/scripts/run_extended_booking_conversation_review.py",
        '''                f"شوفلي {second_service.get('name')} مع {second_doctor.get('name')} يوم {second_day.isoformat()}.",\n                f"الساعة {final_time} مناسبة، احجزها.",\n                "أكدلي إن الحجز للخدمة الجديدة مش الأولى.",\n''',
        '''                f"شوفلي {second_service.get('name')} مع {second_doctor.get('name')} يوم {second_day.isoformat()}.",\n                f"عايز النسخة اللي مدتها {int(second_service.get('duration_minutes') or 0)} دقيقة.",\n                f"الساعة {final_time} مناسبة، احجزها.",\n                "أكدلي إن الحجز للخدمة الجديدة مش الأولى.",\n''',
    )

    print("Applied latest-turn selection reminder and completed the ambiguous-service fixture.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
