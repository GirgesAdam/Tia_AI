from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]


def _read(path: str) -> str:
    return (ROOT / path).read_text(encoding="utf-8")


def _write(path: str, content: str) -> None:
    (ROOT / path).write_text(content, encoding="utf-8")


def patch_turn_interpreter() -> None:
    path = "backend/app/agents/turn_interpreter.py"
    content = _read(path)

    old = (
        '        "reschedule flow, a clear command to change the appointment now to one exact date/time uses "\n'
        '        "action=select_option and selection_time=HH:MM; a question about whether a time is possible is not "\n'
        '        "write authorization. A follow-up asking which previously listed doctor is available soon or earliest "\n'
        '        "uses availability_discovery for the referenced service; do not require the customer to choose a doctor "\n'
        '        "first when they explicitly asked you to compare availability.\\n\\n"\n'
    )
    new = (
        '        "reschedule flow, select_option is only for a replacement slot that the assistant already presented. "\n'
        '        "If the customer instead supplies a new exact target date/time in their own words and clearly commands "\n'
        '        "the change now, action=modify, keep appointment_reschedule, and put the exact target in requested_date "\n'
        '        "and requested_start_time. The backend will verify that target against real replacement availability "\n'
        '        "before any write. A question about whether a time is possible is not write authorization. "\n'
        '        "For reference resolution, phrases that refer to a doctor set from the immediately preceding exchange "\n'
        '        "must inherit the previously discussed grounded service when that service is unambiguous. If the latest "\n'
        '        "turn asks which/any of those compatible doctors is available soon, next, or earliest, use "\n'
        '        "availability_discovery for that service. Do not force one doctor: leave doctor_query, doctor_id, and "\n'
        '        "doctor_candidate_ids empty unless the latest turn actually singles out a doctor. The availability "\n'
        '        "adapter is responsible for comparing all compatible doctors.\\n\\n"\n'
    )
    if old not in content:
        if "select_option is only for a replacement slot" in content:
            return
        raise RuntimeError("turn interpreter semantic follow-up anchor not found")
    _write(path, content.replace(old, new, 1))


def patch_clinic_grounding() -> None:
    path = "backend/app/agents/clinic_grounding.py"
    content = _read(path)
    old = '''    if (\n        "doctor_discovery" in capability_set\n        and selected_doctor_id is None\n        and not doctor_candidate_ids\n        and selected_service_id\n    ):\n'''
    new = '''    if (\n        "doctor_discovery" in capability_set\n        and "availability_discovery" not in capability_set\n        and "appointment_creation" not in capability_set\n        and selected_doctor_id is None\n        and not doctor_candidate_ids\n        and selected_service_id\n    ):\n'''
    if old not in content:
        if 'and "availability_discovery" not in capability_set' in content:
            return
        raise RuntimeError("clinic grounding doctor discovery anchor not found")
    _write(path, content.replace(old, new, 1))


def patch_agent_chat() -> None:
    path = "backend/app/services/agent_chat.py"
    content = _read(path)
    old = '''            and flow_turn is not None\n            and flow_turn.action == "select_option"\n            and not turn_local_side_read\n        ):\n            payload = prefetched_results.get("get_reschedule_options")\n'''
    new = '''            and flow_turn is not None\n            and flow_turn.action in {"modify", "select_option"}\n            and not turn_local_side_read\n        ):\n            payload = prefetched_results.get("get_reschedule_options")\n'''
    if old not in content:
        if 'flow_turn.action in {"modify", "select_option"}' in content:
            return
        raise RuntimeError("agent chat reschedule exact-action anchor not found")
    _write(path, content.replace(old, new, 1))


