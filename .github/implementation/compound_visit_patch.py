from __future__ import annotations

from pathlib import Path
import re

ROOT = Path(__file__).resolve().parents[2]


def text(path: str) -> str:
    return (ROOT / path).read_text(encoding="utf-8")


def write(path: str, value: str) -> None:
    target = ROOT / path
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(value, encoding="utf-8")


def replace_once(path: str, old: str, new: str) -> None:
    value = text(path)
    if value.count(old) != 1:
        raise RuntimeError(f"expected one match in {path}: {old[:80]!r}; got {value.count(old)}")
    write(path, value.replace(old, new, 1))


def sub_once(path: str, pattern: str, replacement: str, *, flags: int = 0) -> None:
    value = text(path)
    updated, count = re.subn(pattern, replacement, value, count=1, flags=flags)
    if count != 1:
        raise RuntimeError(f"expected one regex match in {path}: {pattern!r}; got {count}")
    write(path, updated)


# ---- schema/model plumbing -------------------------------------------------
replace_once(
    "backend/app/models/appointment.py",
    "    patient_package_id: Mapped[UUID | None] = mapped_column(index=True, nullable=True)\n    lead_id: Mapped[UUID | None] = mapped_column(index=True, nullable=True)\n",
    "    patient_package_id: Mapped[UUID | None] = mapped_column(index=True, nullable=True)\n"
    "    # Multiple service appointments that form one customer-visible visit share this id.\n"
    "    visit_group_id: Mapped[UUID | None] = mapped_column(nullable=True)\n"
    "    lead_id: Mapped[UUID | None] = mapped_column(index=True, nullable=True)\n",
)

replace_once(
    "backend/app/services/appointment_creation.py",
    "    patient_package_id: UUID | None = None,\n    lead: Lead | None = None,\n",
    "    patient_package_id: UUID | None = None,\n    visit_group_id: UUID | None = None,\n    lead: Lead | None = None,\n",
)
replace_once(
    "backend/app/services/appointment_creation.py",
    "        patient_package_id=patient_package_id,\n        lead_id=lead.id if lead is not None else None,\n",
    "        patient_package_id=patient_package_id,\n        visit_group_id=visit_group_id,\n        lead_id=lead.id if lead is not None else None,\n",
)
replace_once(
    "backend/app/services/agent_v2/write_executor.py",
    "                    patient_package_id=package_resolution.package_id,\n                    source=\"ai\",\n",
    "                    patient_package_id=package_resolution.package_id,\n                    visit_group_id=_optional_uuid(parameters, \"visit_group_id\"),\n                    source=\"ai\",\n",
)

# ---- planner: a multi-service booking owns doctor auto-resolution ----------
replace_once(
    "backend/app/services/agent_v2/planner.py",
    "def _plan_operation(index: int, operation: TurnOperation, context: PlannerContext) -> PlanStep:\n",
    "def _plan_operation(\n"
    "    index: int,\n"
    "    operation: TurnOperation,\n"
    "    context: PlannerContext,\n"
    "    *,\n"
    "    compound_book: bool = False,\n"
    ") -> PlanStep:\n",
)
replace_once(
    "backend/app/services/agent_v2/planner.py",
    "    if ambiguous.get(\"doctor\"):\n        return _clarify(index=index, operation=operation, field=\"doctor\", goal=\"ask_doctor_choice\")\n",
    "    if ambiguous.get(\"doctor\") and not (compound_book and operation.type == \"book\"):\n"
    "        return _clarify(index=index, operation=operation, field=\"doctor\", goal=\"ask_doctor_choice\")\n",
)
replace_once(
    "backend/app/services/agent_v2/planner.py",
    "    if operation.type == \"book\":\n        if \"doctor_ids\" in params:\n            return _clarify(index=index, operation=operation, field=\"doctor\", goal=\"ask_doctor_choice\")\n",
    "    if operation.type == \"book\":\n"
    "        # A same-turn multi-service visit must select one common doctor deterministically.\n"
    "        # Single-service bookings keep the existing explicit doctor-choice behavior.\n"
    "        if \"doctor_ids\" in params and not compound_book:\n"
    "            return _clarify(index=index, operation=operation, field=\"doctor\", goal=\"ask_doctor_choice\")\n",
)
replace_once(
    "backend/app/services/agent_v2/planner.py",
    "    steps: list[PlanStep] = []\n    for index, operation in enumerate(turn.operations):\n        step = _plan_operation(index, operation, context)\n",
    "    steps: list[PlanStep] = []\n"
    "    executable_book_indexes = {\n"
    "        index\n"
    "        for index, operation in enumerate(turn.operations)\n"
    "        if operation.type == \"book\" and operation.execution_intent == \"execute\"\n"
    "    }\n"
    "    compound_booking = len(executable_book_indexes) >= 2\n"
    "    for index, operation in enumerate(turn.operations):\n"
    "        step = _plan_operation(\n"
    "            index,\n"
    "            operation,\n"
    "            context,\n"
    "            compound_book=compound_booking and index in executable_book_indexes,\n"
    "        )\n",
)

