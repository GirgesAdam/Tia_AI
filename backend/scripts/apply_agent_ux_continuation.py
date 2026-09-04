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

    wrong_time = '''        "ambiguity instead of guessing. A numeric 24-hour clock value such as 02:00 is exact: preserve "\n        "02:00 and never reinterpret it as 14:00 just because clinic hours make 14:00 more plausible. "\n'''
    corrected_time = '''        "ambiguity instead of guessing. Resolve colloquial clock hours using normal clinic context: when a "\n        "customer says 'الساعة 2' without saying morning/night, prefer the plausible clinic-hours reading "\n        "(for example 14:00 when 02:00 is outside working hours). If they explicitly say '2 الفجر', AM/PM, "\n        "or an unambiguous 24-hour value, preserve that meaning. Never silently round an exact minute such as "\n        "14:07 to a nearby bookable slot. "\n'''
    if wrong_time in content:
        content = content.replace(wrong_time, corrected_time, 1)

    old_flow_rule = '''        "14:07 to a nearby bookable slot. "\n        "When the latest turn replaces a service or doctor in an active flow, action=modify and the newly "\n'''
    new_flow_rule = '''        "14:07 to a nearby bookable slot. When an active flow's latest turn changes a time constraint, the "\n        "latest meaning owns that constraint: use clear_entity_fields for any persisted exact/lower/upper "\n        "time bound that is no longer implied by the new turn. Do not keep an older opposite-side bound just "\n        "because it exists in workflow memory. "\n        "When the latest turn replaces a service or doctor in an active flow, action=modify and the newly "\n'''
    if old_flow_rule in content:
        content = content.replace(old_flow_rule, new_flow_rule, 1)

    _write(path, content)


def patch_clinic_grounding() -> None:
    path = "backend/app/agents/clinic_grounding.py"
    content = _read(path)
    marker = "service_relationship_doctor_discovery"
    if marker in content:
        return

    old = '''    selected_doctor_id = getattr(entity_hints, "doctor_id", None)\n    doctor_candidate_ids = list(getattr(entity_hints, "doctor_candidate_ids", []) or [])\n\n    if capability_set.intersection({"service_information", "pricing", "availability_discovery", "appointment_creation"}):\n'''
    new = '''    selected_doctor_id = getattr(entity_hints, "doctor_id", None)\n    doctor_candidate_ids = list(getattr(entity_hints, "doctor_candidate_ids", []) or [])\n\n    # service_relationship_doctor_discovery: the semantic interpreter decides that\n    # the customer is asking for doctors and grounds the service. Python then\n    # materializes the canonical service -> doctor relationship from the catalog;\n    # no customer wording is inspected and no lexical intent rule exists here.\n    if (\n        "doctor_discovery" in capability_set\n        and selected_doctor_id is None\n        and not doctor_candidate_ids\n        and selected_service_id\n    ):\n        service_row = _catalog_row_by_id(catalog, "services", selected_service_id)\n        known_doctor_ids = _catalog_ids(catalog, "doctors")\n        if service_row is not None:\n            doctor_candidate_ids = [\n                str(value)\n                for value in (service_row.get("doctor_ids") or [])\n                if str(value) in known_doctor_ids\n            ]\n\n    if capability_set.intersection({"service_information", "pricing", "availability_discovery", "appointment_creation"}):\n'''
    if old not in content:
        raise RuntimeError("clinic grounding patch anchor not found")
    content = content.replace(old, new, 1)
    _write(path, content)


def patch_grounded_response() -> None:
    path = "backend/app/agents/grounded_response.py"
    content = _read(path)
    marker = "appointment-specific booking prices"
    if marker in content:
        return

    old = '''            "- When availability_windows are provided, summarize those natural continuous windows "\n            "per doctor instead of listing dense quarter-hour slot starts.\\n"\n            "- If VERIFIED_DATA contains multiple candidate services/doctors/branches, present all "\n'''
    new = '''            "- When availability_windows are provided, summarize those natural continuous windows "\n            "per doctor instead of listing dense quarter-hour slot starts.\\n"\n            "- Slot-level prices in verified availability are appointment-specific booking prices. The service "\n            "catalog price is a general/base price. If they differ, do not present them as a contradiction or "\n            "quote both as if both apply to the same booking. If all relevant slots share one verified price, "\n            "use that price for the availability/booking answer; if prices vary, explain that they vary by "\n            "option and use only the verified slot prices.\\n"\n            "- If VERIFIED_DATA contains multiple candidate services/doctors/branches, present all "\n'''
    if old not in content:
        raise RuntimeError("grounded response patch anchor not found")
    content = content.replace(old, new, 1)
    _write(path, content)


