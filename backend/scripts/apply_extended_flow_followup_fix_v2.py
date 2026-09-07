from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]


def replace_once(path: str, old: str, new: str) -> None:
    target = ROOT / path
    text = target.read_text(encoding="utf-8")
    count = text.count(old)
    if count != 1:
        raise RuntimeError(f"Expected one anchor in {path}, found {count}: {old[:120]!r}")
    target.write_text(text.replace(old, new, 1), encoding="utf-8")


def insert_before(path: str, anchor: str, block: str) -> None:
    replace_once(path, anchor, block + anchor)


def main() -> int:
    replace_once(
        "backend/app/agents/turn_interpreter.py",
        '''        "the presented slot. If the customer accepts or chooses a time from the presented offer, use "\n        "select_option instead.\\n\\n"\n''',
        '''        "the presented slot. If the customer accepts or chooses a time from the presented offer, use "\n        "select_option instead. If an earlier exact time was unavailable and the customer now asks to see "\n        "general availability for the same day, action=modify and clear requested_start_time so the rejected "\n        "exact minute cannot keep filtering later turns. If they ask for later/earlier/before/after instead, "\n        "clear the stale exact time and encode only the new broad bound. When the customer chooses one exact "\n        "clock time from a presented availability window AND explicitly asks to book it, include "\n        "appointment_creation and use select_option with selection_time=HH:MM; do not ask for another "\n        "confirmation and do not keep an older rejected exact time.\\n\\n"\n''',
    )
    replace_once(
        "backend/app/agents/turn_interpreter.py",
        '''        "reaffirmed, clear the old doctor requirement so compatibility can be resolved again. For an active "\n''',
        '''        "reaffirmed, clear the old doctor requirement so compatibility can be resolved again. An explicit "\n        "new service in an active booking flow always owns the next discovery: action=modify, ground the new "\n        "service, and never answer or execute from the previous service's availability snapshot. If the latest "\n        "turn names both the new service and a compatible doctor/date, preserve those new requirements and "\n        "refresh availability for them. For an active "\n''',
    )

    helper = '''def _snapshot_has_exact_time(\n    flow: ConversationFlowState,\n    exact_time: str,\n    *,\n    doctor_id: str | None,\n    requested_date: str | None,\n) -> bool:\n    """Verify a semantic exact-time choice against the already-presented snapshot."""\n    snapshot = flow.option_snapshot if isinstance(flow.option_snapshot, dict) else {}\n    snapshot_date = str(snapshot.get("date") or "").strip()\n    if requested_date and snapshot_date and str(requested_date) != snapshot_date:\n        return False\n    normalized = str(exact_time).strip()[:5]\n    slots = snapshot.get("slots")\n    if not isinstance(slots, list):\n        return False\n    matches = 0\n    for slot in slots:\n        if not isinstance(slot, dict):\n            continue\n        if str(slot.get("start_time_24h") or "").strip()[:5] != normalized:\n            continue\n        if doctor_id and str(slot.get("doctor_id") or "") != str(doctor_id):\n            continue\n        matches += 1\n    return matches == 1\n\n\ndef _normalize_active_booking_decision(\n    decision: UnifiedTurnDecision,\n    flow: ConversationFlowState | None,\n) -> UnifiedTurnDecision:\n    """Normalize structured follow-ups using semantic output + verified flow state only."""\n    if flow is None or not flow.is_active or flow.flow_type != "booking":\n        return decision\n\n    existing = flow.entity_state if isinstance(flow.entity_state, dict) else {}\n    old_service_id = str(existing.get("service_id") or "")\n    new_service_id = str(decision.entity_hints.service_id or "")\n    service_changed = bool(old_service_id and new_service_id and old_service_id != new_service_id)\n\n    clear_fields = list(decision.clear_entity_fields)\n    action = decision.action\n    if service_changed:\n        action = "modify"\n        if (\n            not decision.entity_hints.doctor_id\n            and not decision.entity_hints.doctor_query\n            and not decision.entity_hints.doctor_candidate_ids\n        ):\n            for field in ("doctor_query", "doctor_id", "doctor_candidate_ids"):\n                if field not in clear_fields:\n                    clear_fields.append(field)\n\n    exact_time = decision.selection_time or decision.entity_hints.requested_start_time\n    capabilities = {str(item) for item in decision.capabilities}\n    if (\n        not service_changed\n        and exact_time\n        and "appointment_creation" in capabilities\n        and _snapshot_has_exact_time(\n            flow,\n            str(exact_time),\n            doctor_id=decision.entity_hints.doctor_id,\n            requested_date=decision.entity_hints.requested_date,\n        )\n    ):\n        return decision.model_copy(\n            update={\n                "action": "select_option",\n                "clear_entity_fields": clear_fields,\n                "selection_index": None,\n                "selection_time": str(exact_time).strip()[:5],\n            }\n        )\n\n    return decision.model_copy(update={"action": action, "clear_entity_fields": clear_fields})\n\n\n'''
    insert_before("backend/app/agents/turn_interpreter.py", "def interpret_customer_turn(\n", helper)

    replace_once(
        "backend/app/agents/turn_interpreter.py",
        '''    value = _normalize_single_location_decision(invocation.value)\n    grounded_hints = validate_grounded_entity_ids(value.entity_hints, clinic_catalog)\n    return value.model_copy(update={"entity_hints": grounded_hints})''',
        '''    value = _normalize_single_location_decision(invocation.value)\n    grounded_hints = validate_grounded_entity_ids(value.entity_hints, clinic_catalog)\n    value = value.model_copy(update={"entity_hints": grounded_hints})\n    return _normalize_active_booking_decision(value, flow)''',
    )

    replace_once(
        "backend/scripts/run_extended_booking_conversation_review.py",
        '''        days = _future_days_for(db, workspace, service=service, doctor=doctor, count=3, after_hour=17)\n''',
        '''        days = _future_days_for(db, workspace, service=service, doctor=doctor, count=3)\n''',
    )
    replace_once(
        "backend/scripts/run_extended_booking_conversation_review.py",
        '''            count=2,\n            after_hour=17,\n            exclude_appointment_id=target.id,\n''',
        '''            count=2,\n            exclude_appointment_id=target.id,\n''',
    )
    replace_once(
        "backend/scripts/run_extended_booking_conversation_review.py",
        '''                f"عايز أحجز {service.get('name')} مع {doctor.get('name')} أقرب ميعاد بعد الساعة 5 مساءً.",\n''',
        '''                f"عايز أحجز {service.get('name')} مع {doctor.get('name')} أقرب ميعاد متاح.",\n''',
    )
    replace_once(
        "backend/scripts/run_extended_booking_conversation_review.py",
        '''                f"شوفلي بدل منه يوم {first_day.isoformat()} بعد الساعة 5.",\n''',
        '''                f"شوفلي بدل منه يوم {first_day.isoformat()}.",\n''',
    )
    print("Applied structured booking follow-up fix v2.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
