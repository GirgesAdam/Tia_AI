from __future__ import annotations

from pathlib import Path
from textwrap import dedent

ROOT = Path(__file__).resolve().parents[2]


def replace_once(path: str, old: str, new: str) -> None:
    target = ROOT / path
    text = target.read_text(encoding="utf-8")
    if text.count(old) != 1:
        raise RuntimeError(f"Expected exactly one marker in {path}: {old[:80]!r}; found {text.count(old)}")
    target.write_text(text.replace(old, new, 1), encoding="utf-8")


normalization = dedent('''\
    from __future__ import annotations

    from app.agents.v2.turn_contract import TiaTurnUnderstanding, TurnOperation

    _EXPANDABLE_OPERATION_TYPES = frozenset({"availability", "book"})
    _MAX_OPERATIONS = 6


    def _service_set(operation: TurnOperation) -> list[str]:
        service = operation.entities.service
        if (
            operation.type not in _EXPANDABLE_OPERATION_TYPES
            or service is None
            or service.ref is not None
            or service.candidate_mode != "set"
        ):
            return []
        return list(dict.fromkeys(ref for ref in service.candidate_refs if ref))


    def expand_multi_service_operations(
        turn: TiaTurnUnderstanding,
    ) -> tuple[TiaTurnUnderstanding, dict[int, str]]:
        """Expand one semantic multi-service visit into addressable component operations.

        The interpreter is allowed to represent a requested same-visit service set as one
        availability/book operation. Runtime planning, verification, and write ownership are
        operation-index based, so expand only those visit-shaped operations before planning.
        Pricing/comparison/service-info sets remain untouched. The returned index map is runtime
        metadata only; it does not change the provider-facing structured-output contract.
        """
        projected = 0
        service_sets: list[list[str]] = []
        for operation in turn.operations:
            refs = _service_set(operation)
            service_sets.append(refs)
            projected += len(refs) if len(refs) > 1 else 1
        if projected > _MAX_OPERATIONS:
            return turn, {}

        expanded: list[TurnOperation] = []
        visit_groups: dict[int, str] = {}
        for source_index, (operation, refs) in enumerate(zip(turn.operations, service_sets, strict=True)):
            if len(refs) <= 1:
                expanded.append(operation)
                continue
            group_key = f"semantic-multi-service:{source_index}"
            assert operation.entities.service is not None
            for ref in refs:
                service = operation.entities.service.model_copy(
                    update={"ref": ref, "candidate_refs": []}
                )
                component = operation.model_copy(
                    update={
                        "entities": operation.entities.model_copy(update={"service": service})
                    }
                )
                visit_groups[len(expanded)] = group_key
                expanded.append(component)

        if not visit_groups:
            return turn, {}
        return turn.model_copy(update={"operations": expanded}), visit_groups
''')
(ROOT / "backend/app/services/agent_v2/turn_normalization.py").write_text(normalization, encoding="utf-8")

replace_once(
    "backend/app/services/agent_v2/orchestrator.py",
    "from app.services.agent_v2.compound_visit_preflight import preflight_compound_visit_plan\n",
    "from app.services.agent_v2.compound_visit_preflight import preflight_compound_visit_plan\n"
    "from app.services.agent_v2.turn_normalization import expand_multi_service_operations\n",
)
replace_once(
    "backend/app/services/agent_v2/orchestrator.py",
    """    understanding = interpret_customer_turn_v2(\n        history=history,\n        semantic_context=semantic_context,\n        timezone_name=timezone_name,\n        local_now=local_now,\n    )\n    plan = plan_turn(\n""",
    """    understanding = interpret_customer_turn_v2(\n        history=history,\n        semantic_context=semantic_context,\n        timezone_name=timezone_name,\n        local_now=local_now,\n    )\n    understanding, semantic_visit_groups = expand_multi_service_operations(understanding)\n    plan = plan_turn(\n""",
)
replace_once(
    "backend/app/services/agent_v2/orchestrator.py",
    "    plan = normalize_compound_turn_plan(plan, catalog=canonical_catalog)\n",
    "    plan = normalize_compound_turn_plan(\n"
    "        plan,\n"
    "        catalog=canonical_catalog,\n"
    "        operation_visit_groups=semantic_visit_groups,\n"
    "    )\n",
)

replace_once(
    "backend/app/services/agent_v2/planner.py",
    '    if ambiguous.get("doctor") and not (compound_book and operation.type == "book"):\n',
    '    if ambiguous.get("doctor") and not (\n'
    '        operation.type == "availability" or (compound_book and operation.type == "book")\n'
    '    ):\n',
)

