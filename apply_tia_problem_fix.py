from __future__ import annotations

from pathlib import Path
import sys

RUNNER_CONTENT = 'from __future__ import annotations\n\n"""Focused regression suite for Tia booking/inquiry/time semantic problems.\n\nUnlike the broad matrix, this runner contains only previously problematic\nsurfaces plus new nearby variants. Each case evaluates the structured turn\ndecision and, by default, sends the same first turn through the real customer\nagent so the JSON report includes the actual reply and reply model.\n\nAll database writes are wrapped by an outer transaction and rolled back unless\n--keep-data is explicitly supplied. The cases are deliberately first-turn,\nnon-confirmation scenarios and additionally assert that they did not create a\nnew appointment.\n"""\n\nimport argparse\nimport json\nimport sys\nimport traceback\nfrom dataclasses import asdict, dataclass, field\nfrom datetime import UTC, datetime\nfrom pathlib import Path\nfrom time import perf_counter\nfrom typing import Any, Callable\nfrom uuid import UUID\nfrom zoneinfo import ZoneInfo\n\nfrom langchain_core.messages import HumanMessage\nfrom sqlalchemy import create_engine, select\nfrom sqlalchemy.orm import Session\n\nfrom app.agents.clinic_grounding import build_clinic_catalog\nfrom app.agents.turn_interpreter import interpret_customer_turn\nfrom app.core.config import settings\nfrom app.models.workspace import Workspace\nfrom app.services.agent_chat import run_agent_chat\nfrom run_agent_e2e_matrix import (\n    _agent_payload,\n    _appointments_for,\n    _catalog_row,\n    _fixture_patients,\n)\n\n\nCheck = Callable[[Any, dict[str, Any]], tuple[bool, str]]\n\n\n@dataclass(frozen=True)\nclass FocusedCase:\n    name: str\n    category: str\n    message: str\n    check: Check\n\n\n@dataclass\nclass Result:\n    name: str\n    category: str\n    status: str\n    duration_ms: int\n    details: dict[str, Any] = field(default_factory=dict)\n    error: str | None = None\n\n\ndef _has(*names: str) -> Check:\n    def check(decision: Any, _: dict[str, Any]) -> tuple[bool, str]:\n        capabilities = {str(item) for item in (decision.capabilities or [])}\n        missing = [name for name in names if name not in capabilities]\n        return not missing, f"capabilities={sorted(capabilities)} missing={missing}"\n\n    return check\n\n\ndef _lacks(*names: str) -> Check:\n    def check(decision: Any, _: dict[str, Any]) -> tuple[bool, str]:\n        capabilities = {str(item) for item in (decision.capabilities or [])}\n        unexpected = [name for name in names if name in capabilities]\n        return not unexpected, f"capabilities={sorted(capabilities)} unexpected={unexpected}"\n\n    return check\n\n\ndef _flow(expected: str) -> Check:\n    def check(decision: Any, _: dict[str, Any]) -> tuple[bool, str]:\n        actual = str(decision.flow_signal)\n        return actual == expected, f"flow_signal={actual} expected={expected}"\n\n    return check\n\n\ndef _package_intent(expected: str) -> Check:\n    def check(decision: Any, _: dict[str, Any]) -> tuple[bool, str]:\n        actual = str(decision.package_intent)\n        return actual == expected, f"package_intent={actual} expected={expected}"\n\n    return check\n\n\ndef _entity(field: str, expected_key: str) -> Check:\n    def check(decision: Any, expected: dict[str, Any]) -> tuple[bool, str]:\n        actual = getattr(decision.entity_hints, field)\n        wanted = expected[expected_key]\n        return str(actual or "") == str(wanted), f"{field}={actual} expected={wanted}"\n\n    return check\n\n\ndef _time_window(*, after: str | None = None, before: str | None = None) -> Check:\n    def check(decision: Any, _: dict[str, Any]) -> tuple[bool, str]:\n        hints = decision.entity_hints\n        ok = (\n            hints.requested_start_time is None\n            and hints.not_before_time == after\n            and hints.not_after_time == before\n        )\n        return ok, (\n            f"start={hints.requested_start_time} "\n            f"not_before={hints.not_before_time} not_after={hints.not_after_time}"\n        )\n\n    return check\n\n\ndef _date_present(decision: Any, _: dict[str, Any]) -> tuple[bool, str]:\n    value = decision.entity_hints.requested_date\n    return bool(value), f"requested_date={value}"\n\n\ndef _all(*checks: Check) -> Check:\n    def combined(decision: Any, expected: dict[str, Any]) -> tuple[bool, str]:\n        messages: list[str] = []\n        ok_all = True\n        for check in checks:\n            ok, message = check(decision, expected)\n            messages.append(message)\n            ok_all = ok_all and ok\n        return ok_all, " | ".join(messages)\n\n    return combined\n\n\ndef _cases() -> list[FocusedCase]:\n    # Previously problematic cases first, then new near-neighbor variants.\n    return [\n        FocusedCase(\n            "doctor_short_name_booking",\n            "known_problem",\n            "عايز احجز مع د احمد محمود",\n            _all(\n                _has("appointment_creation", "availability_discovery"),\n                _flow("start_booking"),\n                _entity("doctor_id", "ahmed_doctor_id"),\n            ),\n        ),\n        FocusedCase(\n            "booking_after_time",\n            "known_problem",\n            "عايز ميعاد بعد الساعة ٦ بالليل",\n            _all(\n                _has("appointment_creation", "availability_discovery"),\n                _flow("start_booking"),\n                _time_window(after="18:00"),\n            ),\n        ),\n        FocusedCase(\n            "booking_before_time",\n            "known_problem",\n            "عايز ميعاد قبل الساعة ٨ بالليل",\n            _all(\n                _has("appointment_creation", "availability_discovery"),\n                _flow("start_booking"),\n                _time_window(before="20:00"),\n            ),\n        ),\n        FocusedCase(\n            "package_inquiry_does_not_start_booking",\n            "known_problem",\n            "أنا أول مرة وعايز ليزر ابط، أحجز جلسة واحدة ولا أبدأ كورس جلسات كامل؟",\n            _all(\n                _package_intent("inquire"),\n                _has("package_information"),\n                _lacks("appointment_creation", "availability_discovery"),\n                _flow("none"),\n            ),\n        ),\n        FocusedCase(\n            "package_avoid_existing_keeps_booking",\n            "known_problem",\n            "عندي باكدج ليزر ابط بس المرة دي عايز أحجز جلسة عادية منفصلة ومتحسبهاش من الباكدج",\n            _all(\n                _package_intent("avoid_existing"),\n                _has("appointment_creation", "availability_discovery"),\n                _flow("start_booking"),\n            ),\n        ),\n        FocusedCase(\n            "mixed_language_booking_no_price_inference",\n            "known_problem",\n            "عايز احجز underarm laser مع د Ahmed في Nasr City",\n            _all(\n                _has("appointment_creation", "availability_discovery"),\n                _flow("start_booking"),\n                _lacks("pricing"),\n                _entity("service_id", "underarm_service_id"),\n                _entity("doctor_id", "ahmed_doctor_id"),\n            ),\n        ),\n        FocusedCase(\n            "availability_question_after_time",\n            "booking_vs_inquiry",\n            "هل عندكم مواعيد متاحة بعد الساعة ٧ بكرة؟",\n            _all(\n                _has("availability_discovery"),\n                _lacks("appointment_creation"),\n                _flow("none"),\n                _time_window(after="19:00"),\n                _date_present,\n            ),\n        ),\n        FocusedCase(\n            "explicit_booking_after_time",\n            "booking_vs_inquiry",\n            "احجزلي ميعاد بكرة بعد الساعة ٧",\n            _all(\n                _has("appointment_creation", "availability_discovery"),\n                _flow("start_booking"),\n                _time_window(after="19:00"),\n                _date_present,\n            ),\n        ),\n        FocusedCase(\n            "nearest_availability_question",\n            "booking_vs_inquiry",\n            "ممكن أعرف أقرب ميعاد متاح لليزر ابط؟",\n            _all(\n                _has("availability_discovery"),\n                _lacks("appointment_creation"),\n                _flow("none"),\n                _entity("service_id", "underarm_service_id"),\n            ),\n        ),\n        FocusedCase(\n            "nearest_booking_request",\n            "booking_vs_inquiry",\n            "عايز أحجز أقرب ميعاد متاح لليزر ابط",\n            _all(\n                _has("appointment_creation", "availability_discovery"),\n                _flow("start_booking"),\n                _entity("service_id", "underarm_service_id"),\n            ),\n        ),\n        FocusedCase(\n            "price_and_availability_question",\n            "combined_inquiry",\n            "جلسة ليزر ابط بكام وهل في مواعيد فاضية بكرة؟",\n            _all(\n                _has("pricing", "availability_discovery"),\n                _lacks("appointment_creation"),\n                _flow("none"),\n                _entity("service_id", "underarm_service_id"),\n                _date_present,\n            ),\n        ),\n        FocusedCase(\n            "doctor_availability_question_no_booking",\n            "booking_vs_inquiry",\n            "د احمد محمود عنده مواعيد فاضية الأسبوع الجاي؟",\n            _all(\n                _has("availability_discovery"),\n                _lacks("appointment_creation"),\n                _flow("none"),\n                _entity("doctor_id", "ahmed_doctor_id"),\n            ),\n        ),\n        FocusedCase(\n            "time_range_booking",\n            "time_semantics",\n            "عايز أحجز ميعاد من الساعة ٦ لحد ٨ بالليل",\n            _all(\n                _has("appointment_creation", "availability_discovery"),\n                _flow("start_booking"),\n                _time_window(after="18:00", before="20:00"),\n            ),\n        ),\n        FocusedCase(\n            "time_range_availability_question",\n            "time_semantics",\n            "في مواعيد فاضية من الساعة ٦ لحد ٨ بالليل؟",\n            _all(\n                _has("availability_discovery"),\n                _lacks("appointment_creation"),\n                _flow("none"),\n                _time_window(after="18:00", before="20:00"),\n            ),\n        ),\n    ]\n\n\ndef _semantic_expected(catalog: dict[str, Any]) -> dict[str, Any]:\n    underarm = _catalog_row(catalog, "services", "ليزر إزالة الشعر - إبط")\n    ahmed = _catalog_row(catalog, "doctors", "أحمد محمود")\n    return {\n        "underarm_service_id": str(underarm["id"]),\n        "ahmed_doctor_id": str(ahmed["id"]),\n    }\n\n\ndef _run_case(\n    *,\n    db: Session,\n    workspace: Workspace,\n    patient: Any,\n    catalog: dict[str, Any],\n    expected: dict[str, Any],\n    case: FocusedCase,\n    with_replies: bool,\n) -> Result:\n    started = perf_counter()\n    timezone_name = (workspace.timezone or "Africa/Cairo").strip()\n    local_now = datetime.now(ZoneInfo(timezone_name))\n\n    decision = interpret_customer_turn(\n        flow=None,\n        history=[HumanMessage(content=case.message)],\n        timezone_name=timezone_name,\n        local_now=local_now,\n        clinic_catalog=catalog,\n    )\n    semantic_ok, semantic_check = case.check(decision, expected)\n\n    reply_text: str | None = None\n    reply_model: str | None = None\n    reply_ok = True\n    no_unexpected_write = True\n    reply_error: str | None = None\n\n    if with_replies:\n        before = {row.id for row in _appointments_for(db, workspace, patient)}\n        try:\n            payload = _agent_payload(\n                patient_id=patient.id,\n                message=case.message,\n                conversation_id=None,\n            )\n            response = run_agent_chat(db=db, workspace=workspace, payload=payload)\n            reply_text = response.reply\n            reply_model = response.model\n            reply_ok = bool((reply_text or "").strip())\n        except Exception as exc:  # noqa: BLE001 - report and continue\n            reply_ok = False\n            reply_error = f"{type(exc).__name__}: {exc}"\n        after = {row.id for row in _appointments_for(db, workspace, patient)}\n        no_unexpected_write = before == after\n\n    ok = semantic_ok and reply_ok and no_unexpected_write\n    details = {\n        "message": case.message,\n        "semantic_ok": semantic_ok,\n        "semantic_check": semantic_check,\n        "capabilities": list(decision.capabilities or []),\n        "flow_signal": str(decision.flow_signal),\n        "package_intent": str(decision.package_intent),\n        "entity_hints": decision.entity_hints.model_dump(mode="json"),\n        "confidence": decision.confidence,\n        "reason": decision.reason,\n        "reply_checked": with_replies,\n        "reply_ok": reply_ok,\n        "reply": reply_text,\n        "reply_model": reply_model,\n        "reply_error": reply_error,\n        "no_unexpected_write": no_unexpected_write,\n    }\n    failures: list[str] = []\n    if not semantic_ok:\n        failures.append(semantic_check)\n    if not reply_ok:\n        failures.append(reply_error or "Agent reply was empty.")\n    if not no_unexpected_write:\n        failures.append("First-turn case unexpectedly created an appointment.")\n\n    return Result(\n        name=case.name,\n        category=case.category,\n        status="PASS" if ok else "FAIL",\n        duration_ms=int((perf_counter() - started) * 1000),\n        details=details,\n        error=" | ".join(failures) if failures else None,\n    )\n\n\ndef parse_args() -> argparse.Namespace:\n    parser = argparse.ArgumentParser(\n        description="Run only Tia\'s currently problematic booking/inquiry/time regressions."\n    )\n    parser.add_argument("--workspace-slug", default="tia")\n    parser.add_argument("--workspace-id", type=UUID, default=None)\n    parser.add_argument(\n        "--semantic-only",\n        action="store_true",\n        help="Skip run_agent_chat reply generation and evaluate only the structured interpreter.",\n    )\n    parser.add_argument(\n        "--keep-data",\n        action="store_true",\n        help="Commit test conversations instead of rolling them back. Not recommended.",\n    )\n    parser.add_argument(\n        "--report",\n        default="artifacts/agent-problem-regression-report.json",\n    )\n    return parser.parse_args()\n\n\ndef main() -> int:\n    args = parse_args()\n    if str(settings.environment or "").strip().lower() == "production":\n        print("Refusing to run the focused agent regression suite in production.", file=sys.stderr)\n        return 2\n\n    engine = create_engine(settings.database_url, pool_pre_ping=True)\n    connection = engine.connect()\n    outer = connection.begin()\n    db = Session(\n        bind=connection,\n        expire_on_commit=False,\n        join_transaction_mode="create_savepoint",\n    )\n\n    results: list[Result] = []\n    report_meta: dict[str, Any] = {}\n    exit_code = 1\n\n    try:\n        if args.workspace_id is not None:\n            workspace = db.scalar(select(Workspace).where(Workspace.id == args.workspace_id))\n        else:\n            workspace = db.scalar(select(Workspace).where(Workspace.slug == args.workspace_slug))\n        if workspace is None:\n            raise RuntimeError("Workspace not found.")\n\n        catalog = build_clinic_catalog(db, workspace)\n        if not catalog.get("services") or not catalog.get("doctors") or not catalog.get("branches"):\n            raise RuntimeError("Active clinic catalog is incomplete.")\n\n        patients = _fixture_patients(db, workspace)\n        patient = patients.get("busy-evening")\n        if patient is None:\n            raise RuntimeError(\n                "Focused regression patient is missing. Run the realistic fixture seed first."\n            )\n\n        expected = _semantic_expected(catalog)\n        report_meta = {\n            "started_at": datetime.now(UTC).isoformat(),\n            "workspace_id": str(workspace.id),\n            "workspace_slug": workspace.slug,\n            "suite": "focused-problem-regression",\n            "with_replies": not args.semantic_only,\n            "rollback": not args.keep_data,\n        }\n\n        for case in _cases():\n            try:\n                result = _run_case(\n                    db=db,\n                    workspace=workspace,\n                    patient=patient,\n                    catalog=catalog,\n                    expected=expected,\n                    case=case,\n                    with_replies=not args.semantic_only,\n                )\n            except Exception as exc:  # noqa: BLE001\n                result = Result(\n                    name=case.name,\n                    category=case.category,\n                    status="FAIL",\n                    duration_ms=0,\n                    details={"message": case.message},\n                    error=f"{type(exc).__name__}: {exc}",\n                )\n            results.append(result)\n            print(\n                f"[{result.status}] {result.category}/{result.name} "\n                f"({result.duration_ms} ms)"\n            )\n            if result.error:\n                print(f"       {result.error}")\n\n        exit_code = 1 if any(row.status == "FAIL" for row in results) else 0\n\n    except Exception as exc:  # noqa: BLE001\n        print(traceback.format_exc(), file=sys.stderr)\n        results.append(\n            Result(\n                name="suite_exception",\n                category="setup",\n                status="FAIL",\n                duration_ms=0,\n                error=f"{type(exc).__name__}: {exc}",\n            )\n        )\n        exit_code = 1\n    finally:\n        try:\n            db.close()\n        finally:\n            if args.keep_data:\n                outer.commit()\n            else:\n                outer.rollback()\n            connection.close()\n            engine.dispose()\n\n    counts = {\n        "PASS": sum(1 for row in results if row.status == "PASS"),\n        "FAIL": sum(1 for row in results if row.status == "FAIL"),\n    }\n    path = Path(args.report)\n    if not path.is_absolute():\n        path = Path.cwd() / path\n    path.parent.mkdir(parents=True, exist_ok=True)\n    payload = {\n        **report_meta,\n        "counts": counts,\n        "results": [asdict(row) for row in results],\n    }\n    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")\n\n    print("\\nSummary:", json.dumps(counts, ensure_ascii=False))\n    print(f"Report: {path}")\n    if not args.keep_data:\n        print("Database writes rolled back: yes")\n    print("Customer-agent replies included:", "no" if args.semantic_only else "yes")\n    print("WhatsApp/n8n used: no")\n    return exit_code\n\n\nif __name__ == "__main__":\n    raise SystemExit(main())\n'
TEST_CONTENT = 'from pathlib import Path\n\n\ndef test_focused_problem_runner_contains_only_problem_and_nearby_regressions() -> None:\n    backend = Path(__file__).resolve().parent.parent\n    source = (backend / "scripts/run_agent_problem_regression.py").read_text(encoding="utf-8")\n\n    required = (\n        "doctor_short_name_booking",\n        "booking_after_time",\n        "booking_before_time",\n        "package_inquiry_does_not_start_booking",\n        "package_avoid_existing_keeps_booking",\n        "mixed_language_booking_no_price_inference",\n        "availability_question_after_time",\n        "explicit_booking_after_time",\n        "nearest_availability_question",\n        "nearest_booking_request",\n        "price_and_availability_question",\n        "doctor_availability_question_no_booking",\n        "time_range_booking",\n        "time_range_availability_question",\n    )\n    for case in required:\n        assert case in source\n\n    # Previously clean broad-matrix cases should not be copied into this suite.\n    for clean_case in (\n        "active_catalog",\n        "full_booking_grounding",\n        "service_information_no_write",\n        "medical_suitability",\n        "catalog_id_grounding",\n    ):\n        assert clean_case not in source\n\n\ndef test_focused_problem_runner_records_real_agent_reply() -> None:\n    backend = Path(__file__).resolve().parent.parent\n    source = (backend / "scripts/run_agent_problem_regression.py").read_text(encoding="utf-8")\n\n    assert "run_agent_chat" in source\n    assert \'"reply": reply_text\' in source\n    assert \'"reply_model": reply_model\' in source\n    assert \'"no_unexpected_write": no_unexpected_write\' in source\n\n\ndef test_focused_problem_runner_has_no_runtime_lexical_routing() -> None:\n    backend = Path(__file__).resolve().parent.parent\n    source = (backend / "scripts/run_agent_problem_regression.py").read_text(encoding="utf-8").lower()\n\n    assert "re.compile" not in source\n    assert "re.search" not in source\n    assert "re.match" not in source\n    assert "keyword" not in source\n'
NORMALIZER_BLOCK = 'def _normalize_unified_turn_contract(\n    value: UnifiedTurnDecision,\n) -> UnifiedTurnDecision:\n    """Enforce package-vs-appointment structure after semantic interpretation.\n\n    This invariant uses the model\'s structured package_intent, never customer\n    message keywords. Package purchase/inquiry does not itself authorize an\n    ordinary appointment or an availability search.\n    """\n    intent = str(value.package_intent)\n    if intent not in {"purchase", "inquire"}:\n        return value\n\n    capabilities = [\n        capability\n        for capability in value.capabilities\n        if str(capability) not in {"appointment_creation", "availability_discovery"}\n    ]\n    if "package_information" not in capabilities:\n        capabilities.append("package_information")\n\n    return value.model_copy(\n        update={\n            "capabilities": capabilities,\n            "flow_signal": "none",\n        }\n    )\n\n\n'

