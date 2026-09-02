from __future__ import annotations

from pathlib import Path
import re
import sys

INTERPRETER = Path("backend/app/agents/turn_interpreter.py")
AGENT_CHAT = Path("backend/app/services/agent_chat.py")
RUNNER = Path("backend/scripts/run_agent_problem_regression.py")
TEST = Path("backend/tests/test_agent_problem_regression_runner.py")

NEW_CASES = 'def _cases() -> list[FocusedCase]:\n    # Keep only the remaining compound-read failure plus nearby distinctions.\n    return [\n        FocusedCase(\n            "price_and_nearest_availability",\n            "remaining_problem",\n            "جلسة ليزر ابط بكام وأقرب ميعاد متاح إمتى؟",\n            _all(\n                _has("pricing", "availability_discovery"),\n                _lacks("appointment_creation"),\n                _entity("service_id", "underarm_service_id"),\n            ),\n        ),\n        FocusedCase(\n            "price_and_dated_availability",\n            "compound_inquiry",\n            "ليزر ابط بكام وإيه المواعيد المتاحة يوم السبت؟",\n            _all(\n                _has("pricing", "availability_discovery"),\n                _lacks("appointment_creation"),\n                _entity("service_id", "underarm_service_id"),\n                _date_present,\n            ),\n        ),\n        FocusedCase(\n            "price_and_time_window_availability",\n            "compound_inquiry",\n            "جلسة ليزر ابط بكام وفي مواعيد من ٦ لـ٨ بالليل؟",\n            _all(\n                _has("pricing", "availability_discovery"),\n                _lacks("appointment_creation"),\n                _entity("service_id", "underarm_service_id"),\n                _time_window(after="18:00", before="20:00"),\n            ),\n        ),\n        FocusedCase(\n            "service_details_price_and_availability",\n            "compound_inquiry",\n            "ليزر ابط مدته قد إيه وسعره كام وأقرب ميعاد متاح إمتى؟",\n            _all(\n                _has("service_information", "pricing", "availability_discovery"),\n                _lacks("appointment_creation"),\n                _entity("service_id", "underarm_service_id"),\n            ),\n        ),\n        FocusedCase(\n            "doctor_price_and_availability",\n            "compound_inquiry",\n            "جلسة ليزر ابط مع د احمد محمود بكام وأقرب ميعاد عنده إمتى؟",\n            _all(\n                _has("pricing", "availability_discovery"),\n                _lacks("appointment_creation"),\n                _entity("service_id", "underarm_service_id"),\n                _entity("doctor_id", "ahmed_doctor_id"),\n            ),\n        ),\n        FocusedCase(\n            "branch_price_and_availability",\n            "compound_inquiry",\n            "ليزر ابط في فرع مدينة نصر بكام وأقرب ميعاد متاح إمتى؟",\n            _all(\n                _has("pricing", "availability_discovery"),\n                _lacks("appointment_creation"),\n                _entity("service_id", "underarm_service_id"),\n            ),\n        ),\n        FocusedCase(\n            "price_then_explicit_nearest_booking",\n            "compound_booking",\n            "جلسة ليزر ابط بكام واحجزلي أقرب ميعاد متاح",\n            _all(\n                _has("pricing", "availability_discovery", "appointment_creation"),\n                _flow("start_booking"),\n                _entity("service_id", "underarm_service_id"),\n            ),\n        ),\n        FocusedCase(\n            "price_and_conditional_time_booking",\n            "compound_booking",\n            "ليزر ابط بكام ولو فيه ميعاد بعد ٧ بالليل احجزلي",\n            _all(\n                _has("pricing", "availability_discovery", "appointment_creation"),\n                _flow("start_booking"),\n                _entity("service_id", "underarm_service_id"),\n                _time_window(after="19:00"),\n            ),\n        ),\n    ]\n\n\n'
NEW_TEST = 'from pathlib import Path\n\n\ndef test_focused_runner_contains_only_current_compound_surface() -> None:\n    backend = Path(__file__).resolve().parent.parent\n    source = (backend / "scripts/run_agent_problem_regression.py").read_text(encoding="utf-8")\n\n    required = (\n        "price_and_nearest_availability",\n        "price_and_dated_availability",\n        "price_and_time_window_availability",\n        "service_details_price_and_availability",\n        "doctor_price_and_availability",\n        "branch_price_and_availability",\n        "price_then_explicit_nearest_booking",\n        "price_and_conditional_time_booking",\n    )\n    for case in required:\n        assert case in source\n\n    for clean_case in (\n        "nearest_availability_question",\n        "price_and_availability_question",\n        "package_comparison_reply_quality",\n        "availability_then_decide",\n        "doctor_availability_then_decide",\n        "explicit_conditional_booking",\n        "price_plus_explicit_booking",\n        "time_window_inquiry_with_service",\n        "time_window_booking_with_service",\n        "availability_without_service",\n    ):\n        assert clean_case not in source\n\n\ndef test_compound_reads_reuse_grounded_response_instead_of_slot_only_formatter() -> None:\n    backend = Path(__file__).resolve().parent.parent\n    source = (backend / "app/services/agent_chat.py").read_text(encoding="utf-8")\n\n    assert "slot_only_capabilities" in source\n    assert "set(policy.capabilities).issubset(slot_only_capabilities)" in source\n\n\ndef test_focused_runner_still_records_real_reply() -> None:\n    backend = Path(__file__).resolve().parent.parent\n    source = (backend / "scripts/run_agent_problem_regression.py").read_text(encoding="utf-8")\n\n    assert "run_agent_chat" in source\n    assert \'"reply": reply_text\' in source\n    assert \'"reply_model": reply_model\' in source\n    assert \'"no_unexpected_write": no_unexpected_write\' in source\n\n\ndef test_focused_runner_has_no_runtime_lexical_routing() -> None:\n    backend = Path(__file__).resolve().parent.parent\n    source = (backend / "scripts/run_agent_problem_regression.py").read_text(encoding="utf-8").lower()\n\n    assert "re.compile" not in source\n    assert "re.search" not in source\n    assert "re.match" not in source\n    assert "keyword" not in source\n'