# ---- compound policy: tag bookings + package purchases as one atomic group -
policy_path = "backend/app/services/agent_v2/compound_turn_policy.py"
replace_once(
    policy_path,
    "_COMPOUND_ANCHOR_FACT = \"compound_visit_anchor_local\"\n",
    "_COMPOUND_ANCHOR_FACT = \"compound_visit_anchor_local\"\n"
    "_COMPOUND_WRITE_GROUP_FACT = \"compound_write_group\"\n"
    "_COMPOUND_GROUPED_FACT = \"compound_visit_grouped\"\n",
)
insert_policy = r'''

def _tag_compound_write_group(steps: list[PlanStep]) -> list[PlanStep]:
    """Tag a multi-service booking and any package purchases it depends on as one write group."""
    bookings = [step for step in steps if _write_kind(step) == "booking"]
    service_ids = {
        str(_write_parameters(step).get("service_id"))
        for step in bookings
        if _write_parameters(step).get("service_id")
    }
    if len(bookings) < 2 or len(service_ids) < 2:
        return steps

    group_key = "compound:" + ",".join(str(step.operation_index) for step in bookings)
    purchase_indexes = {
        int(step.facts[_PACKAGE_DEPENDENCY_FACT])
        for step in bookings
        if step.facts.get(_PACKAGE_DEPENDENCY_FACT) is not None
    }
    tagged: list[PlanStep] = []
    for step in steps:
        if step in bookings or step.operation_index in purchase_indexes:
            step = step.model_copy(
                update={
                    "facts": {
                        **step.facts,
                        _COMPOUND_WRITE_GROUP_FACT: group_key,
                        _COMPOUND_GROUPED_FACT: True,
                    }
                }
            )
        tagged.append(step)
    return tagged


def compound_write_group(step: PlanStep) -> str | None:
    value = step.facts.get(_COMPOUND_WRITE_GROUP_FACT)
    return str(value) if value not in (None, "") else None
'''
replace_once(
    policy_path,
    "\ndef normalize_compound_turn_plan(\n",
    insert_policy + "\n\ndef normalize_compound_turn_plan(\n",
)
replace_once(
    policy_path,
    "    steps = _tag_and_order_package_dependencies(list(plan.steps))\n    steps = _sequence_shared_anchor_bookings(steps, catalog=catalog)\n",
    "    steps = _tag_and_order_package_dependencies(list(plan.steps))\n"
    "    steps = _tag_compound_write_group(steps)\n"
    "    steps = _sequence_shared_anchor_bookings(steps, catalog=catalog)\n",
)

