from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]


def read(path: str) -> str:
    return (ROOT / path).read_text(encoding="utf-8")


def write(path: str, value: str) -> None:
    target = ROOT / path
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(value, encoding="utf-8")


def replace_once(path: str, old: str, new: str) -> None:
    value = read(path)
    if value.count(old) != 1:
        raise RuntimeError(f"expected one finish match in {path}; got {value.count(old)}")
    write(path, value.replace(old, new, 1))


preflight = "backend/app/services/agent_v2/compound_visit_preflight.py"
old = '''    This prevents partial visits such as booking service A and only then discovering
    that service B cannot follow it.
    """
    groups: dict[str, list[PlanStep]] = {}
'''
new = '''    This prevents partial visits such as booking service A and only then discovering
    that service B cannot follow it.
    """
    plan = _auto_resolve_grouped_visits(
        plan,
        context=context,
        timezone_name=timezone_name,
        visit_group_id=visit_group_id,
    )
    groups: dict[str, list[PlanStep]] = {}
'''
replace_once(preflight, old, new)

# The first-stage patch intentionally stops at the insertion above when the old
# source shape is ambiguous. Reuse the already-reviewed tail for orchestrator
# plumbing and focused tests rather than duplicating it here.
source = (ROOT / ".github/implementation/compound_visit_patch.py").read_text(encoding="utf-8")
marker = "# ---- orchestrator: stable group id + nested transaction rollback barrier -----"
position = source.index(marker)
tail = source[position:]
namespace = {
    "__file__": str(ROOT / ".github/implementation/compound_visit_patch.py"),
    "__name__": "__compound_finish__",
    "ROOT": ROOT,
    "text": read,
    "write": write,
    "replace_once": replace_once,
}
exec(compile(tail, "compound_visit_patch_tail.py", "exec"), namespace, namespace)

# Normalization intentionally converts later items in an exact same-visit request
# to `after`, but preserves the original shared anchor in structured facts. The
# common-doctor resolver must prefer that canonical anchor instead of mistaking
# the normalized cursor for a customer ambiguity.
replace_once(
    preflight,
    '''def _requested_group_anchor(
    steps: list[PlanStep],
    *,
    context: ReadExecutionContext,
    timezone_name: str,
) -> tuple[datetime, str] | None:
    dates: list[dict[str, object]] = []
''',
    '''def _requested_group_anchor(
    steps: list[PlanStep],
    *,
    context: ReadExecutionContext,
    timezone_name: str,
) -> tuple[datetime, str] | None:
    compound_anchors = {
        value
        for step in steps
        if (value := compound_anchor_key(step)) is not None
    }
    if len(compound_anchors) == 1:
        try:
            return datetime.fromisoformat(next(iter(compound_anchors))), "exact"
        except ValueError:
            return None

    dates: list[dict[str, object]] = []
''',
)

# Explicitly choosing different doctors for services in one requested visit is a
# contradictory constraint, not a signal to silently split the visit. Unspecified
# or candidate doctors still resolve automatically through the common intersection.
replace_once(
    preflight,
    '''        common_doctors = _common_doctors(ordered, context)
        anchor = _requested_group_anchor(ordered, context=context, timezone_name=timezone_name)
        if not common_doctors or anchor is None:
            requested = anchor[0] if anchor is not None else context.now.astimezone(ZoneInfo(timezone_name)).replace(tzinfo=None)
            for step in ordered:
                blocked = _suppress_group_write(step, requested_anchor=requested)
                blocked = blocked.model_copy(
                    update={
                        "facts": {
                            **blocked.facts,
                            "compound_visit_no_common_doctor": not bool(common_doctors),
                        }
                    }
                )
                replacements[step.operation_index] = blocked
            continue

        requested_anchor, request_mode = anchor
''',
    '''        common_doctors = _common_doctors(ordered, context)
        anchor = _requested_group_anchor(ordered, context=context, timezone_name=timezone_name)
        if not common_doctors:
            explicit_doctors = {
                str(value)
                for step in ordered
                if (value := _params(step).get("doctor_id")) not in (None, "")
            }
            conflicting_explicit_doctors = (
                len(explicit_doctors) > 1
                and all(_params(step).get("doctor_id") not in (None, "") for step in ordered)
            )
            requested = (
                anchor[0]
                if anchor is not None
                else context.now.astimezone(ZoneInfo(timezone_name)).replace(tzinfo=None)
            )
            for step in ordered:
                if conflicting_explicit_doctors:
                    replacements[step.operation_index] = step.model_copy(
                        update={
                            "disposition": "clarify",
                            "reads": [],
                            "write_intent": None,
                            "state_action": "none",
                            "clarification_field": "doctor",
                            "response_goal": "ask_doctor_choice",
                            "facts": {
                                **step.facts,
                                "compound_visit_conflicting_doctors": True,
                            },
                        }
                    )
                else:
                    blocked = _suppress_group_write(step, requested_anchor=requested)
                    replacements[step.operation_index] = blocked.model_copy(
                        update={
                            "facts": {
                                **blocked.facts,
                                "compound_visit_no_common_doctor": True,
                            }
                        }
                    )
            continue
        if anchor is None:
            requested = context.now.astimezone(ZoneInfo(timezone_name)).replace(tzinfo=None)
            for step in ordered:
                replacements[step.operation_index] = _suppress_group_write(
                    step,
                    requested_anchor=requested,
                )
            continue

        requested_anchor, request_mode = anchor
''',
)

