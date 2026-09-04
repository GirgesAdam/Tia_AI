from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]


def _read(path: str) -> str:
    return (ROOT / path).read_text(encoding="utf-8")


def _write(path: str, content: str) -> None:
    (ROOT / path).write_text(content, encoding="utf-8")


def _replace_once(content: str, old: str, new: str, *, label: str) -> str:
    count = content.count(old)
    if count != 1:
        raise RuntimeError(f"{label}: expected exactly one match, found {count}")
    return content.replace(old, new, 1)


def patch_turn_interpreter() -> None:
    path = "backend/app/agents/turn_interpreter.py"
    content = _read(path)
    old = '''        "ambiguity instead of guessing.\\n\\n"\n'''
    new = '''        "ambiguity instead of guessing. Resolve colloquial clock hours using normal clinic context: when a "\n        "customer says 'الساعة 2' without saying morning/night, prefer the plausible clinic-hours reading "\n        "(for example 14:00 when 02:00 is outside working hours). If they explicitly say '2 الفجر', AM/PM, "\n        "or an unambiguous 24-hour value, preserve that meaning. Never silently round an exact minute such as "\n        "14:07 to a nearby bookable slot. When the latest turn replaces a service or doctor in an active flow, "\n        "action=modify and the newly grounded entity owns the requirement. If a service changes and the old "\n        "doctor was not explicitly reaffirmed, clear the old doctor requirement so compatibility can be resolved "\n        "again. For an active reschedule flow, a clear command to change the appointment now to one exact "\n        "date/time uses action=select_option and selection_time=HH:MM; a question about whether a time is possible "\n        "is not write authorization. A follow-up asking which previously listed doctor is available soon or earliest "\n        "uses availability_discovery for the referenced service; do not require the customer to choose a doctor "\n        "first when they explicitly asked you to compare availability.\\n\\n"\n'''
    content = _replace_once(content, old, new, label="contextual time and active-flow semantics")
    _write(path, content)


def patch_agent_chat() -> None:
    path = "backend/app/services/agent_chat.py"
    content = _read(path)

    old_header = '''def _exact_booking_selection_index(\n    *,\n    decision: SemanticCapabilityDecision,\n    payload: dict[str, object],\n) -> int | None:\n    """Return one verified slot index for an explicit exact-time booking request.\n\n    This is deliberately structural, not lexical: the interpreter has already\n    classified the newest turn as appointment creation and extracted an exact\n    date/time. If exactly one adapter-verified slot matches that clock time, no\n    second confirmation turn is needed. Ambiguous or multi-option requests keep\n    the normal option-selection flow.\n    """\n    if "appointment_creation" not in set(decision.capabilities):\n        return None\n'''
    new_header = '''def _exact_action_selection_index(\n    *,\n    decision: SemanticCapabilityDecision,\n    payload: dict[str, object],\n    required_capability: str,\n) -> int | None:\n    """Return one verified slot index for one semantically authorized exact-time action.\n\n    The interpreter owns intent; Python only verifies that the exact structured\n    clock time maps to exactly one adapter slot before a write can execute.\n    """\n    if required_capability not in set(decision.capabilities):\n        return None\n'''
    content = _replace_once(content, old_header, new_header, label="generic exact slot verifier")

    content = _replace_once(
        content,
        '''def _exact_booking_flow_turn(\n    decision: SemanticCapabilityDecision,\n''',
        '''def _exact_action_flow_turn(\n    decision: SemanticCapabilityDecision,\n''',
        label="generic exact action turn name",
    )
    content = _replace_once(
        content,
        '''    """Convert an already-structured exact booking request into a slot choice."""\n''',
        '''    """Convert an already-structured exact appointment action into a verified slot choice."""\n''',
        label="generic exact action turn doc",
    )
    content = _replace_once(
        content,
        '''            "The current turn explicitly requests appointment creation at an exact "\n            "date/time and exactly one verified adapter slot matches it."\n''',
        '''            "The current turn semantically authorizes an appointment action at an exact "\n            "date/time and exactly one verified adapter slot matches it."\n''',
        label="generic exact action reason",
    )

    content = _replace_once(
        content,
        '''                selection_index = _exact_booking_selection_index(\n                    decision=semantic_decision,\n                    payload=payload,\n                )\n''',
        '''                selection_index = _exact_action_selection_index(\n                    decision=semantic_decision,\n                    payload=payload,\n                    required_capability="appointment_creation",\n                )\n''',
        label="booking exact verifier call",
    )
    content = _replace_once(
        content,
        '''                        turn=_exact_booking_flow_turn(\n                            semantic_decision,\n                            selection_index=selection_index,\n                        ),\n''',
        '''                        turn=_exact_action_flow_turn(\n                            semantic_decision,\n                            selection_index=selection_index,\n                        ),\n''',
        label="booking exact turn call",
    )

    package_anchor = '''\n        if (\n            prefetch_direct is None\n            and "package_refund_quote" not in policy.capabilities\n'''
    reschedule_block = '''\n        if (\n            prefetch_direct is None\n            and flow is not None\n            and flow.is_active\n            and flow.flow_type == "appointment_reschedule"\n            and flow_turn is not None\n            and flow_turn.action == "select_option"\n            and not turn_local_side_read\n        ):\n            payload = prefetched_results.get("get_reschedule_options")\n            if isinstance(payload, dict):\n                selection_index = _exact_action_selection_index(\n                    decision=semantic_decision,\n                    payload=payload,\n                    required_capability="appointment_reschedule",\n                )\n                if selection_index is not None:\n                    flow = _sync_flow_from_verified_prefetch(\n                        db=db,\n                        flow=flow,\n                        prefetched_results=prefetched_results,\n                        run_id=run_id,\n                    )\n                    prefetch_direct = _structured_flow_write(\n                        db=db,\n                        flow=flow,\n                        turn=_exact_action_flow_turn(\n                            semantic_decision,\n                            selection_index=selection_index,\n                        ),\n                        policy=policy,\n                        tool_context=tool_context,\n                        run_id=run_id,\n                    )\n\n        if (\n            prefetch_direct is None\n            and "package_refund_quote" not in policy.capabilities\n'''
    content = _replace_once(content, package_anchor, reschedule_block, label="exact reschedule execution")
    _write(path, content)