# ---- preflight: resolve one common doctor and one joint visit automatically -
preflight_path = "backend/app/services/agent_v2/compound_visit_preflight.py"
replace_once(
    preflight_path,
    "from uuid import UUID\n",
    "from uuid import UUID, uuid4\n",
)
replace_once(
    preflight_path,
    "from app.services.agent_v2.compound_turn_policy import compound_anchor_key, compound_sequence_index\n",
    "from app.services.agent_v2.compound_turn_policy import (\n"
    "    compound_anchor_key,\n"
    "    compound_sequence_index,\n"
    "    compound_write_group,\n"
    ")\n",
)
replace_once(
    preflight_path,
    "def _availability_for_day(\n    steps: list[PlanStep],\n    *,\n    booking_date: date,\n    context: ReadExecutionContext,\n) -> list[AvailabilityResult] | None:\n",
    "def _availability_for_day(\n"
    "    steps: list[PlanStep],\n"
    "    *,\n"
    "    booking_date: date,\n"
    "    context: ReadExecutionContext,\n"
    "    forced_doctor_id: str | None = None,\n"
    ") -> list[AvailabilityResult] | None:\n",
)
replace_once(
    preflight_path,
    "        doctor_id = params.get(\"doctor_id\")\n        branch_id = params.get(\"branch_id\") or branch_default\n        if service_id is None or doctor_id is None or branch_id is None:\n",
    "        doctor_id = forced_doctor_id or params.get(\"doctor_id\")\n"
    "        branch_id = params.get(\"branch_id\") or branch_default\n"
    "        if service_id is None or doctor_id is None or branch_id is None:\n",
)
replace_once(
    preflight_path,
    "def _find_joint_chain(\n    steps: list[PlanStep],\n    *,\n    requested_anchor: datetime,\n    context: ReadExecutionContext,\n    timezone_name: str,\n) -> tuple[list[AvailabilitySlot] | None, bool]:\n",
    "def _find_joint_chain(\n"
    "    steps: list[PlanStep],\n"
    "    *,\n"
    "    requested_anchor: datetime,\n"
    "    context: ReadExecutionContext,\n"
    "    timezone_name: str,\n"
    "    forced_doctor_id: str | None = None,\n"
    ") -> tuple[list[AvailabilitySlot] | None, bool]:\n",
)
replace_once(
    preflight_path,
    "        results = _availability_for_day(steps, booking_date=current_date, context=context)\n",
    "        results = _availability_for_day(\n"
    "            steps,\n"
    "            booking_date=current_date,\n"
    "            context=context,\n"
    "            forced_doctor_id=forced_doctor_id,\n"
    "        )\n",
)