replace_once(
    "backend/app/services/agent_v2/compound_turn_policy.py",
    '_COMPOUND_WRITE_GROUP_FACT = "compound_write_group"\n',
    '_COMPOUND_WRITE_GROUP_FACT = "compound_write_group"\n'
    '_COMPOUND_VISIT_GROUP_FACT = "compound_visit_group"\n',
)
replace_once(
    "backend/app/services/agent_v2/compound_turn_policy.py",
    """                        _COMPOUND_WRITE_GROUP_FACT: group_key,\n                        _COMPOUND_GROUPED_FACT: True,\n""",
    """                        _COMPOUND_WRITE_GROUP_FACT: group_key,\n                        _COMPOUND_VISIT_GROUP_FACT: group_key,\n                        _COMPOUND_GROUPED_FACT: True,\n""",
)
replace_once(
    "backend/app/services/agent_v2/compound_turn_policy.py",
    """def compound_write_group(step: PlanStep) -> str | None:\n    value = step.facts.get(_COMPOUND_WRITE_GROUP_FACT)\n    return str(value) if value not in (None, "") else None\n\n\ndef normalize_compound_turn_plan(\n    plan: TurnPlan,\n    *,\n    catalog: dict[str, Any],\n) -> TurnPlan:\n""",
    """def _tag_semantic_visit_groups(\n    steps: list[PlanStep],\n    operation_visit_groups: dict[int, str] | None,\n) -> list[PlanStep]:\n    if not operation_visit_groups:\n        return steps\n    tagged: list[PlanStep] = []\n    for step in steps:\n        group_key = operation_visit_groups.get(step.operation_index)\n        if group_key is not None:\n            step = step.model_copy(\n                update={\n                    "facts": {\n                        **step.facts,\n                        _COMPOUND_VISIT_GROUP_FACT: group_key,\n                        _COMPOUND_GROUPED_FACT: True,\n                    }\n                }\n            )\n        tagged.append(step)\n    return tagged\n\n\ndef compound_write_group(step: PlanStep) -> str | None:\n    value = step.facts.get(_COMPOUND_WRITE_GROUP_FACT)\n    return str(value) if value not in (None, "") else None\n\n\ndef compound_visit_group(step: PlanStep) -> str | None:\n    value = step.facts.get(_COMPOUND_VISIT_GROUP_FACT)\n    if value in (None, ""):\n        return compound_write_group(step)\n    return str(value)\n\n\ndef normalize_compound_turn_plan(\n    plan: TurnPlan,\n    *,\n    catalog: dict[str, Any],\n    operation_visit_groups: dict[int, str] | None = None,\n) -> TurnPlan:\n""",
)
replace_once(
    "backend/app/services/agent_v2/compound_turn_policy.py",
    """    steps = _tag_and_order_package_dependencies(list(plan.steps))\n    steps = _tag_compound_write_group(steps)\n    steps = _sequence_shared_anchor_bookings(steps, catalog=catalog)\n""",
    """    steps = _tag_and_order_package_dependencies(list(plan.steps))\n    steps = _tag_compound_write_group(steps)\n    steps = _tag_semantic_visit_groups(steps, operation_visit_groups)\n    steps = _sequence_shared_anchor_bookings(steps, catalog=catalog)\n""",
)

replace_once(
    "backend/app/services/agent_v2/compound_visit_preflight.py",
    """    compound_anchor_key,\n    compound_sequence_index,\n    compound_write_group,\n)\n""",
    """    compound_anchor_key,\n    compound_sequence_index,\n    compound_visit_group,\n)\n""",
)
replace_once(
    "backend/app/services/agent_v2/compound_visit_preflight.py",
    """def _params(step: PlanStep) -> dict[str, object]:\n    return dict(step.write_intent.parameters) if step.write_intent is not None else {}\n""",
    """def _params(step: PlanStep) -> dict[str, object]:\n    if step.write_intent is not None:\n        return dict(step.write_intent.parameters)\n    for request in step.reads:\n        if request.kind == "availability":\n            return dict(request.parameters)\n    return dict(step.facts)\n""",
)
replace_once(
    "backend/app/services/agent_v2/compound_visit_preflight.py",
    """    groups: dict[str, list[PlanStep]] = {}\n    for step in plan.steps:\n        group = compound_write_group(step)\n        if group is not None and _write_kind(step) == "booking":\n            groups.setdefault(group, []).append(step)\n""",
    """    groups: dict[str, list[PlanStep]] = {}\n    for step in plan.steps:\n        group = compound_visit_group(step)\n        has_availability_read = any(request.kind == "availability" for request in step.reads)\n        if group is not None and (_write_kind(step) == "booking" or has_availability_read):\n            groups.setdefault(group, []).append(step)\n""",
)