def patch_live_runner() -> None:
    path = "backend/scripts/run_live_agent_ux_review.py"
    content = _read(path)

    content = _replace_once(
        content,
        '''Twenty short two-turn conversations run against the real LLM + PostgreSQL adapter.\n''',
        '''Twenty-one short two-turn conversations run against the real LLM + PostgreSQL adapter.\n''',
        label="review count doc",
    )

    old_unavailable = '''    if name == "unavailable_exact_time":\n        return f"عايز {service_name} مع {doctor_name} يوم {date_text} الساعة 02:00", "مش هاحجز دلوقتي، قولي بس أقرب وقت متاح", lambda: (True, "read_only")\n'''
    new_unavailable = '''    if name == "unavailable_exact_time":\n        return (\n            f"عايز أحجز {service_name} مع {doctor_name} يوم {date_text} الساعة 14:07",\n            "لو 14:07 مش متاح متحجزش وقت قريب منه، قولي بس أقرب وقت متاح",\n            lambda: (\n                (db.scalar(select(func.count(Appointment.id)).where(\n                    Appointment.workspace_id == workspace.id,\n                    Appointment.patient_id == patient.id,\n                )) or 0) == before_count,\n                "no_silent_exact_minute_rounding",\n            ),\n        )\n'''
    content = _replace_once(content, old_unavailable, new_unavailable, label="no silent exact-minute rounding")

    content = _replace_once(
        content,
        '''        return f"عايز أحجز {service_name} يوم {date_text}", "لا غيرت رأيي، عايز بوتوكس بدل الليزر ومتحجزش حاجة دلوقتي", lambda: (((db.scalar(select(func.count(Appointment.id)).where(Appointment.workspace_id == workspace.id, Appointment.patient_id == patient.id)) or 0) == before_count), "no_stale_booking")\n''',
        '''        return f"عايز أحجز {service_name} يوم {date_text}", "لا غيرت رأيي، عايز بوتوكس بدل الليزر. بكام ومواعيده إيه؟ ومتحجزش حاجة دلوقتي", lambda: (((db.scalar(select(func.count(Appointment.id)).where(Appointment.workspace_id == workspace.id, Appointment.patient_id == patient.id)) or 0) == before_count), "no_stale_booking")\n''',
        label="observable service switch conversation",
    )

    content = _replace_once(
        content,
        '''        if name in {"general_availability_ranges", "doctor_availability_ranges", "book_from_window", "unavailable_exact_time", "availability_after_six", "availability_window", "mixed_language"}:\n''',
        '''        if name in {"general_availability_ranges", "doctor_availability_ranges", "book_from_window", "unavailable_exact_time", "availability_after_six", "availability_window", "mixed_language", "service_change_mid_flow"}:\n''',
        label="service switch natural availability check",
    )

    anchor = '''        if name in {"availability_window", "service_change_mid_flow"}:\n            no_false_medical_handoff = not any(\n                token in replies for token in ("الفريق الطبي", "تحويل المحادثة", "حوّلت المحادثة")\n            )\n            checks.append(f"no_false_medical_handoff={no_false_medical_handoff}")\n            scenario_ok = scenario_ok and no_false_medical_handoff\n'''
    expanded = '''        if name in {"availability_window", "service_change_mid_flow"}:\n            no_false_medical_handoff = not any(\n                token in replies for token in ("الفريق الطبي", "تحويل المحادثة", "حوّلت المحادثة")\n            )\n            checks.append(f"no_false_medical_handoff={no_false_medical_handoff}")\n            scenario_ok = scenario_ok and no_false_medical_handoff\n        if name == "service_change_mid_flow":\n            second_reply = (result.turns[1].assistant or "") if len(result.turns) > 1 else ""\n            service_switch_ok = "بوت" in second_reply and "جنيه" in second_reply\n            checks.append(f"service_switch_acknowledged={service_switch_ok}")\n            scenario_ok = scenario_ok and service_switch_ok\n        if name == "doctor_discovery":\n            second_reply = (result.turns[1].assistant or "") if len(result.turns) > 1 else ""\n            availability_answered = "متاح" in second_reply and any(token in second_reply for token in ("يوم", "من ", "الساعة"))\n            checks.append(f"closest_doctor_availability_answered={availability_answered}")\n            scenario_ok = scenario_ok and availability_answered\n'''
    content = _replace_once(content, anchor, expanded, label="truthful flow-switch and doctor checks")
    _write(path, content)


def main() -> None:
    patch_turn_interpreter()
    patch_agent_chat()
    patch_live_runner()
    print("Agent UX continuation patch applied.")


if __name__ == "__main__":
    main()