def patch_live_runner() -> None:
    path = "backend/scripts/run_live_agent_ux_review.py"
    content = _read(path)

    if 'dest="cases"' not in content:
        old = '''    parser.add_argument("--workspace-slug", default="tia")\n    parser.add_argument("--report", default="artifacts/live-agent-ux-review.json")\n    return parser.parse_args()\n'''
        new = '''    parser.add_argument("--workspace-slug", default="tia")\n    parser.add_argument("--report", default="artifacts/live-agent-ux-review.json")\n    parser.add_argument("--case", dest="cases", action="append", default=None)\n    return parser.parse_args()\n'''
        if old not in content:
            raise RuntimeError("live runner args anchor not found")
        content = content.replace(old, new, 1)

    if "exclude_service_id: str | None = None" not in content:
        old = "def _booking_context(db: Session, workspace: Workspace):\n"
        new = '''def _booking_context(\n    db: Session,\n    workspace: Workspace,\n    *,\n    exclude_service_id: str | None = None,\n):\n'''
        if old not in content:
            raise RuntimeError("live runner booking context signature anchor not found")
        content = content.replace(old, new, 1)
        old = '''    for service in services:\n        service_id = str(service["id"])\n        compatible_doctors = [\n'''
        new = '''    for service in services:\n        service_id = str(service["id"])\n        if exclude_service_id and service_id == str(exclude_service_id):\n            continue\n        compatible_doctors = [\n'''
        if old not in content:
            raise RuntimeError("live runner service exclusion anchor not found")
        content = content.replace(old, new, 1)

    if 'name == "booked_slot_same_doctor"' not in content:
        anchor = '''    if name == "doctor_discovery":\n        return f"مين الدكاترة اللي بيعملوا {service_name}؟", "مين منهم متاح قريب؟", lambda: (True, "read_only")\n'''
        addition = '''    if name == "doctor_discovery":\n        return f"مين الدكاترة اللي بيعملوا {service_name}؟", "مين منهم متاح قريب؟", lambda: (True, "read_only")\n    if name == "booked_slot_same_doctor":\n        other_patient = db.scalar(\n            select(Patient)\n            .where(\n                Patient.workspace_id == workspace.id,\n                Patient.status != "blocked",\n                Patient.id != patient.id,\n            )\n            .order_by(Patient.created_at.asc())\n            .limit(1)\n        )\n        if other_patient is None:\n            raise RuntimeError("No second active patient available for occupied-slot fixture")\n        busy_slot = available.slots[len(available.slots) // 2]\n        busy_local = busy_slot.start_at.astimezone(local_tz)\n        busy = Appointment(\n            workspace_id=workspace.id,\n            patient_id=other_patient.id,\n            branch_id=UUID(str(busy_slot.branch_id)),\n            doctor_id=UUID(str(busy_slot.doctor_id)),\n            service_id=UUID(str(busy_slot.service_id)),\n            status="confirmed",\n            source="staff",\n            start_at=busy_slot.start_at,\n            end_at=busy_slot.end_at,\n            busy_start_at=busy_slot.start_at,\n            busy_end_at=busy_slot.end_at,\n            duration_minutes=busy_slot.duration_minutes,\n            price_minor=busy_slot.price_minor,\n            currency=busy_slot.currency,\n            payment_status="unpaid",\n            payment_method="unknown",\n            billing_context="standard",\n            confirmed_at=datetime.now(UTC),\n        )\n        db.add(busy)\n        db.flush()\n        return (\n            f"مواعيد {service_name} مع {doctor_name} يوم {date_text} إيه؟",\n            f"تمام احجزلي مع نفس الدكتور يوم {date_text} الساعة {busy_local.strftime('%H:%M')}",\n            lambda: (\n                busy.status == "confirmed"\n                and (db.scalar(select(func.count(Appointment.id)).where(\n                    Appointment.workspace_id == workspace.id,\n                    Appointment.patient_id == patient.id,\n                )) or 0) == before_count,\n                "occupied_slot_preserved_and_not_double_booked",\n            ),\n        )\n'''
        if anchor not in content:
            raise RuntimeError("live runner busy-slot scenario anchor not found")
        content = content.replace(anchor, addition, 1)

    old_service_case = '''    if name == "service_change_mid_flow":\n        return f"عايز أحجز {service_name} يوم {date_text}", "لا غيرت رأيي، عايز بوتوكس بدل الليزر. بكام ومواعيده إيه؟ ومتحجزش حاجة دلوقتي", lambda: (((db.scalar(select(func.count(Appointment.id)).where(Appointment.workspace_id == workspace.id, Appointment.patient_id == patient.id)) or 0) == before_count), "no_stale_booking")\n'''
    if old_service_case in content:
        new_service_case = '''    if name == "service_change_mid_flow":\n        _, alternate_service, _, _, alternate_day, _ = _booking_context(\n            db,\n            workspace,\n            exclude_service_id=str(service["id"]),\n        )\n        alternate_name = str(alternate_service.get("name") or "الخدمة التانية")\n        return (\n            f"عايز أحجز {service_name} يوم {date_text}",\n            f"لا غيرت رأيي، عايز {alternate_name} بدل الخدمة الأولى. بكام ومواعيده يوم {alternate_day.isoformat()}؟ ومتحجزش حاجة دلوقتي",\n            lambda: (((db.scalar(select(func.count(Appointment.id)).where(Appointment.workspace_id == workspace.id, Appointment.patient_id == patient.id)) or 0) == before_count), "no_stale_booking"),\n        )\n'''
        content = content.replace(old_service_case, new_service_case, 1)

    old_service_check = '''        if name == "service_change_mid_flow":\n            second_reply = (result.turns[1].assistant or "") if len(result.turns) > 1 else ""\n            service_switch_ok = "بوت" in second_reply and "جنيه" in second_reply\n            money_values = {\n                match.group(1).replace(",", "")\n                for match in re.finditer(r"([0-9][0-9,]*)\\s*(?:جنيه|EGP)", second_reply, re.I)\n            }\n            coherent_price = len(money_values) <= 1\n            checks.append(f"service_switch_acknowledged={service_switch_ok}")\n            checks.append(f"single_coherent_booking_price={coherent_price}")\n            scenario_ok = scenario_ok and service_switch_ok and coherent_price\n'''
    if old_service_check in content:
        new_service_check = '''        if name == "service_change_mid_flow":\n            second_reply = (result.turns[1].assistant or "") if len(result.turns) > 1 else ""\n            compound_read_answered = "جنيه" in second_reply and ("من " in second_reply or "متاح" in second_reply)\n            money_values = {\n                match.group(1).replace(",", "")\n                for match in re.finditer(r"([0-9][0-9,]*)\\s*(?:جنيه|EGP)", second_reply, re.I)\n            }\n            coherent_price = len(money_values) <= 1\n            checks.append(f"service_switch_read_answered={compound_read_answered}")\n            checks.append(f"single_coherent_booking_price={coherent_price}")\n            scenario_ok = scenario_ok and compound_read_answered and coherent_price\n'''
        content = content.replace(old_service_check, new_service_check, 1)

    if '"booked_slot_same_doctor",' not in content:
        old = '''            "availability_window", "doctor_discovery", "mixed_language", "service_change_mid_flow",\n'''
        new = '''            "availability_window", "doctor_discovery", "booked_slot_same_doctor", "mixed_language", "service_change_mid_flow",\n'''
        if old not in content:
            raise RuntimeError("live runner case dispatch anchor not found")
        content = content.replace(old, new, 1)

        old = '''        if name in {"general_availability_ranges", "doctor_availability_ranges", "book_from_window", "unavailable_exact_time", "availability_after_six", "availability_window", "mixed_language", "service_change_mid_flow"}:\n'''
        new = '''        if name in {"general_availability_ranges", "doctor_availability_ranges", "book_from_window", "unavailable_exact_time", "availability_after_six", "availability_window", "booked_slot_same_doctor", "mixed_language", "service_change_mid_flow"}:\n'''
        if old not in content:
            raise RuntimeError("live runner natural windows anchor not found")
        content = content.replace(old, new, 1)

        old = '''        if name == "privacy":\n            privacy_ok = any(token in replies for token in ("خصوص", "مينفع", "مش مسموح", "ماقدرش", "مقدرش", "بيانات"))\n'''
        new = '''        if name == "booked_slot_same_doctor":\n            second_reply = (result.turns[1].assistant or "") if len(result.turns) > 1 else ""\n            no_false_confirmation = not any(token in second_reply for token in ("تم الحجز", "اتحجز", "حجزتلك"))\n            checks.append(f"no_false_busy_slot_confirmation={no_false_confirmation}")\n            scenario_ok = scenario_ok and no_false_confirmation\n        if name == "privacy":\n            privacy_ok = any(token in replies for token in ("خصوص", "مينفع", "مش مسموح", "ماقدرش", "مقدرش", "بيانات"))\n'''
        if old not in content:
            raise RuntimeError("live runner busy-slot check anchor not found")
        content = content.replace(old, new, 1)

    if 'names = args.cases or default_names' not in content:
        old = '''    names = [\n        "price_duration", "general_availability_ranges", "doctor_availability_ranges",\n        "book_from_window", "unavailable_exact_time", "availability_after_six",\n        "availability_window", "cancel_unique", "cancel_ambiguous", "reschedule_unique",\n        "reschedule_ambiguous", "list_appointments", "doctor_discovery", "package_remaining",\n        "package_compare", "package_refund", "history", "medical_handoff", "privacy", "mixed_language",\n        "service_change_mid_flow",\n    ]\n'''
        new = '''    default_names = [\n        "price_duration", "general_availability_ranges", "doctor_availability_ranges",\n        "book_from_window", "unavailable_exact_time", "availability_after_six",\n        "availability_window", "cancel_unique", "cancel_ambiguous", "reschedule_unique",\n        "reschedule_ambiguous", "list_appointments", "doctor_discovery", "booked_slot_same_doctor",\n        "package_remaining", "package_compare", "package_refund", "history", "medical_handoff",\n        "privacy", "mixed_language", "service_change_mid_flow",\n    ]\n    names = args.cases or default_names\n'''
        if old not in content:
            raise RuntimeError("live runner names anchor not found")
        content = content.replace(old, new, 1)

    _write(path, content)


def main() -> None:
    patch_turn_interpreter()
    patch_clinic_grounding()
    patch_agent_chat()
    patch_live_runner()
    print("Semantic follow-up regression patch applied.")


if __name__ == "__main__":
    main()