def patch_live_runner() -> None:
    path = "backend/scripts/run_live_agent_ux_review.py"
    content = _read(path)

    wrong = '''    if name == "unavailable_exact_time":\n        return (\n            f"عايز أحجز {service_name} مع {doctor_name} يوم {date_text} الساعة 02:00",\n            "لو الوقت ده مش متاح متحجزش بداله، قولي بس أقرب وقت متاح",\n            lambda: (\n                (db.scalar(select(func.count(Appointment.id)).where(\n                    Appointment.workspace_id == workspace.id,\n                    Appointment.patient_id == patient.id,\n                )) or 0) == before_count,\n                "no_silent_time_substitution",\n            ),\n        )\n'''
    corrected = '''    if name == "unavailable_exact_time":\n        return (\n            f"عايز أحجز {service_name} مع {doctor_name} يوم {date_text} الساعة 14:07",\n            "لو 14:07 مش متاح متحجزش وقت قريب منه، قولي بس أقرب وقت متاح",\n            lambda: (\n                (db.scalar(select(func.count(Appointment.id)).where(\n                    Appointment.workspace_id == workspace.id,\n                    Appointment.patient_id == patient.id,\n                )) or 0) == before_count,\n                "no_silent_exact_minute_rounding",\n            ),\n        )\n'''
    if wrong in content:
        content = content.replace(wrong, corrected, 1)

    old_checks = '''        if name == "doctor_discovery":\n            second_reply = (result.turns[1].assistant or "") if len(result.turns) > 1 else ""\n            availability_answered = "متاح" in second_reply and any(token in second_reply for token in ("يوم", "من ", "الساعة"))\n            checks.append(f"closest_doctor_availability_answered={availability_answered}")\n            scenario_ok = scenario_ok and availability_answered\n'''
    new_checks = '''        if name == "availability_after_six":\n            second_reply = (result.turns[1].assistant or "") if len(result.turns) > 1 else ""\n            stale_lower_bound_absent = "من 6 م" not in second_reply\n            checks.append(f"new_time_constraint_replaced_old_bound={stale_lower_bound_absent}")\n            scenario_ok = scenario_ok and stale_lower_bound_absent\n        if name == "doctor_discovery":\n            first_reply = (result.turns[0].assistant or "") if result.turns else ""\n            second_reply = (result.turns[1].assistant or "") if len(result.turns) > 1 else ""\n            doctor_names_grounded = "مش ظاهرة" not in first_reply and "غير ظاهرة" not in first_reply\n            availability_answered = "متاح" in second_reply and any(token in second_reply for token in ("يوم", "من ", "الساعة"))\n            checks.append(f"doctor_names_grounded={doctor_names_grounded}")\n            checks.append(f"closest_doctor_availability_answered={availability_answered}")\n            scenario_ok = scenario_ok and doctor_names_grounded and availability_answered\n'''
    if old_checks not in content:
        raise RuntimeError("live runner doctor check anchor not found")
    content = content.replace(old_checks, new_checks, 1)

    old_service = '''        if name == "service_change_mid_flow":\n            second_reply = (result.turns[1].assistant or "") if len(result.turns) > 1 else ""\n            service_switch_ok = "بوت" in second_reply and "جنيه" in second_reply\n            checks.append(f"service_switch_acknowledged={service_switch_ok}")\n            scenario_ok = scenario_ok and service_switch_ok\n'''
    new_service = '''        if name == "service_change_mid_flow":\n            second_reply = (result.turns[1].assistant or "") if len(result.turns) > 1 else ""\n            service_switch_ok = "بوت" in second_reply and "جنيه" in second_reply\n            money_values = {\n                match.group(1).replace(",", "")\n                for match in re.finditer(r"([0-9][0-9,]*)\\s*(?:جنيه|EGP)", second_reply, re.I)\n            }\n            coherent_price = len(money_values) <= 1\n            checks.append(f"service_switch_acknowledged={service_switch_ok}")\n            checks.append(f"single_coherent_booking_price={coherent_price}")\n            scenario_ok = scenario_ok and service_switch_ok and coherent_price\n'''
    if old_service not in content:
        raise RuntimeError("live runner service price anchor not found")
    content = content.replace(old_service, new_service, 1)

    _write(path, content)


def main() -> None:
    patch_turn_interpreter()
    patch_clinic_grounding()
    patch_grounded_response()
    patch_live_runner()
    print("Agent UX continuation patch applied.")


if __name__ == "__main__":
    main()
