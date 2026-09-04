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
    wrong = '''        "ambiguity instead of guessing. A numeric 24-hour clock value such as 02:00 is exact: preserve "\n        "02:00 and never reinterpret it as 14:00 just because clinic hours make 14:00 more plausible. "\n'''
    corrected = '''        "ambiguity instead of guessing. Resolve colloquial clock hours using normal clinic context: when a "\n        "customer says 'الساعة 2' without saying morning/night, prefer the plausible clinic-hours reading "\n        "(for example 14:00 when 02:00 is outside working hours). If they explicitly say '2 الفجر', AM/PM, "\n        "or an unambiguous 24-hour value, preserve that meaning. Never silently round an exact minute such as "\n        "14:07 to a nearby bookable slot. "\n'''
    if wrong in content:
        content = content.replace(wrong, corrected, 1)
        _write(path, content)


def patch_live_runner() -> None:
    path = "backend/scripts/run_live_agent_ux_review.py"
    content = _read(path)
    wrong = '''    if name == "unavailable_exact_time":\n        return (\n            f"عايز أحجز {service_name} مع {doctor_name} يوم {date_text} الساعة 02:00",\n            "لو الوقت ده مش متاح متحجزش بداله، قولي بس أقرب وقت متاح",\n            lambda: (\n                (db.scalar(select(func.count(Appointment.id)).where(\n                    Appointment.workspace_id == workspace.id,\n                    Appointment.patient_id == patient.id,\n                )) or 0) == before_count,\n                "no_silent_time_substitution",\n            ),\n        )\n'''
    corrected = '''    if name == "unavailable_exact_time":\n        return (\n            f"عايز أحجز {service_name} مع {doctor_name} يوم {date_text} الساعة 14:07",\n            "لو 14:07 مش متاح متحجزش وقت قريب منه، قولي بس أقرب وقت متاح",\n            lambda: (\n                (db.scalar(select(func.count(Appointment.id)).where(\n                    Appointment.workspace_id == workspace.id,\n                    Appointment.patient_id == patient.id,\n                )) or 0) == before_count,\n                "no_silent_exact_minute_rounding",\n            ),\n        )\n'''
    if wrong in content:
        content = content.replace(wrong, corrected, 1)
        _write(path, content)


def main() -> None:
    patch_turn_interpreter()
    patch_live_runner()
    print("Agent UX continuation patch applied.")


if __name__ == "__main__":
    main()
