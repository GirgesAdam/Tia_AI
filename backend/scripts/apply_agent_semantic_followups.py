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


def main() -> None:
    patch_turn_interpreter()
    patch_clinic_grounding()
    patch_agent_chat()
    print("Semantic follow-up regression patch applied.")


if __name__ == "__main__":
    main()