preflight_helpers = r'''

def _doctor_candidates(step: PlanStep, context: ReadExecutionContext) -> set[str]:
    params = _params(step)
    doctor_id = params.get("doctor_id")
    if doctor_id:
        return {str(doctor_id)}
    raw_ids = params.get("doctor_ids")
    if isinstance(raw_ids, list):
        ids = {str(item) for item in raw_ids if item}
        if ids:
            return ids

    service_id = params.get("service_id")
    catalog = context.catalog if isinstance(context.catalog, dict) else {}
    doctors = catalog.get("doctors") if isinstance(catalog, dict) else None
    if service_id is None or not isinstance(doctors, list):
        return set()
    return {
        str(row["id"])
        for row in doctors
        if isinstance(row, dict)
        and row.get("id")
        and isinstance(row.get("service_ids"), list)
        and str(service_id) in {str(value) for value in row["service_ids"]}
    }


def _common_doctors(steps: list[PlanStep], context: ReadExecutionContext) -> list[str]:
    candidate_sets = [_doctor_candidates(step, context) for step in steps]
    if not candidate_sets or any(not values for values in candidate_sets):
        return []
    common = set.intersection(*candidate_sets)
    return sorted(common)


def _requested_group_anchor(
    steps: list[PlanStep],
    *,
    context: ReadExecutionContext,
    timezone_name: str,
) -> tuple[datetime, str] | None:
    dates: list[dict[str, object]] = []
    times: list[dict[str, object] | None] = []
    for step in steps:
        params = _params(step)
        raw_date = params.get("date")
        raw_time = params.get("time")
        if not isinstance(raw_date, dict):
            return None
        dates.append(raw_date)
        times.append(raw_time if isinstance(raw_time, dict) else None)

    date_modes = {str(item.get("mode")) for item in dates}
    tz = ZoneInfo(timezone_name)
    if date_modes == {"next_available"}:
        local_now = context.now.astimezone(tz)
        return local_now.replace(tzinfo=None), "next_available"
    if date_modes != {"exact"}:
        return None

    exact_dates = {str(item.get("start_date")) for item in dates if item.get("start_date")}
    if len(exact_dates) != 1:
        return None
    day = date.fromisoformat(next(iter(exact_dates)))
    exact_times = {
        str(item.get("start_time"))
        for item in times
        if isinstance(item, dict) and item.get("mode") == "exact" and item.get("start_time")
    }
    if len(exact_times) == 1 and all(
        isinstance(item, dict) and item.get("mode") == "exact" for item in times
    ):
        return datetime.combine(day, datetime.strptime(next(iter(exact_times)), "%H:%M").time()), "exact"
    return datetime.combine(day, datetime.min.time()), "date_only"


def _attach_visit_group(step: PlanStep, visit_group_id: str, doctor_id: str) -> PlanStep:
    reads = []
    for request in step.reads:
        parameters = dict(request.parameters)
        if request.kind == "availability":
            parameters.pop("doctor_ids", None)
            parameters["doctor_id"] = doctor_id
        reads.append(request.model_copy(update={"parameters": parameters}))

    write_intent = step.write_intent
    if write_intent is not None:
        parameters = dict(write_intent.parameters)
        parameters.pop("doctor_ids", None)
        parameters["doctor_id"] = doctor_id
        parameters["visit_group_id"] = visit_group_id
        write_intent = write_intent.model_copy(update={"parameters": parameters})

    facts = dict(step.facts)
    facts.pop("doctor_ids", None)
    facts.update(
        {
            "doctor_id": doctor_id,
            "visit_group_id": visit_group_id,
            "compound_visit_auto_doctor": True,
            "compound_visit_preflight_resolved": True,
        }
    )
    return step.model_copy(update={"reads": reads, "write_intent": write_intent, "facts": facts})


def _auto_resolve_grouped_visits(
    plan: TurnPlan,
    *,
    context: ReadExecutionContext,
    timezone_name: str,
    visit_group_id: str | None,
) -> TurnPlan:
    groups: dict[str, list[PlanStep]] = {}
    for step in plan.steps:
        group = compound_write_group(step)
        if group is not None and _write_kind(step) == "booking":
            groups.setdefault(group, []).append(step)
    if not groups:
        return plan

    replacements: dict[int, PlanStep] = {}
    for _group_key, raw_group in groups.items():
        ordered = sorted(raw_group, key=lambda step: step.operation_index)
        if len(ordered) < 2:
            continue
        common_doctors = _common_doctors(ordered, context)
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
        best: tuple[datetime, str, list[AvailabilitySlot], bool] | None = None
        for doctor_id in common_doctors:
            chain, exact_fits = _find_joint_chain(
                ordered,
                requested_anchor=requested_anchor,
                context=context,
                timezone_name=timezone_name,
                forced_doctor_id=doctor_id,
            )
            if chain is None:
                continue
            candidate = (chain[0].start_at, doctor_id, chain, exact_fits)
            if best is None or candidate[:2] < best[:2]:
                best = candidate

        if best is None:
            for step in ordered:
                replacements[step.operation_index] = _suppress_group_write(
                    step,
                    requested_anchor=requested_anchor,
                )
            continue

        _first_start, doctor_id, chain, exact_fits = best
        allow_write = request_mode == "next_available" or (request_mode == "exact" and exact_fits)
        group_id = visit_group_id or str(uuid4())
        for step, slot in zip(ordered, chain, strict=True):
            rewritten = _rewrite_step_for_slot(
                step,
                slot,
                timezone_name=timezone_name,
                requested_anchor=requested_anchor,
                allow_write=allow_write,
            )
            replacements[step.operation_index] = _attach_visit_group(
                rewritten,
                group_id,
                doctor_id,
            )

    if not replacements:
        return plan
    return plan.model_copy(
        update={"steps": [replacements.get(step.operation_index, step) for step in plan.steps]}
    )
'''
replace_once(
    preflight_path,
    "\ndef preflight_compound_visit_plan(\n",
    preflight_helpers + "\n\ndef preflight_compound_visit_plan(\n",
)
replace_once(
    preflight_path,
    "def preflight_compound_visit_plan(\n    plan: TurnPlan,\n    *,\n    context: ReadExecutionContext,\n    timezone_name: str,\n) -> TurnPlan:\n",
    "def preflight_compound_visit_plan(\n"
    "    plan: TurnPlan,\n"
    "    *,\n"
    "    context: ReadExecutionContext,\n"
    "    timezone_name: str,\n"
    "    visit_group_id: str | None = None,\n"
    ") -> TurnPlan:\n",
)
replace_once(
    preflight_path,
    "    groups: dict[str, list[PlanStep]] = {}\n",
    "    plan = _auto_resolve_grouped_visits(\n"
    "        plan,\n"
    "        context=context,\n"
    "        timezone_name=timezone_name,\n"
    "        visit_group_id=visit_group_id,\n"
    "    )\n"
    "    groups: dict[str, list[PlanStep]] = {}\n",
)