INTERPRETER = Path("backend/app/agents/turn_interpreter.py")
RUNNER = Path("backend/scripts/run_agent_problem_regression.py")
TEST = Path("backend/tests/test_agent_problem_regression_runner.py")
BACKUP = Path("backend/app/agents/turn_interpreter.py.tia-problem-fix.bak")

BOOKING_MARKER = "Treat booking authorization separately from availability curiosity"
PACKAGE_MARKER = "A comparison such as one session versus a course/package is still an inquiry"
NORMALIZER_NAME = "_normalize_unified_turn_contract"


def fail(message: str) -> None:
    raise RuntimeError(message)


def harden_interpreter(original: str) -> str:
    text = original

    if BOOKING_MARKER not in text:
        anchor = (
            '            "A fresh booking request uses start_booking; moving an existing appointment '
            'uses start_reschedule.\\n\\n"\n'
        )
        addition = (
            '            "Treat booking authorization separately from availability curiosity: '
            'appointment_creation is required "\n'
            '            "when the customer is actually asking to make/reserve an appointment, even if '
            'service/date/branch/doctor "\n'
            '            "is still missing and even when the requested time is expressed as before/after/a range. "\n'
            '            "Use availability_discovery without appointment_creation when the customer is only asking '
            'what times "\n'
            '            "are available and has not asked to reserve one. An appointment_creation request normally '
            'also needs "\n'
            '            "availability_discovery unless an active flow is selecting an already verified slot. "\n'
            '            "Naming a concrete service, doctor, or branch as the target of a booking does not by itself '
            'require "\n'
            '            "service_information, pricing, doctor_discovery, or branch_discovery once the target is '
            'grounded; "\n'
            '            "use those read capabilities only when the customer asks for that information/options or '
            'resolution "\n'
            '            "is genuinely needed.\\n\\n"\n'
        )
        if anchor not in text:
            fail("Booking prompt anchor not found in local turn_interpreter.py.")
        text = text.replace(anchor, anchor + addition, 1)

    if PACKAGE_MARKER not in text:
        anchor = (
            '            "booking unless the latest turn separately and explicitly authorizes one single appointment. "\n'
        )
        addition = (
            '            "A comparison such as one session versus a course/package is still an inquiry, not booking '
            'authorization, "\n'
            '            "so it must not set start_booking merely because a service was mentioned. "\n'
        )
        if anchor not in text:
            fail("Package prompt anchor not found in local turn_interpreter.py.")
        text = text.replace(anchor, anchor + addition, 1)

    if f"def {NORMALIZER_NAME}(" not in text:
        anchor = "def _history_excerpt(history: list[BaseMessage]) -> str:"
        pos = text.find(anchor)
        if pos < 0:
            fail("_history_excerpt() anchor not found in local turn_interpreter.py.")
        text = text[:pos] + NORMALIZER_BLOCK + text[pos:]

    normalized_assignment = "    value = _normalize_unified_turn_contract(invocation.value)\n"
    if normalized_assignment not in text:
        anchor = "    value = invocation.value\n"
        if anchor not in text:
            fail("Interpreter result assignment anchor not found.")
        text = text.replace(anchor, normalized_assignment, 1)

    return text


