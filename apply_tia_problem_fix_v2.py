from __future__ import annotations

from pathlib import Path
import re
import sys

INTERPRETER = Path("backend/app/agents/turn_interpreter.py")
AGENT_CHAT = Path("backend/app/services/agent_chat.py")
RUNNER = Path("backend/scripts/run_agent_problem_regression.py")
TEST = Path("backend/tests/test_agent_problem_regression_runner.py")

OLD_PROMPT = '            "are available and has not asked to reserve one. An appointment_creation request normally also needs "\n'
NEW_PROMPT = '            "are available and has not asked to reserve one. Asking for availability stays read-only even when it is combined "\n            "with service details, a price question, or a requested date/time. Do not infer appointment_creation from "\n            "availability_discovery itself. An appointment_creation request normally also needs "\n'
OLD_BOOKING_SIG = 'def _verified_booking_slots_reply(payload: dict[str, object]) -> str | None:'
NEW_BOOKING_SIG = 'def _verified_booking_slots_reply(\n    payload: dict[str, object],\n    *,\n    booking_authorized: bool,\n) -> str | None:'
OLD_BOOKING_RETURN = '    return intro + "\\n" + "\\n".join(presented) + "\\nاختار رقم الميعاد المناسب ليك."'
NEW_BOOKING_RETURN = '    closing = (\n        "اختار رقم الميعاد المناسب ليك."\n        if booking_authorized\n        else "لو حابب تحجز واحد من المواعيد دي، قولي رقمه."\n    )\n    return intro + "\\n" + "\\n".join(presented) + "\\n" + closing'
OLD_BOOKING_CALL = '                    verified_reply = _verified_booking_slots_reply(payload)'
NEW_BOOKING_CALL = '                    verified_reply = _verified_booking_slots_reply(\n                        payload,\n                        booking_authorized="appointment_creation" in set(policy.capabilities),\n                    )'
OLD_PACKAGE_SIG = 'def _verified_package_intent_reply(*, intent: str, package_payload: dict[str, object] | None) -> str | None:'
NEW_PACKAGE_SIG = 'def _verified_package_intent_reply(\n    *,\n    intent: str,\n    package_payload: dict[str, object] | None,\n    catalog_payload: dict[str, object] | None = None,\n) -> str | None:'
PACKAGE_EXTRACTION = '    service_name: str | None = None\n    standalone_price: str | None = None\n    if isinstance(catalog_payload, dict):\n        services = catalog_payload.get("services")\n        if isinstance(services, list) and len(services) == 1 and isinstance(services[0], dict):\n            service = services[0]\n            raw_name = service.get("name")\n            raw_price = service.get("price")\n            if isinstance(raw_name, str) and raw_name.strip():\n                service_name = raw_name.strip()\n            if isinstance(raw_price, str) and raw_price.strip():\n                standalone_price = raw_price.strip()\n                if standalone_price.endswith(" EGP"):\n                    standalone_price = standalone_price[:-4] + " جنيه"\n\n'
OLD_INQUIRE = '    return (\n        "أنت بتسأل عن باكدج، مش عن حجز جلسة واحدة. تفاصيل الباكدجات الجديدة من عدد الجلسات "\n        "والسعر مش مسجلة عندي كعرض موثوق حالياً، فمش هافترض سعر باكدج من سعر الجلسة العادية."\n    )\n'
NEW_INQUIRE = '    if service_name and standalone_price:\n        return (\n            f"لو بتقارن بين جلسة واحدة وباكدج: جلسة {service_name} العادية سعرها "\n            f"{standalone_price}. أما تفاصيل الباكدجات الجديدة من عدد الجلسات والسعر "\n            "فمش مسجلة عندي كعرض موثوق حالياً، فمش هافترض تفاصيل مش موجودة."\n        )\n    return (\n        "لو بتقارن بين جلسة واحدة وباكدج، تفاصيل الباكدجات الجديدة من عدد الجلسات والسعر "\n        "مش مسجلة عندي كعرض موثوق حالياً، فمش هافترض تفاصيل مش موجودة."\n    )\n'
OLD_PACKAGE_CALL = '            package_intent_reply = _verified_package_intent_reply(\n                intent=str(semantic_decision.package_intent),\n                package_payload=(prefetched_results.get("customer_packages") if isinstance(prefetched_results.get("customer_packages"), dict) else None),\n            )\n'
NEW_PACKAGE_CALL = '            package_intent_reply = _verified_package_intent_reply(\n                intent=str(semantic_decision.package_intent),\n                package_payload=(\n                    prefetched_results.get("customer_packages")\n                    if isinstance(prefetched_results.get("customer_packages"), dict)\n                    else None\n                ),\n                catalog_payload=(\n                    prefetched_results.get("clinic_catalog")\n                    if isinstance(prefetched_results.get("clinic_catalog"), dict)\n                    else None\n                ),\n            )\n'
NEW_CASES = 'def _cases() -> list[FocusedCase]:\n    # Only the remaining problem surface plus new nearby variants.\n    # For read-only availability checks, appointment_creation is the meaningful\n    # authorization distinction. The runtime may keep a lightweight flow only to\n    # preserve presented options for a possible follow-up booking.\n    return [\n        FocusedCase(\n            "nearest_availability_question",\n            "remaining_problem",\n            "ممكن أعرف أقرب ميعاد متاح لليزر ابط؟",\n            _all(\n                _has("availability_discovery"),\n                _lacks("appointment_creation"),\n                _entity("service_id", "underarm_service_id"),\n            ),\n        ),\n        FocusedCase(\n            "price_and_availability_question",\n            "remaining_problem",\n            "جلسة ليزر ابط بكام وهل في مواعيد فاضية بكرة؟",\n            _all(\n                _has("pricing", "availability_discovery"),\n                _lacks("appointment_creation"),\n                _entity("service_id", "underarm_service_id"),\n                _date_present,\n            ),\n        ),\n        FocusedCase(\n            "package_comparison_reply_quality",\n            "remaining_problem",\n            "أنا أول مرة وعايز ليزر ابط، أحجز جلسة واحدة ولا أبدأ كورس جلسات كامل؟",\n            _all(\n                _package_intent("inquire"),\n                _has("package_information", "pricing"),\n                _lacks("appointment_creation"),\n            ),\n        ),\n        FocusedCase(\n            "price_and_nearest_availability",\n            "compound_inquiry",\n            "جلسة ليزر ابط بكام وأقرب ميعاد متاح إمتى؟",\n            _all(\n                _has("pricing", "availability_discovery"),\n                _lacks("appointment_creation"),\n                _entity("service_id", "underarm_service_id"),\n            ),\n        ),\n        FocusedCase(\n            "availability_then_decide",\n            "booking_vs_inquiry",\n            "ممكن أشوف مواعيد ليزر ابط الأول وبعدها أقرر أحجز ولا لأ؟",\n            _all(\n                _has("availability_discovery"),\n                _lacks("appointment_creation"),\n                _entity("service_id", "underarm_service_id"),\n            ),\n        ),\n        FocusedCase(\n            "doctor_availability_then_decide",\n            "booking_vs_inquiry",\n            "شوفلي مواعيد د احمد محمود الأسبوع الجاي وأنا أقرر",\n            _all(\n                _has("availability_discovery"),\n                _lacks("appointment_creation"),\n                _entity("doctor_id", "ahmed_doctor_id"),\n            ),\n        ),\n        FocusedCase(\n            "explicit_conditional_booking",\n            "booking_vs_inquiry",\n            "لو فيه ميعاد ليزر ابط بكرة بعد الساعة ٧ احجزلي",\n            _all(\n                _has("appointment_creation", "availability_discovery"),\n                _flow("start_booking"),\n                _entity("service_id", "underarm_service_id"),\n                _time_window(after="19:00"),\n                _date_present,\n            ),\n        ),\n        FocusedCase(\n            "price_plus_explicit_booking",\n            "booking_vs_inquiry",\n            "جلسة ليزر ابط بكام؟ واحجزلي بكرة لو فيه ميعاد",\n            _all(\n                _has("pricing", "appointment_creation", "availability_discovery"),\n                _flow("start_booking"),\n                _entity("service_id", "underarm_service_id"),\n                _date_present,\n            ),\n        ),\n        FocusedCase(\n            "time_window_inquiry_with_service",\n            "time_semantics",\n            "إيه المواعيد المتاحة لليزر ابط بين ٦ و٨ بالليل؟",\n            _all(\n                _has("availability_discovery"),\n                _lacks("appointment_creation"),\n                _entity("service_id", "underarm_service_id"),\n                _time_window(after="18:00", before="20:00"),\n            ),\n        ),\n        FocusedCase(\n            "time_window_booking_with_service",\n            "time_semantics",\n            "احجزلي ليزر ابط في أي ميعاد بين ٦ و٨ بالليل",\n            _all(\n                _has("appointment_creation", "availability_discovery"),\n                _flow("start_booking"),\n                _entity("service_id", "underarm_service_id"),\n                _time_window(after="18:00", before="20:00"),\n            ),\n        ),\n        FocusedCase(\n            "availability_without_service",\n            "booking_vs_inquiry",\n            "ممكن أعرف عندكم مواعيد فاضية بكرة؟",\n            _all(\n                _has("availability_discovery"),\n                _lacks("appointment_creation"),\n                _date_present,\n            ),\n        ),\n    ]\n\n\n'
NEW_TEST = 'from pathlib import Path\n\n\ndef test_focused_problem_runner_contains_only_current_problem_surface() -> None:\n    backend = Path(__file__).resolve().parent.parent\n    source = (backend / "scripts/run_agent_problem_regression.py").read_text(encoding="utf-8")\n\n    required = (\n        "nearest_availability_question",\n        "price_and_availability_question",\n        "package_comparison_reply_quality",\n        "price_and_nearest_availability",\n        "availability_then_decide",\n        "doctor_availability_then_decide",\n        "explicit_conditional_booking",\n        "price_plus_explicit_booking",\n        "time_window_inquiry_with_service",\n        "time_window_booking_with_service",\n        "availability_without_service",\n    )\n    for case in required:\n        assert case in source\n\n    for clean_case in (\n        "doctor_short_name_booking",\n        "booking_after_time",\n        "booking_before_time",\n        "package_avoid_existing_keeps_booking",\n        "mixed_language_booking_no_price_inference",\n        "explicit_booking_after_time",\n        "nearest_booking_request",\n        "doctor_availability_question_no_booking",\n        "time_range_booking",\n        "time_range_availability_question",\n    ):\n        assert clean_case not in source\n\n\ndef test_focused_problem_runner_records_real_agent_reply() -> None:\n    backend = Path(__file__).resolve().parent.parent\n    source = (backend / "scripts/run_agent_problem_regression.py").read_text(encoding="utf-8")\n\n    assert "run_agent_chat" in source\n    assert \'"reply": reply_text\' in source\n    assert \'"reply_model": reply_model\' in source\n    assert \'"no_unexpected_write": no_unexpected_write\' in source\n\n\ndef test_focused_problem_runner_has_no_runtime_lexical_routing() -> None:\n    backend = Path(__file__).resolve().parent.parent\n    source = (backend / "scripts/run_agent_problem_regression.py").read_text(encoding="utf-8").lower()\n\n    assert "re.compile" not in source\n    assert "re.search" not in source\n    assert "re.match" not in source\n    assert "keyword" not in source\n'