# ---- orchestrator: stable group id + nested transaction rollback barrier -----
orch = "backend/app/services/agent_v2/orchestrator.py"
replace_once(orch, "from uuid import UUID\n", "from uuid import NAMESPACE_URL, UUID, uuid5\n")
replace_once(
    orch,
    "    compound_anchor_key,\n    normalize_compound_turn_plan,\n",
    "    compound_anchor_key,\n    compound_write_group,\n    normalize_compound_turn_plan,\n",
)
replace_once(
    orch,
    "    plan = preflight_compound_visit_plan(\n        plan,\n        context=read_context,\n        timezone_name=timezone_name,\n    )\n    resolved_turn_id = turn_id or str(run_id)\n",
    "    resolved_turn_id = turn_id or str(run_id)\n"
    "    stable_visit_group_id = str(\n"
    "        uuid5(NAMESPACE_URL, f\"tia-v2-visit:{workspace.id}:{resolved_turn_id}\")\n"
    "    )\n"
    "    plan = preflight_compound_visit_plan(\n"
    "        plan,\n"
    "        context=read_context,\n"
    "        timezone_name=timezone_name,\n"
    "        visit_group_id=stable_visit_group_id,\n"
    "    )\n",
)
replace_once(
    orch,
    "    compound_cursors: dict[str, datetime] = {}\n\n    for planned_step in plan.steps:\n",
    "    compound_cursors: dict[str, datetime] = {}\n"
    "    grouped_positions: dict[str, list[int]] = {}\n"
    "    for position, grouped_step in enumerate(plan.steps):\n"
    "        group = compound_write_group(grouped_step)\n"
    "        if group is not None:\n"
    "            grouped_positions.setdefault(group, []).append(position)\n"
    "    active_group_key: str | None = None\n"
    "    active_group_tx = None\n"
    "    active_group_outcome_start = 0\n"
    "    active_group_trace_start = 0\n\n"
    "    for step_position, planned_step in enumerate(plan.steps):\n",
)
# inject group key after effective step creation/persistence, before reads
replace_once(
    orch,
    "        effective_step = persist_initial_task_intent(\n            effective_step,\n            operation=operation,\n            context=semantic_context,\n        )\n\n        if effective_step.state_action == \"update_active\":\n",
    "        effective_step = persist_initial_task_intent(\n"
    "            effective_step,\n"
    "            operation=operation,\n"
    "            context=semantic_context,\n"
    "        )\n"
    "        step_group_key = compound_write_group(effective_step) or compound_write_group(planned_step)\n\n"
    "        if effective_step.state_action == \"update_active\":\n",
)
# start group transaction immediately before executing a group write
replace_once(
    orch,
    "            action_result = write_executor(advanced)\n            outcome = build_step_outcome(\n",
    "            if step_group_key is not None and active_group_tx is None:\n"
    "                active_group_key = step_group_key\n"
    "                active_group_outcome_start = len(outcomes)\n"
    "                active_group_trace_start = len(traces)\n"
    "                active_group_tx = db.begin_nested()\n\n"
    "            action_result = write_executor(advanced)\n"
    "            outcome = build_step_outcome(\n",
)
# on completed group final position, commit savepoint
replace_once(
    orch,
    "            if outcome.status == \"completed\":\n                write_kind = advanced.write_intent.kind if advanced.write_intent is not None else None\n",
    "            if outcome.status == \"completed\":\n"
    "                if (\n"
    "                    step_group_key is not None\n"
    "                    and active_group_key == step_group_key\n"
    "                    and grouped_positions.get(step_group_key)\n"
    "                    and step_position == grouped_positions[step_group_key][-1]\n"
    "                    and active_group_tx is not None\n"
    "                ):\n"
    "                    active_group_tx.commit()\n"
    "                    active_group_tx = None\n"
    "                    active_group_key = None\n"
    "                write_kind = advanced.write_intent.kind if advanced.write_intent is not None else None\n",
)
# before breaking on failed write, rollback and erase earlier success outcomes/traces
replace_once(
    orch,
    "            if outcome.status == \"handoff\":\n                if current_task is not None:\n                    cancelled_existing_task = persisted is not None\n                    current_task = None\n                break\n\n            break\n\n        outcome = build_step_outcome(\n",
    "            if outcome.status == \"handoff\":\n"
    "                if current_task is not None:\n"
    "                    cancelled_existing_task = persisted is not None\n"
    "                    current_task = None\n"
    "            if step_group_key is not None and active_group_key == step_group_key and active_group_tx is not None:\n"
    "                active_group_tx.rollback()\n"
    "                active_group_tx = None\n"
    "                active_group_key = None\n"
    "                outcomes = outcomes[:active_group_outcome_start]\n"
    "                traces = traces[:active_group_trace_start]\n"
    "                outcomes.append(outcome)\n"
    "                traces.append(\n"
    "                    V2RuntimeStepTrace(\n"
    "                        operation_index=advanced.operation_index,\n"
    "                        operation_type=advanced.operation_type,\n"
    "                        disposition_before=planned_step.disposition,\n"
    "                        disposition_after=advanced.disposition,\n"
    "                        read_kinds=tuple(result.kind for result in reads.results),\n"
    "                        outcome=outcome,\n"
    "                    )\n"
    "                )\n"
    "            break\n\n"
    "        outcome = build_step_outcome(\n",
)
# non-write group member after earlier group writes => rollback before appending its outcome
replace_once(
    orch,
    "        traces.append(\n            V2RuntimeStepTrace(\n                operation_index=advanced.operation_index,\n                operation_type=advanced.operation_type,\n                disposition_before=planned_step.disposition,\n                disposition_after=advanced.disposition,\n                read_kinds=tuple(result.kind for result in reads.results),\n                outcome=outcome,\n            )\n        )\n        outcomes.append(outcome)\n",
    "        if step_group_key is not None and active_group_key == step_group_key and active_group_tx is not None:\n"
    "            active_group_tx.rollback()\n"
    "            active_group_tx = None\n"
    "            active_group_key = None\n"
    "            outcomes = outcomes[:active_group_outcome_start]\n"
    "            traces = traces[:active_group_trace_start]\n"
    "        traces.append(\n"
    "            V2RuntimeStepTrace(\n"
    "                operation_index=advanced.operation_index,\n"
    "                operation_type=advanced.operation_type,\n"
    "                disposition_before=planned_step.disposition,\n"
    "                disposition_after=advanced.disposition,\n"
    "                read_kinds=tuple(result.kind for result in reads.results),\n"
    "                outcome=outcome,\n"
    "            )\n"
    "        )\n"
    "        outcomes.append(outcome)\n",
)
# defensive rollback if loop exits unexpectedly with an open compound savepoint
replace_once(
    orch,
    "    persisted_after = _persist_final_task(\n",
    "    if active_group_tx is not None:\n"
    "        active_group_tx.rollback()\n"
    "        outcomes = outcomes[:active_group_outcome_start]\n"
    "        traces = traces[:active_group_trace_start]\n"
    "        active_group_tx = None\n"
    "        active_group_key = None\n\n"
    "    persisted_after = _persist_final_task(\n",
)