BACKUPS = {
    INTERPRETER: Path("backend/app/agents/turn_interpreter.py.tia-v4.bak"),
    AGENT_CHAT: Path("backend/app/services/agent_chat.py.tia-v4.bak"),
    RUNNER: Path("backend/scripts/run_agent_problem_regression.py.tia-v4.bak"),
    TEST: Path("backend/tests/test_agent_problem_regression_runner.py.tia-v4.bak"),
}

SEMANTIC_MARKER = "Preserve every independently requested read capability on compound turns."
SLOT_MARKER = "slot_only_capabilities"


def update_interpreter(text: str) -> str:
    if SEMANTIC_MARKER in text:
        return text

    function_start = text.find("def interpret_customer_turn(")
    if function_start < 0:
        raise RuntimeError("Could not find interpret_customer_turn().")

    prompt_start = text.find("system = SystemMessage(", function_start)
    if prompt_start < 0:
        raise RuntimeError("Could not find the unified SystemMessage prompt.")

    active_flow_anchor = text.find(
        '            "For an active flow:',
        prompt_start,
    )
    if active_flow_anchor < 0:
        raise RuntimeError('Could not find the "For an active flow" prompt paragraph.')

    addition = (
        '            "Preserve every independently requested read capability on compound turns. "\\n'
        '            "If the latest customer turn asks for multiple facts or reads, include all capabilities needed "\\n'
        '            "to answer those parts together. Do not drop pricing, service information, availability, doctor "\\n'
        '            "information, or branch information merely because another requested read can already produce a "\\n'
        '            "useful response. A compound pricing + availability question remains read-only unless the customer "\\n'
        '            "separately authorizes creating/reserving an appointment.\\\\n\\\\n"\\n'
    )
    return text[:active_flow_anchor] + addition + text[active_flow_anchor:]


def update_agent_chat(text: str) -> str:
    if SLOT_MARKER in text:
        return text

    call_pos = text.rfind("verified_reply = _verified_booking_slots_reply(")
    if call_pos < 0:
        raise RuntimeError("Could not find the verified booking slots reply call.")

    search_start = max(0, call_pos - 1000)
    window = text[search_start:call_pos]
    old_guard = "                if prefetch_direct is None:\\n"
    rel_if = window.rfind(old_guard)
    if rel_if < 0:
        raise RuntimeError("Could not find the prefetch_direct guard before the slot formatter.")

    if_pos = search_start + rel_if
    new_guard = (
        '                slot_only_capabilities = {\\n'
        '                    "availability_discovery",\\n'
        '                    "appointment_creation",\\n'
        '                }\\n'
        '                if (\\n'
        '                    prefetch_direct is None\\n'
        '                    and set(policy.capabilities).issubset(slot_only_capabilities)\\n'
        '                ):\\n'
    )
    return text[:if_pos] + new_guard + text[if_pos + len(old_guard):]


def update_runner(text: str) -> str:
    pattern = re.compile(
        r"def _cases\\(\\) -> list\\[FocusedCase\\]:\\n.*?(?=def _semantic_expected\\()",
        re.DOTALL,
    )
    if not pattern.search(text):
        raise RuntimeError("Could not find focused runner _cases() block.")
    return pattern.sub(lambda _: NEW_CASES, text, count=1)


def validate(path: Path) -> None:
    compile(path.read_text(encoding="utf-8"), str(path), "exec")


def main() -> int:
    paths = (INTERPRETER, AGENT_CHAT, RUNNER, TEST)
    for path in paths:
        if not path.exists():
            print(f"ERROR: missing {path}. Run this file from the Tia repository root.", file=sys.stderr)
            return 2

    originals = {path: path.read_text(encoding="utf-8") for path in paths}

    try:
        updated = {
            INTERPRETER: update_interpreter(originals[INTERPRETER]),
            AGENT_CHAT: update_agent_chat(originals[AGENT_CHAT]),
            RUNNER: update_runner(originals[RUNNER]),
            TEST: NEW_TEST,
        }

        for path, backup in BACKUPS.items():
            if not backup.exists():
                backup.write_text(originals[path], encoding="utf-8", newline="\\n")

        for path, content in updated.items():
            path.write_text(content, encoding="utf-8", newline="\\n")

        for path in paths:
            validate(path)

    except Exception:
        for path, content in originals.items():
            path.write_text(content, encoding="utf-8", newline="\\n")
        raise

    print("Tia compound inquiry v4 applied successfully.")
    print("Changed only existing semantic + response-composition paths.")
    print("Focused suite now contains only the remaining compound problem surface.")
    print("Python syntax validation: OK")
    print("Keyword/regex customer routing added: no")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