def replace_once(text: str, old: str, new: str, label: str) -> str:
    if old not in text:
        raise RuntimeError(f"Could not find expected {label} anchor.")
    return text.replace(old, new, 1)


def harden_interpreter(text: str) -> str:
    if "Do not infer appointment_creation from availability_discovery itself." in text:
        return text
    return replace_once(text, OLD_PROMPT, NEW_PROMPT, "semantic prompt")


def improve_agent_chat(text: str) -> str:
    if "booking_authorized: bool" not in text:
        text = replace_once(text, OLD_BOOKING_SIG, NEW_BOOKING_SIG, "booking formatter signature")
    if "لو حابب تحجز واحد من المواعيد دي" not in text:
        text = replace_once(text, OLD_BOOKING_RETURN, NEW_BOOKING_RETURN, "booking formatter closing")
    if 'booking_authorized="appointment_creation" in set(policy.capabilities)' not in text:
        text = replace_once(text, OLD_BOOKING_CALL, NEW_BOOKING_CALL, "booking formatter call")

    if "catalog_payload: dict[str, object] | None = None" not in text:
        text = replace_once(text, OLD_PACKAGE_SIG, NEW_PACKAGE_SIG, "package formatter signature")

    if "standalone_price: str | None = None" not in text:
        fn_pos = text.find("def _verified_package_intent_reply")
        anchor_pos = text.find('    if intent == "purchase":\n', fn_pos)
        if anchor_pos < 0:
            raise RuntimeError("Could not find package formatter body anchor.")
        text = text[:anchor_pos] + PACKAGE_EXTRACTION + text[anchor_pos:]

    if "لو بتقارن بين جلسة واحدة وباكدج: جلسة" not in text:
        text = replace_once(text, OLD_INQUIRE, NEW_INQUIRE, "package inquiry reply")

    package_call_pos = text.find("package_intent_reply = _verified_package_intent_reply")
    if package_call_pos < 0:
        raise RuntimeError("Could not find package reply call.")
    nearby = text[package_call_pos: package_call_pos + 1000]
    if "catalog_payload=(" not in nearby:
        text = replace_once(text, OLD_PACKAGE_CALL, NEW_PACKAGE_CALL, "package reply call")

    return text