def safe_write(path: Path, content: str) -> None:
    if path.exists():
        existing = path.read_text(encoding="utf-8")
        if existing == content:
            return
        own_markers = (
            "Focused regression suite for Tia booking/inquiry/time semantic problems",
            "test_focused_problem_runner_contains_only_problem_and_nearby_regressions",
        )
        if not any(marker in existing for marker in own_markers):
            fail(f"Refusing to overwrite unrelated existing file: {path}")
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8", newline="\n")


def validate(path: Path) -> None:
    compile(path.read_text(encoding="utf-8"), str(path), "exec")


def main() -> int:
    if not INTERPRETER.exists():
        print(
            "ERROR: run this file from the Tia repository root; "
            "backend/app/agents/turn_interpreter.py was not found.",
            file=sys.stderr,
        )
        return 2

    original = INTERPRETER.read_text(encoding="utf-8")
    patched = harden_interpreter(original)

    if not BACKUP.exists():
        BACKUP.write_text(original, encoding="utf-8", newline="\n")

    runner_existed = RUNNER.exists()
    test_existed = TEST.exists()

    try:
        INTERPRETER.write_text(patched, encoding="utf-8", newline="\n")
        safe_write(RUNNER, RUNNER_CONTENT)
        safe_write(TEST, TEST_CONTENT)

        validate(INTERPRETER)
        validate(RUNNER)
        validate(TEST)
    except Exception:
        INTERPRETER.write_text(original, encoding="utf-8", newline="\n")
        if not runner_existed and RUNNER.exists():
            RUNNER.unlink()
        if not test_existed and TEST.exists():
            TEST.unlink()
        raise

    print("Tia problem fix applied successfully.")
    print("turn_interpreter.py:", "changed" if patched != original else "already hardened")
    print("focused runner:", RUNNER)
    print("focused test:", TEST)
    print("backup:", BACKUP)
    print("Python syntax validation: OK")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