# ---- focused tests ---------------------------------------------------------
write(
    "backend/tests/test_v2_same_visit_booking.py",
    r'''from __future__ import annotations

from datetime import UTC, date, datetime
from types import SimpleNamespace
from uuid import UUID

from app.agents.v2.semantic_context import build_semantic_context
from app.agents.v2.turn_contract import DateConstraint, EntityReference, TiaTurnUnderstanding, TurnEntities, TurnOperation
from app.integrations.clinic.base import AvailabilityResult, AvailabilitySlot
from app.services.agent_v2.compound_turn_policy import compound_write_group, normalize_compound_turn_plan
from app.services.agent_v2.compound_visit_preflight import preflight_compound_visit_plan
from app.services.agent_v2.planner import PlannerContext, plan_turn
from app.services.agent_v2.read_executor import ReadExecutionContext

NOW = datetime(2026, 9, 13, 8, 0, tzinfo=UTC)
SERVICE_A = "11111111-1111-1111-1111-111111111111"
SERVICE_B = "22222222-2222-2222-2222-222222222222"
DOCTOR_A = "aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa"
DOCTOR_B = "bbbbbbbb-bbbb-bbbb-bbbb-bbbbbbbbbbbb"
DOCTOR_C = "cccccccc-cccc-cccc-cccc-cccccccccccc"
BRANCH = "33333333-3333-3333-3333-333333333333"
WORKSPACE = UUID("44444444-4444-4444-4444-444444444444")
PATIENT = UUID("55555555-5555-5555-5555-555555555555")
DAY = date(2026, 9, 14)


def _semantic():
    return build_semantic_context(
        {
            "services": [
                {"id": SERVICE_A, "name": "إبط", "duration_minutes": 30},
                {"id": SERVICE_B, "name": "بكيني", "duration_minutes": 30},
            ],
            "doctors": [
                {"id": DOCTOR_A, "name": "أحمد", "service_ids": [SERVICE_A, SERVICE_B]},
                {"id": DOCTOR_B, "name": "مريم", "service_ids": [SERVICE_A, SERVICE_B]},
                {"id": DOCTOR_C, "name": "سارة", "service_ids": [SERVICE_A]},
            ],
        }
    )


def _turn() -> TiaTurnUnderstanding:
    doctor_set = EntityReference(text=None, ref=None, candidate_refs=["D1", "D2"], candidate_mode="set")
    return TiaTurnUnderstanding(
        operations=[
            TurnOperation(
                type="book",
                entities=TurnEntities(
                    service=EntityReference(text=None, ref="S1", candidate_refs=[]),
                    doctor=doctor_set,
                    date=DateConstraint(mode="next_available", start_date=None, end_date=None),
                ),
            ),
            TurnOperation(
                type="book",
                entities=TurnEntities(
                    service=EntityReference(text=None, ref="S2", candidate_refs=[]),
                    doctor=doctor_set,
                    date=DateConstraint(mode="next_available", start_date=None, end_date=None),
                ),
            ),
        ],
        safety_signals=[],
    )


def _slot(service_id: str, doctor_id: str, start: str, end: str) -> AvailabilitySlot:
    return AvailabilitySlot(
        branch_id=BRANCH,
        branch_name="Clinic",
        doctor_id=doctor_id,
        doctor_name="Doctor",
        service_id=service_id,
        service_name="Service",
        start_at=datetime.fromisoformat(start),
        end_at=datetime.fromisoformat(end),
        duration_minutes=30,
        price_minor=10000,
        currency="EGP",
    )


def _result(service_id: str, slots: list[AvailabilitySlot]) -> AvailabilityResult:
    return AvailabilityResult(
        timezone="Africa/Cairo",
        branch_id=BRANCH,
        branch_name="Clinic",
        service_id=service_id,
        service_name="Service",
        service_duration_minutes=30,
        service_price_minor=10000,
        service_currency="EGP",
        slots=tuple(slots),
    )


class _Adapter:
    def get_availability(self, request):
        # Doctor B has the globally earliest joint chain. Doctor A has a later one.
        if request.doctor_id == DOCTOR_B:
            if request.service_id == SERVICE_A:
                return _result(SERVICE_A, [_slot(SERVICE_A, DOCTOR_B, "2026-09-14T07:00:00+00:00", "2026-09-14T07:30:00+00:00")])
            return _result(SERVICE_B, [_slot(SERVICE_B, DOCTOR_B, "2026-09-14T07:30:00+00:00", "2026-09-14T08:00:00+00:00")])
        if request.doctor_id == DOCTOR_A:
            if request.service_id == SERVICE_A:
                return _result(SERVICE_A, [_slot(SERVICE_A, DOCTOR_A, "2026-09-14T09:00:00+00:00", "2026-09-14T09:30:00+00:00")])
            return _result(SERVICE_B, [_slot(SERVICE_B, DOCTOR_A, "2026-09-14T09:30:00+00:00", "2026-09-14T10:00:00+00:00")])
        return _result(request.service_id, [])


class _Db:
    def get(self, _model, _key):
        return SimpleNamespace(workspace_id=WORKSPACE, buffer_before_minutes=0, buffer_after_minutes=0)


def test_multi_service_booking_does_not_ask_customer_to_pick_common_doctor() -> None:
    semantic = _semantic()
    plan = plan_turn(_turn(), PlannerContext(semantic_context=semantic, active_task=None, now=NOW))

    assert len(plan.steps) == 2
    assert all(step.disposition == "read" for step in plan.steps)
    assert all(step.write_intent is not None for step in plan.steps)
    assert all(step.clarification_field is None for step in plan.steps)


def test_nearest_multi_service_visit_selects_one_common_doctor_and_group_id() -> None:
    semantic = _semantic()
    plan = normalize_compound_turn_plan(
        plan_turn(_turn(), PlannerContext(semantic_context=semantic, active_task=None, now=NOW)),
        catalog=semantic.model_input,
    )
    groups = {compound_write_group(step) for step in plan.steps}
    assert len(groups) == 1
    assert None not in groups

    context = ReadExecutionContext(
        db=_Db(),
        workspace=SimpleNamespace(id=WORKSPACE, primary_branch_id=UUID(BRANCH)),
        patient=SimpleNamespace(id=PATIENT),
        now=NOW,
        catalog={
            "services": [
                {"id": SERVICE_A, "duration_minutes": 30},
                {"id": SERVICE_B, "duration_minutes": 30},
            ],
            "doctors": [
                {"id": DOCTOR_A, "service_ids": [SERVICE_A, SERVICE_B]},
                {"id": DOCTOR_B, "service_ids": [SERVICE_A, SERVICE_B]},
                {"id": DOCTOR_C, "service_ids": [SERVICE_A]},
            ],
        },
        adapter=_Adapter(),
    )
    resolved = preflight_compound_visit_plan(
        plan,
        context=context,
        timezone_name="Africa/Cairo",
        visit_group_id="66666666-6666-6666-6666-666666666666",
    )
    bookings = [step for step in resolved.steps if step.write_intent is not None]
    assert len(bookings) == 2
    assert {step.write_intent.parameters["doctor_id"] for step in bookings} == {DOCTOR_B}
    assert {step.write_intent.parameters["visit_group_id"] for step in bookings} == {
        "66666666-6666-6666-6666-666666666666"
    }
    assert all("doctor_ids" not in step.write_intent.parameters for step in bookings)


def test_no_common_doctor_blocks_entire_compound_visit() -> None:
    semantic = _semantic()
    plan = plan_turn(_turn(), PlannerContext(semantic_context=semantic, active_task=None, now=NOW))
    # Force disjoint canonical candidate sets before grouping.
    first, second = plan.steps
    assert first.write_intent is not None and second.write_intent is not None
    first = first.model_copy(update={"write_intent": first.write_intent.model_copy(update={"parameters": {**first.write_intent.parameters, "doctor_ids": [DOCTOR_A]}}), "facts": {**first.facts, "doctor_ids": [DOCTOR_A]}})
    second = second.model_copy(update={"write_intent": second.write_intent.model_copy(update={"parameters": {**second.write_intent.parameters, "doctor_ids": [DOCTOR_B]}}), "facts": {**second.facts, "doctor_ids": [DOCTOR_B]}})
    grouped = normalize_compound_turn_plan(plan.model_copy(update={"steps": [first, second]}), catalog=semantic.model_input)
    context = ReadExecutionContext(
        db=_Db(),
        workspace=SimpleNamespace(id=WORKSPACE, primary_branch_id=UUID(BRANCH)),
        patient=SimpleNamespace(id=PATIENT),
        now=NOW,
        catalog={},
        adapter=_Adapter(),
    )
    resolved = preflight_compound_visit_plan(grouped, context=context, timezone_name="Africa/Cairo")
    assert all(step.write_intent is None for step in resolved.steps)
    assert all(step.disposition == "blocked" for step in resolved.steps)
    assert all(step.facts.get("compound_visit_no_common_doctor") is True for step in resolved.steps)
''',
)

print("compound visit patch applied")