legacy_test = "backend/tests/test_v2_compound_visit_preflight.py"
legacy = read(legacy_test)
legacy = legacy.replace("_slot(SERVICE_B, DOCTOR_B,", "_slot(SERVICE_B, DOCTOR_A,")
legacy = legacy.replace("        _normalized(),\n", "        _normalized(same_doctor=True),\n")
legacy += r'''


def test_explicit_different_doctors_require_one_doctor_for_the_visit() -> None:
    adapter = _Adapter({})

    planned = preflight_compound_visit_plan(
        _normalized(),
        context=_context(adapter),
        timezone_name="Africa/Cairo",
    )

    assert [step.write_intent for step in planned.steps] == [None, None]
    assert [step.disposition for step in planned.steps] == ["clarify", "clarify"]
    assert [step.clarification_field for step in planned.steps] == ["doctor", "doctor"]
    assert all(step.facts["compound_visit_conflicting_doctors"] is True for step in planned.steps)
'''
write(legacy_test, legacy)

write(
    "backend/tests/test_v2_visit_group_write.py",
    r'''from __future__ import annotations

from types import SimpleNamespace
from uuid import UUID

import app.services.agent_v2.write_executor as target
from app.services.agent_v2.planner import PlanStep, WriteIntent

WORKSPACE_ID = UUID("11111111-1111-1111-1111-111111111111")
PATIENT_ID = UUID("22222222-2222-2222-2222-222222222222")
BRANCH_ID = UUID("33333333-3333-3333-3333-333333333333")
DOCTOR_ID = UUID("44444444-4444-4444-4444-444444444444")
SERVICE_ID = UUID("55555555-5555-5555-5555-555555555555")
VISIT_GROUP_ID = UUID("66666666-6666-6666-6666-666666666666")
APPOINTMENT_ID = UUID("77777777-7777-7777-7777-777777777777")


class _Db:
    def __init__(self) -> None:
        self.commits = 0
        self.rollbacks = 0

    def commit(self) -> None:
        self.commits += 1

    def rollback(self) -> None:
        self.rollbacks += 1


def _booking_step(*, visit_group_id: str | None) -> PlanStep:
    parameters: dict[str, object] = {
        "branch_id": str(BRANCH_ID),
        "doctor_id": str(DOCTOR_ID),
        "service_id": str(SERVICE_ID),
        "start_at": "2026-09-14T10:00:00+03:00",
        "package_usage": "unspecified",
    }
    if visit_group_id is not None:
        parameters["visit_group_id"] = visit_group_id
    return PlanStep(
        operation_index=0,
        operation_type="book",
        disposition="write_ready",
        write_intent=WriteIntent(
            kind="booking",
            authorized=True,
            parameters=parameters,
            requires_verification=True,
        ),
        response_goal="booking_completed",
    )


def _patch_booking_dependencies(monkeypatch, captured: dict[str, object]) -> None:
    monkeypatch.setattr(target, "require_tia_workspace_domain_write", lambda *args, **kwargs: None)
    monkeypatch.setattr(
        target,
        "resolve_booking_package",
        lambda *args, **kwargs: SimpleNamespace(
            package_id=None,
            package_used=False,
            package_name=None,
        ),
    )

    def _create_appointment_operation(*args, **kwargs):
        captured.update(kwargs)
        return SimpleNamespace(id=APPOINTMENT_ID, status="confirmed")

    monkeypatch.setattr(target, "create_appointment_operation", _create_appointment_operation)


def test_booking_write_passes_verified_visit_group_id(monkeypatch) -> None:
    captured: dict[str, object] = {}
    _patch_booking_dependencies(monkeypatch, captured)
    db = _Db()

    result = target.execute_write_ready_step(
        db,
        workspace=SimpleNamespace(id=WORKSPACE_ID),
        patient=SimpleNamespace(id=PATIENT_ID, status="active"),
        step=_booking_step(visit_group_id=str(VISIT_GROUP_ID)),
        commit=True,
    )

    assert result["ok"] is True
    assert captured["visit_group_id"] == VISIT_GROUP_ID
    assert db.commits == 1
    assert db.rollbacks == 0


def test_single_booking_remains_compatible_without_visit_group(monkeypatch) -> None:
    captured: dict[str, object] = {}
    _patch_booking_dependencies(monkeypatch, captured)
    db = _Db()

    result = target.execute_write_ready_step(
        db,
        workspace=SimpleNamespace(id=WORKSPACE_ID),
        patient=SimpleNamespace(id=PATIENT_ID, status="active"),
        step=_booking_step(visit_group_id=None),
        commit=True,
    )

    assert result["ok"] is True
    assert captured["visit_group_id"] is None
''',
)

print("compound visit patch finish applied")