# Regression tests target normalization and policy ownership. Live regression covers the
# real adapter/common-doctor chain after deployment.
tests = dedent('''\
    from app.agents.v2.turn_contract import (
        DateConstraint,
        EntityReference,
        TiaTurnUnderstanding,
        TurnEntities,
        TurnOperation,
    )
    from app.services.agent_v2.compound_turn_policy import (
        compound_visit_group,
        compound_write_group,
        normalize_compound_turn_plan,
    )
    from app.services.agent_v2.planner import PlanStep, ReadRequest, TurnPlan, WriteIntent
    from app.services.agent_v2.turn_normalization import expand_multi_service_operations


    def _multi_service_operation(kind: str = "availability") -> TurnOperation:
        return TurnOperation(
            type=kind,
            entities=TurnEntities(
                service=EntityReference(
                    text="service A and service B",
                    candidate_refs=["S1", "S2"],
                    candidate_mode="set",
                ),
                doctor=EntityReference(
                    text="any suitable doctor",
                    candidate_refs=["D1", "D2"],
                    candidate_mode="set",
                ),
                date=DateConstraint(mode="next_available"),
            ),
            execution_intent="execute" if kind == "book" else "informational",
        )


    def test_multi_service_availability_expands_before_planning() -> None:
        turn = TiaTurnUnderstanding(operations=[_multi_service_operation()])
        expanded, groups = expand_multi_service_operations(turn)

        assert [operation.entities.service.ref for operation in expanded.operations] == ["S1", "S2"]
        assert all(operation.entities.service.candidate_refs == [] for operation in expanded.operations)
        assert groups == {0: "semantic-multi-service:0", 1: "semantic-multi-service:0"}
        assert all(operation.entities.doctor.candidate_refs == ["D1", "D2"] for operation in expanded.operations)


    def test_multi_service_book_expands_and_preserves_execution_intent() -> None:
        turn = TiaTurnUnderstanding(operations=[_multi_service_operation("book")])
        expanded, groups = expand_multi_service_operations(turn)

        assert len(expanded.operations) == 2
        assert all(operation.type == "book" for operation in expanded.operations)
        assert all(operation.execution_intent == "execute" for operation in expanded.operations)
        assert len(set(groups.values())) == 1


    def test_non_visit_service_set_is_not_expanded() -> None:
        pricing = _multi_service_operation().model_copy(update={"type": "pricing"})
        turn = TiaTurnUnderstanding(operations=[pricing])

        expanded, groups = expand_multi_service_operations(turn)

        assert expanded is turn
        assert groups == {}


    def test_expansion_fails_closed_when_turn_would_exceed_operation_limit() -> None:
        turn = TiaTurnUnderstanding(
            operations=[
                _multi_service_operation(),
                _multi_service_operation(),
                _multi_service_operation(),
                TurnOperation(type="social", entities=TurnEntities()),
            ]
        )

        expanded, groups = expand_multi_service_operations(turn)

        assert expanded is turn
        assert groups == {}


    def _availability_step(index: int, service_id: str) -> PlanStep:
        params = {
            "service_id": service_id,
            "doctor_ids": ["D1", "D2"],
            "date": {"mode": "next_available", "start_date": None, "end_date": None},
        }
        return PlanStep(
            operation_index=index,
            operation_type="availability",
            disposition="read",
            reads=[ReadRequest(kind="availability", parameters=params)],
            response_goal="present_availability",
            facts=params,
        )


    def test_semantic_multi_service_availability_gets_one_logical_visit_group() -> None:
        plan = TurnPlan(steps=[_availability_step(0, "S1"), _availability_step(1, "S2")])
        normalized = normalize_compound_turn_plan(
            plan,
            catalog={},
            operation_visit_groups={0: "semantic-multi-service:0", 1: "semantic-multi-service:0"},
        )

        assert {compound_visit_group(step) for step in normalized.steps} == {
            "semantic-multi-service:0"
        }
        assert all(compound_write_group(step) is None for step in normalized.steps)


    def _purchase(index: int, service_id: str) -> PlanStep:
        return PlanStep(
            operation_index=index,
            operation_type="buy_package",
            disposition="read",
            write_intent=WriteIntent(
                kind="buy_package",
                authorized=True,
                parameters={"service_id": service_id},
            ),
            facts={"service_id": service_id},
        )


    def _booking(index: int, service_id: str) -> PlanStep:
        params = {
            "service_id": service_id,
            "date": {"mode": "next_available", "start_date": None, "end_date": None},
        }
        return PlanStep(
            operation_index=index,
            operation_type="book",
            disposition="read",
            reads=[ReadRequest(kind="availability", parameters=params)],
            write_intent=WriteIntent(kind="booking", authorized=True, parameters=params),
            facts=params,
        )


    def test_two_package_purchases_and_expanded_bookings_share_atomic_write_group() -> None:
        plan = TurnPlan(
            steps=[
                _purchase(0, "S1"),
                _purchase(1, "S2"),
                _booking(2, "S1"),
                _booking(3, "S2"),
            ]
        )
        normalized = normalize_compound_turn_plan(
            plan,
            catalog={},
            operation_visit_groups={2: "semantic-multi-service:2", 3: "semantic-multi-service:2"},
        )

        groups = [compound_write_group(step) for step in normalized.steps]
        assert all(group is not None for group in groups)
        assert len(set(groups)) == 1
        assert {compound_visit_group(step) for step in normalized.steps if step.operation_type == "book"} == {
            "semantic-multi-service:2"
        }
''')
(ROOT / "backend/tests/test_v2_multi_service_visit_semantics.py").write_text(tests, encoding="utf-8")
