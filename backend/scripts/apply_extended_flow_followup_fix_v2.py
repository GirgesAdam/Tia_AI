from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]


def replace_once(path: str, old: str, new: str) -> None:
    target = ROOT / path
    text = target.read_text(encoding="utf-8")
    count = text.count(old)
    if count != 1:
        raise RuntimeError(f"Expected one anchor in {path}, found {count}: {old[:140]!r}")
    target.write_text(text.replace(old, new, 1), encoding="utf-8")


def main() -> int:
    replace_once(
        "backend/app/agents/turn_interpreter.py",
        '''        "clock time from a presented availability window AND explicitly asks to book it, include "\n        "appointment_creation and use select_option with selection_time=HH:MM; do not ask for another "\n        "confirmation and do not keep an older rejected exact time.\\n\\n"\n''',
        '''        "clock time from a presented availability window AND explicitly asks to book it, include "\n        "appointment_creation and use select_option with selection_time=HH:MM; do not ask for another "\n        "confirmation and do not keep an older rejected exact time. This remains true even when the persisted "\n        "booking flow currently lists availability_discovery only; the latest explicit booking command owns "\n        "the capability for that turn.\\n\\n"\n''',
    )

    replace_once(
        "backend/app/agents/turn_interpreter.py",
        '''    if (\n        not service_changed\n        and exact_time\n        and "appointment_creation" in capabilities\n        and _snapshot_has_exact_time(\n            flow,\n            str(exact_time),\n            doctor_id=decision.entity_hints.doctor_id,\n            requested_date=decision.entity_hints.requested_date,\n        )\n    ):\n        return decision.model_copy(\n            update={\n                "action": "select_option",\n                "clear_entity_fields": clear_fields,\n                "selection_index": None,\n                "selection_time": str(exact_time).strip()[:5],\n            }\n        )\n\n    return decision.model_copy(update={"action": action, "clear_entity_fields": clear_fields})\n''',
        '''    exact_choice_is_in_snapshot = bool(\n        not service_changed\n        and exact_time\n        and "appointment_creation" in capabilities\n        and _snapshot_has_exact_time(\n            flow,\n            str(exact_time),\n            doctor_id=decision.entity_hints.doctor_id,\n            requested_date=decision.entity_hints.requested_date,\n        )\n    )\n    if exact_choice_is_in_snapshot:\n        return decision.model_copy(\n            update={\n                "action": "select_option",\n                "clear_entity_fields": clear_fields,\n                "selection_index": None,\n                "selection_time": str(exact_time).strip()[:5],\n            }\n        )\n\n    if (\n        not service_changed\n        and exact_time\n        and "appointment_creation" in capabilities\n        and decision.action == "select_option"\n    ):\n        # The customer authorized one exact booking time, but the current snapshot\n        # is empty or no longer represents that choice. Re-run exact availability\n        # through the normal modify/read path in this same turn; do not inspect text\n        # and do not guess from an older snapshot.\n        for field in ("not_before_time", "not_after_time"):\n            if field not in clear_fields:\n                clear_fields.append(field)\n        return decision.model_copy(\n            update={\n                "action": "modify",\n                "clear_entity_fields": clear_fields,\n                "selection_index": None,\n                "selection_time": None,\n            }\n        )\n\n    return decision.model_copy(update={"action": action, "clear_entity_fields": clear_fields})\n''',
    )

    replace_once(
        "backend/scripts/run_extended_booking_conversation_review.py",
        '''                f"قصدي الميعاد اللي يوم {target_local.date().isoformat()}.",\n''',
        '''                f"قصدي الميعاد اللي يوم {target_local.date().isoformat()} الساعة {target_local.strftime('%H:%M')}.",\n''',
    )

    print("Applied minimal exact-time recheck fix and clarified the two-appointment fixture.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