def update_runner(text: str) -> str:
    pattern = re.compile(
        r"def _cases\(\) -> list\[FocusedCase\]:\n.*?(?=def _semantic_expected\()",
        re.DOTALL,
    )
    if not pattern.search(text):
        raise RuntimeError("Could not find focused regression _cases() block.")
    return pattern.sub(lambda _: NEW_CASES, text, count=1)


def validate(path: Path) -> None:
    compile(path.read_text(encoding="utf-8"), str(path), "exec")


def main() -> int:
    paths = (INTERPRETER, AGENT_CHAT, RUNNER, TEST)
    for path in paths:
        if not path.exists():
            print(f"ERROR: missing {path}. Run this from the Tia repository root.", file=sys.stderr)
            return 2

    originals = {path: path.read_text(encoding="utf-8") for path in paths}

    try:
        updated = {
            INTERPRETER: harden_interpreter(originals[INTERPRETER]),
            AGENT_CHAT: improve_agent_chat(originals[AGENT_CHAT]),
            RUNNER: update_runner(originals[RUNNER]),
            TEST: NEW_TEST,
        }

        for path, content in updated.items():
            path.write_text(content, encoding="utf-8", newline="\n")

        for path in paths:
            validate(path)

    except Exception:
        for path, content in originals.items():
            path.write_text(content, encoding="utf-8", newline="\n")
        raise

    print("Tia v2 focused hardening applied successfully.")
    print("Changed existing semantic/response paths only; no new routing layer.")
    print("Focused suite now contains only remaining problems + nearby variants.")
    print("Python syntax validation: OK")
    print("Keyword/regex routing added: no")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
