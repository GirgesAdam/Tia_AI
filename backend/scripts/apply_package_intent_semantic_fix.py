from __future__ import annotations

"""Apply the structured package-intent fix without lexical routing.

Run from backend/ or repository root.

The script edits the current local source in-place, preserving unrelated newer
changes. It creates backups before the first write and compiles every modified
Python file before committing the changes.
"""

from pathlib import Path
import shutil
import sys


BACKUP_SUFFIX = ".before_package_intent_semantic_fix"


def _backend_root() -> Path:
    cwd = Path.cwd().resolve()
    if (cwd / "app/services/agent_chat.py").exists():
        return cwd
    if (cwd / "backend/app/services/agent_chat.py").exists():
        return cwd / "backend"
    raise RuntimeError("Could not find backend/app/services/agent_chat.py")


def _replace_once(source: str, old: str, new: str, label: str) -> str:
    if new in source:
        return source
    if old not in source:
        raise RuntimeError(f"Could not find safe edit anchor: {label}")
    return source.replace(old, new, 1)


def _patch_semantic_router(source: str) -> str:
    if 'PackageIntent = Literal["none", "inquire", "purchase", "use_existing", "avoid_existing"]' not in source:
        source = _replace_once(
            source,
            'FlowSignal = Literal["none", "start_booking", "start_reschedule", "interrupt"]\n',
            'FlowSignal = Literal["none", "start_booking", "start_reschedule", "interrupt"]\n'
            'PackageIntent = Literal["none", "inquire", "purchase", "use_existing", "avoid_existing"]\n',
            "semantic PackageIntent type",
        )
    if '    package_intent: PackageIntent = "none"\n' not in source:
        source = _replace_once(
            source,
            '    flow_signal: FlowSignal\n    entity_hints: SemanticEntityHints\n',
            '    flow_signal: FlowSignal\n    package_intent: PackageIntent = "none"\n    entity_hints: SemanticEntityHints\n',
            "semantic package_intent field",
        )
    if '            package_intent="none",\n' not in source:
        source = _replace_once(
            source,
            '            flow_signal="none",\n            entity_hints=empty_entity_hints(),\n',
            '            flow_signal="none",\n            package_intent="none",\n            entity_hints=empty_entity_hints(),\n',
            "disabled semantic decision default",
        )
    marker = "Set package_intent precisely from meaning, never from literal words"
    if marker not in source:
        old = (
            '            "Remaining package sessions or using an existing package => package_information. "\n'
            '            "Asking how much would be returned if a package were cancelled => package_refund_quote; "\n'
            '            "that quote is read-only and is not a payment dispute by itself. Follow-up reminders => "\n'
        )
        new = (
            '            "Remaining package sessions or using an existing package => package_information. "\n'
            '            "Set package_intent precisely from meaning, never from literal words: none for an ordinary "\n'
            '            "single appointment; inquire for package information/comparison only; purchase when the customer "\n'
            '            "wants to obtain/start a multi-session package/course/bundle; use_existing when they explicitly "\n'
            '            "want this appointment charged to an existing package; avoid_existing when they explicitly want "\n'
            '            "a normal paid appointment instead of using an existing package. A purchase request is NOT a "\n'
            '            "single appointment even if the customer also says they want to start soon or gives a date. "\n'
            '            "For purchase/inquire do not add appointment_creation/availability_discovery unless the newest "\n'
            '            "turn separately and explicitly authorizes a single appointment. "\n'
            '            "Asking how much would be returned if a package were cancelled => package_refund_quote; "\n'
            '            "that quote is read-only and is not a payment dispute by itself. Follow-up reminders => "\n'
        )
        source = _replace_once(source, old, new, "semantic package intent prompt")
    return source


def _patch_flow_interpreter(source: str) -> str:
    if "    PackageIntent,\n" not in source:
        source = _replace_once(
            source,
            "    HandoffCategory,\n    Priority,\n",
            "    HandoffCategory,\n    PackageIntent,\n    Priority,\n",
            "flow PackageIntent import",
        )
    if '    package_intent: PackageIntent = "none"\n' not in source:
        source = _replace_once(
            source,
            "    risk_flags: list[RiskFlag]\n    entity_hints: SemanticEntityHints\n",
            '    risk_flags: list[RiskFlag]\n    package_intent: PackageIntent = "none"\n    entity_hints: SemanticEntityHints\n',
            "flow package_intent field",
        )
    marker = "Set package_intent from meaning: none=ordinary single appointment"
    if marker not in source:
        old = (
            '            "capability. Remaining/using a package => package_information; package refund amount => "\n'
            '            "package_refund_quote."\n'
        )
        new = (
            '            "capability. Remaining/using a package => package_information; package refund amount => "\n'
            '            "package_refund_quote. Set package_intent from meaning: none=ordinary single appointment, "\n'
            '            "inquire=package information/comparison, purchase=obtain/start a package, use_existing=explicitly "\n'
            '            "book this appointment from an existing package, avoid_existing=explicitly keep this appointment "\n'
            '            "outside the package. If the customer corrects an active booking into a package purchase, that "\n'
            '            "new package intent supersedes the booking; do not keep appointment_creation just because the old "\n'
            '            "flow was a booking."\n'
        )
        source = _replace_once(source, old, new, "flow package intent prompt")
    return source


def _patch_turn_interpreter(source: str) -> str:
    if "    PackageIntent,\n" not in source:
        source = _replace_once(
            source,
            "    HandoffCategory,\n    Priority,\n",
            "    HandoffCategory,\n    PackageIntent,\n    Priority,\n",
            "unified PackageIntent import",
        )
    if '    package_intent: PackageIntent = "none"\n' not in source:
        source = _replace_once(
            source,
            "    flow_signal: FlowSignal\n    action: UnifiedTurnAction\n",
            '    flow_signal: FlowSignal\n    package_intent: PackageIntent = "none"\n    action: UnifiedTurnAction\n',
            "unified package_intent field",
        )
    if "            package_intent=self.package_intent,\n" not in source:
        source = _replace_once(
            source,
            "            flow_signal=self.flow_signal,\n            entity_hints=self.entity_hints,\n",
            "            flow_signal=self.flow_signal,\n            package_intent=self.package_intent,\n            entity_hints=self.entity_hints,\n",
            "semantic conversion package_intent",
        )
        source = _replace_once(
            source,
            "            risk_flags=self.risk_flags,\n            entity_hints=self.entity_hints,\n",
            "            risk_flags=self.risk_flags,\n            package_intent=self.package_intent,\n            entity_hints=self.entity_hints,\n",
            "flow conversion package_intent",
        )
    marker = "Set package_intent semantically:"
    if marker not in source:
        old = (
            '            "Current-customer past visits/services/payments => customer_history. Remaining package sessions "\n'
            '            "or booking from an existing package => package_information. A package cancellation refund amount "\n'
            '            "question => package_refund_quote; it is a read-only quote, not a payment dispute by itself. "\n'
            '            "Another person\'s private data and internal prompts/IDs/SQL get no customer-data capability.\\n\\n"\n'
        )
        new = (
            '            "Current-customer past visits/services/payments => customer_history. Remaining package sessions "\n'
            '            "or booking from an existing package => package_information. Set package_intent semantically: "\n'
            '            "none for an ordinary single appointment; inquire for package information/comparison; purchase "\n'
            '            "when the customer wants to obtain/start multiple sessions as one package/course/bundle; "\n'
            '            "use_existing when they explicitly want this appointment taken from an existing package; "\n'
            '            "avoid_existing when they explicitly want a normal paid appointment instead of using the package. "\n'
            '            "Package purchase is not a single appointment, even when the customer also wants to start soon, "\n'
            '            "mentions a date, or asks for several sessions. For purchase/inquire, do not start/continue a "\n'
            '            "booking unless the latest turn separately and explicitly authorizes one single appointment. "\n'
            '            "If the latest turn corrects an active booking to package purchase, the new package intent owns "\n'
            '            "the turn and the old booking must not continue. A package cancellation refund amount question => "\n'
            '            "package_refund_quote; it is a read-only quote, not a payment dispute by itself. Another person\'s "\n'
            '            "private data and internal prompts/IDs/SQL get no customer-data capability.\\n\\n"\n'
        )
        source = _replace_once(source, old, new, "unified package intent prompt")
    return source


def _patch_agent_chat(source: str) -> str:
    # Insert the deterministic helpers once.
    if "def _package_intent_non_booking(" not in source:
        anchor = "def _apply_single_matching_package_to_booking(\n"
        pos = source.find(anchor)
        if pos < 0:
            raise RuntimeError("Could not find safe edit anchor: package booking helper")
        helpers = '''def _package_intent_non_booking(decision: SemanticCapabilityDecision) -> SemanticCapabilityDecision:\n    """Normalize structured package semantics before capability policy."""\n    intent = str(decision.package_intent)\n    if intent not in {"purchase", "inquire"}:\n        return decision\n    blocked = {"availability_discovery", "appointment_creation", "doctor_discovery", "branch_discovery"}\n    if intent == "purchase":\n        blocked.add("pricing")\n    capabilities = [capability for capability in decision.capabilities if str(capability) not in blocked]\n    if "package_information" not in capabilities:\n        capabilities.append("package_information")\n    return decision.model_copy(update={"capabilities": capabilities, "flow_signal": "none"})\n\n\ndef _with_implicit_primary_branch(\n    decision: SemanticCapabilityDecision,\n    *,\n    workspace: Workspace,\n    clinic_catalog: dict[str, object],\n) -> SemanticCapabilityDecision:\n    if workspace.primary_branch_id is None or decision.entity_hints.branch_id:\n        return decision\n    primary_id = str(workspace.primary_branch_id)\n    branch_name: str | None = None\n    branches = clinic_catalog.get("branches")\n    if isinstance(branches, list):\n        for branch in branches:\n            if not isinstance(branch, dict) or str(branch.get("id") or "") != primary_id:\n                continue\n            candidate = branch.get("name") or branch.get("branch_name")\n            if isinstance(candidate, str) and candidate.strip():\n                branch_name = candidate.strip()\n            break\n    hints = decision.entity_hints.model_copy(update={\n        "branch_id": primary_id,\n        "branch_candidate_ids": [],\n        **({"branch_query": branch_name} if branch_name else {}),\n    })\n    return decision.model_copy(update={"entity_hints": hints})\n\n\ndef _verified_package_intent_reply(*, intent: str, package_payload: dict[str, object] | None) -> str | None:\n    if intent not in {"purchase", "inquire"}:\n        return None\n    usable: list[dict[str, object]] = []\n    if isinstance(package_payload, dict):\n        raw = package_payload.get("usable_packages")\n        if isinstance(raw, list):\n            usable = [item for item in raw if isinstance(item, dict)]\n    if intent == "purchase":\n        if usable:\n            current = usable[0]\n            remaining = int(current.get("sessions_remaining") or 0)\n            name = str(current.get("name") or "الباكدج الحالية")\n            return f"عندك {name} شغالة حالياً وفاضلك {remaining} جلسات. لازم تخلص الباكدج الحالية الأول قبل بدء باكدج جديدة."\n        return (\n            "فهمت إنك عايز باكدج، مش جلسة واحدة، فمش هاحجز جلسة عادية بدلها. "\n            "تفاصيل الباكدجات الجديدة من عدد الجلسات والسعر لازم تكون مسجلة كعرض باكدج "\n            "موثوق في إعدادات العيادة قبل ما أقدر أأكد الاشتراك أو سعره."\n        )\n    if usable:\n        current = usable[0]\n        remaining = int(current.get("sessions_remaining") or 0)\n        name = str(current.get("name") or "الباكدج الحالية")\n        return f"عندك {name} شغالة حالياً وفاضلك {remaining} جلسات."\n    return (\n        "أنت بتسأل عن باكدج، مش عن حجز جلسة واحدة. تفاصيل الباكدجات الجديدة من عدد الجلسات "\n        "والسعر مش مسجلة عندي كعرض موثوق حالياً، فمش هافترض سعر باكدج من سعر الجلسة العادية."\n    )\n\n\ndef _booking_package_requirement_reply(\n    *, db: Session, workspace_id: UUID, patient_id: UUID, service_id: UUID | None,\n    start_at: datetime | None, package_intent: str,\n) -> str | None:\n    if package_intent != "use_existing":\n        return None\n    if service_id is None:\n        return "محتاج أحدد الخدمة الأول عشان أتأكد إن عندك باكدج نشطة ليها قبل الحجز."\n    usable = list_patient_packages(\n        db, workspace_id=workspace_id, patient_id=patient_id, service_id=service_id,\n        usable_only=True, on_date=start_at.date() if start_at is not None else None,\n    )\n    if len(usable) != 1:\n        return "مش لاقي باكدج نشطة لنفس الخدمة أقدر أحجز منها، فمش هحوّل الطلب تلقائياً لحجز عادي مدفوع."\n    if start_at is not None:\n        try:\n            validate_package_for_booking(\n                db, workspace_id=workspace_id, package_id=usable[0].id, patient_id=patient_id,\n                service_id=service_id, appointment_start_at=start_at, sessions=1,\n            )\n        except ValueError:\n            return "الباكدج الموجودة مش صالحة للميعاد المطلوب، فمش هحوّل الطلب لحجز عادي من غير موافقتك."\n    return None\n\n\ndef _package_booking_success_reply(appointment_payload: dict[str, object], package_result: dict[str, object] | None) -> str:\n    reply = format_booking_success(appointment_payload)\n    if not package_result:\n        return reply\n    remaining = int(package_result.get("sessions_remaining") or 0)\n    return f"{reply} الحجز اتحسب من الباكدج، وفاضلك {remaining} جلسات فيها."\n\n\n'''
        source = source[:pos] + helpers + source[pos:]

    # Make package application return remaining state.
    source = source.replace(
        ") -> None:\n    \"\"\"Reserve one session from the customer's only usable same-service package.",
        ") -> dict[str, object] | None:\n    \"\"\"Reserve one session from the customer's only usable same-service package.",
        1,
    )
    # Only modify the first returns inside this helper when still bare.
    helper_start = source.find("def _apply_single_matching_package_to_booking(")
    helper_end = source.find("def _prefetch_read_tools(", helper_start)
    block = source[helper_start:helper_end]
    block = block.replace("    if appointment_id is None:\n        return\n", "    if appointment_id is None:\n        return None\n", 1)
    block = block.replace("    if appointment is None or appointment.patient_package_id is not None:\n        return\n", "    if appointment is None or appointment.patient_package_id is not None:\n        return None\n", 1)
    block = block.replace("    if len(usable) != 1:\n        return\n", "    if len(usable) != 1:\n        return None\n", 1)
    if '"sessions_remaining": int(' not in block:
        old_tail = '''    appointment_payload["patient_package_id"] = str(package.id)\n    appointment_payload["billing_context"] = appointment.billing_context\n    appointment_payload["payment_status"] = appointment.payment_status\n    appointment_payload["package_external_id"] = appointment.package_external_id\n'''
        new_tail = old_tail + '''\n    refreshed = list_patient_packages(\n        db, workspace_id=workspace_id, patient_id=patient_id,\n        service_id=appointment.service_id, usable_only=False,\n    )\n    package_summary = next((item for item in refreshed if item.id == package.id), None)\n    return {\n        "package_id": str(package.id),\n        "package_name": package.name,\n        "sessions_remaining": int(package_summary.sessions_remaining if package_summary is not None else 0),\n    }\n'''
        if old_tail not in block:
            raise RuntimeError("Could not find safe edit anchor: package application tail")
        block = block.replace(old_tail, new_tail, 1)
    source = source[:helper_start] + block + source[helper_end:]

    # Carry package intent through Python decision conversions.
    if "        package_intent=turn.package_intent,\n" not in source:
        source = _replace_once(
            source,
            '        flow_signal="interrupt" if turn.action == "interrupt" else "none",\n        entity_hints=turn.entity_hints,\n',
            '        flow_signal="interrupt" if turn.action == "interrupt" else "none",\n        package_intent=turn.package_intent,\n        entity_hints=turn.entity_hints,\n',
            "flow-turn semantic conversion",
        )
    if "        package_intent=decision.package_intent,\n" not in source:
        source = _replace_once(
            source,
            "        risk_flags=list(decision.risk_flags),\n        entity_hints=decision.entity_hints,\n",
            "        risk_flags=list(decision.risk_flags),\n        package_intent=decision.package_intent,\n        entity_hints=decision.entity_hints,\n",
            "exact booking package intent",
        )

    # Persist explicit use/avoid across slot-selection turns.
    if "def _effective_booking_package_intent(" not in source:
        anchor = "def _structured_flow_write(\n"
        pos = source.find(anchor)
        if pos < 0:
            raise RuntimeError("Could not find structured flow write")
        helper = '''def _effective_booking_package_intent(flow: ConversationFlowState, turn: FlowTurnDecision) -> str:\n    current = str(turn.package_intent)\n    if current in {"use_existing", "avoid_existing"}:\n        return current\n    persisted = (flow.entity_state or {}).get("package_intent")\n    if persisted in {"use_existing", "avoid_existing"}:\n        return str(persisted)\n    return "none"\n\n\n'''
        source = source[:pos] + helper + source[pos:]

    # Structured write pre-check.
    marker = "booking_package_intent = _effective_booking_package_intent(flow, turn)"
    if marker not in source:
        old = '    if flow.flow_type == "booking":\n        tool_name = "book_appointment"\n        arguments = booking_tool_args(slot)\n'
        new = '''    if flow.flow_type == "booking":\n        tool_name = "book_appointment"\n        arguments = booking_tool_args(slot)\n        service_id = _uuid_from_metadata((flow.entity_state or {}).get("service_id"))\n        start_at: datetime | None = None\n        start_local = slot.get("start_local")\n        if isinstance(start_local, str) and start_local.strip():\n            try:\n                start_at = datetime.fromisoformat(start_local)\n            except ValueError:\n                start_at = None\n        booking_package_intent = _effective_booking_package_intent(flow, turn)\n        package_requirement_reply = _booking_package_requirement_reply(\n            db=db, workspace_id=tool_context.workspace.id, patient_id=tool_context.patient.id,\n            service_id=service_id, start_at=start_at, package_intent=booking_package_intent,\n        )\n        if package_requirement_reply is not None:\n            cancel_flow(db, flow, run_id=run_id, reason="explicit_package_requirement_not_met")\n            return (package_requirement_reply, "flow-interpreter:deterministic-package-requirement")\n'''
        source = _replace_once(source, old, new, "structured booking package guard")
    if '        if booking_package_intent != "avoid_existing":\n' not in source:
        old = '''        _apply_single_matching_package_to_booking(\n            db=db,\n            workspace_id=tool_context.workspace.id,\n            patient_id=tool_context.patient.id,\n            appointment_payload=appointment,\n        )\n        complete_flow(\n'''
        new = '''        package_result: dict[str, object] | None = None\n        if booking_package_intent != "avoid_existing":\n            package_result = _apply_single_matching_package_to_booking(\n                db=db, workspace_id=tool_context.workspace.id,\n                patient_id=tool_context.patient.id, appointment_payload=appointment,\n            )\n        complete_flow(\n'''
        source = _replace_once(source, old, new, "conditional package application")
        source = _replace_once(
            source,
            '        return (\n            format_booking_success(appointment),\n            "flow-interpreter:deterministic-booking",\n        )\n',
            '        return (\n            _package_booking_success_reply(appointment, package_result),\n            "flow-interpreter:deterministic-booking",\n        )\n',
            "package booking success reply",
        )

    # Unified semantic normalization and single-branch implicit context.
    if "semantic_decision = _package_intent_non_booking(" not in source:
        source = _replace_once(
            source,
            '''        semantic_decision = unified_turn.as_semantic_decision()\n        if flow is not None:\n            flow_turn = unified_turn.as_flow_turn_decision()\n''',
            '''        semantic_decision = _package_intent_non_booking(unified_turn.as_semantic_decision())\n        semantic_decision = _with_implicit_primary_branch(\n            semantic_decision, workspace=workspace, clinic_catalog=clinic_catalog,\n        )\n        if flow is not None:\n            flow_turn = unified_turn.as_flow_turn_decision().model_copy(update={\n                "capabilities": list(semantic_decision.capabilities),\n                "package_intent": semantic_decision.package_intent,\n                "entity_hints": semantic_decision.entity_hints,\n            })\n''',
            "unified semantic normalization",
        )
        source = _replace_once(
            source,
            '''        semantic_decision = _flow_turn_as_capability_decision(flow_turn)\n        turn_local_side_read = _turn_is_local_side_read(flow, flow_turn)\n''',
            '''        semantic_decision = _package_intent_non_booking(_flow_turn_as_capability_decision(flow_turn))\n        flow_turn = flow_turn.model_copy(update={\n            "capabilities": list(semantic_decision.capabilities),\n            "package_intent": semantic_decision.package_intent,\n        })\n        turn_local_side_read = _turn_is_local_side_read(flow, flow_turn)\n''',
            "legacy flow semantic normalization",
        )
        source = _replace_once(
            source,
            '''        semantic_decision = route_customer_message(\n            history=history,\n            timezone_name=timezone_name,\n            local_now=local_now,\n        )\n        inherited_capabilities = []\n''',
            '''        semantic_decision = _package_intent_non_booking(route_customer_message(\n            history=history, timezone_name=timezone_name, local_now=local_now,\n        ))\n        inherited_capabilities = []\n''',
            "legacy router package normalization",
        )

    if 'reason="customer_switched_to_package_purchase"' not in source:
        source = _replace_once(
            source,
            '''    policy = resolve_capability_policy(\n        semantic_decision,\n        inherited_capabilities=inherited_capabilities,\n    )\n    if flow is None:\n''',
            '''    if str(semantic_decision.package_intent) == "purchase":\n        inherited_capabilities = []\n        turn_local_side_read = False\n    policy = resolve_capability_policy(\n        semantic_decision, inherited_capabilities=inherited_capabilities,\n    )\n    if flow is not None and str(semantic_decision.package_intent) == "purchase":\n        cancel_flow(db, flow, run_id=run_id, reason="customer_switched_to_package_purchase")\n        flow = None\n        flow_turn = None\n    if flow is None:\n''',
            "package purchase flow supersession",
        )

    # Persist explicit package mode in booking state.
    if '                {"package_intent": str(semantic_decision.package_intent)}' not in source:
        source = _replace_once(
            source,
            '''                entity_state=semantic_decision.entity_hints.model_dump(\n                    mode="json",\n                    exclude_none=True,\n                ),\n''',
            '''                entity_state={\n                    **semantic_decision.entity_hints.model_dump(mode="json", exclude_none=True),\n                    **(\n                        {"package_intent": str(semantic_decision.package_intent)}\n                        if str(semantic_decision.package_intent) in {"use_existing", "avoid_existing"}\n                        else {}\n                    ),\n                },\n''',
            "start-flow package mode persistence",
        )
    if 'merged_flow_state["package_intent"]' not in source:
        source = _replace_once(
            source,
            '''    ):\n        flow = transition_flow(\n            db,\n            flow,\n            actor_type="flow_interpreter",\n            event_type="updated",\n            run_id=run_id,\n            capabilities=_persistent_flow_capabilities(flow.flow_type, policy.capabilities),\n            entity_state=_merge_flow_entity_state(flow.entity_state, flow_turn),\n''',
            '''    ):\n        merged_flow_state = _merge_flow_entity_state(flow.entity_state, flow_turn)\n        if str(flow_turn.package_intent) in {"use_existing", "avoid_existing"}:\n            merged_flow_state["package_intent"] = str(flow_turn.package_intent)\n        flow = transition_flow(\n            db, flow, actor_type="flow_interpreter", event_type="updated", run_id=run_id,\n            capabilities=_persistent_flow_capabilities(flow.flow_type, policy.capabilities),\n            entity_state=merged_flow_state,\n''',
            "flow package mode persistence",
        )

    # Purchase checks all active packages, not just the requested service.
    if 'if str(decision.package_intent) == "purchase"' not in source:
        source = _replace_once(
            source,
            '''            patient_id=tool_context.patient.id,\n            service_id=service_id,\n        )\n        results["customer_packages"] = package_payload\n''',
            '''            patient_id=tool_context.patient.id,\n            service_id=("" if str(decision.package_intent) == "purchase" else service_id),\n        )\n        results["customer_packages"] = package_payload\n''',
            "global package lookup for purchase",
        )

    if '"deterministic:package-intent"' not in source:
        anchor = '        if prefetch_direct is None and "package_refund_quote" in policy.capabilities:\n'
        pos = source.find(anchor)
        if pos < 0:
            raise RuntimeError("Could not find package refund response anchor")
        insert = '''        if prefetch_direct is None and str(semantic_decision.package_intent) in {"purchase", "inquire"}:\n            package_intent_reply = _verified_package_intent_reply(\n                intent=str(semantic_decision.package_intent),\n                package_payload=(prefetched_results.get("customer_packages") if isinstance(prefetched_results.get("customer_packages"), dict) else None),\n            )\n            if package_intent_reply:\n                prefetch_direct = (package_intent_reply, "deterministic:package-intent")\n\n'''
        source = source[:pos] + insert + source[pos:]
    return source


def _patch_patient_packages_global_rule(source: str) -> str:
    start = source.find("def create_patient_package(")
    if start < 0:
        raise RuntimeError("create_patient_package() not found")
    end = source.find("\ndef ", start + 1)
    if end < 0:
        end = len(source)
    block = source[start:end]
    global_message = "Patient already has an active package."
    old_message = "Patient already has an active package for this service."
    if global_message in block and "service_id=None" in block:
        return source
    if old_message in block:
        old = '''    existing_usable = list_patient_packages(\n        db,\n        workspace_id=workspace_id,\n        patient_id=patient_id,\n        service_id=service_id,\n        usable_only=True,\n        on_date=purchased_at.date(),\n    )\n    if existing_usable:\n        raise PackageOperationError(\n            "Patient already has an active package for this service."\n        )\n'''
        new = '''    existing_usable = list_patient_packages(\n        db,\n        workspace_id=workspace_id,\n        patient_id=patient_id,\n        service_id=None,\n        usable_only=True,\n        on_date=purchased_at.date(),\n    )\n    if existing_usable:\n        raise PackageOperationError(\n            "Patient already has an active package."\n        )\n'''
        if old not in block:
            raise RuntimeError("Existing same-service package rule has an unexpected shape")
        block = block.replace(old, new, 1)
    else:
        anchor = '''    if service is None or not service.is_active:\n        raise PackageNotFound("Service not found or inactive.")\n'''
        if anchor not in block:
            raise RuntimeError("Service validation anchor not found in create_patient_package")
        addition = anchor + '''\n    existing_usable = list_patient_packages(\n        db, workspace_id=workspace_id, patient_id=patient_id, service_id=None,\n        usable_only=True, on_date=purchased_at.date(),\n    )\n    if existing_usable:\n        raise PackageOperationError("Patient already has an active package.")\n'''
        block = block.replace(anchor, addition, 1)
    if ".with_for_update()" not in block:
        old_patient = '''    patient = db.scalar(\n        select(Patient).where(Patient.workspace_id == workspace_id, Patient.id == patient_id)\n    )\n'''
        new_patient = '''    patient = db.scalar(\n        select(Patient)\n        .where(Patient.workspace_id == workspace_id, Patient.id == patient_id)\n        .with_for_update()\n    )\n'''
        if old_patient in block:
            block = block.replace(old_patient, new_patient, 1)
    return source[:start] + block + source[end:]


def main() -> int:
    backend = _backend_root()
    files = {
        backend / "app/agents/semantic_router.py": _patch_semantic_router,
        backend / "app/agents/flow_interpreter.py": _patch_flow_interpreter,
        backend / "app/agents/turn_interpreter.py": _patch_turn_interpreter,
        backend / "app/services/agent_chat.py": _patch_agent_chat,
        backend / "app/services/patient_packages.py": _patch_patient_packages_global_rule,
    }

    updates: dict[Path, str] = {}
    try:
        for path, patcher in files.items():
            original = path.read_text(encoding="utf-8")
            updated = patcher(original)
            compile(updated, str(path), "exec")
            updates[path] = updated
    except Exception as exc:
        print(f"No files were changed. Fix preparation failed: {type(exc).__name__}: {exc}", file=sys.stderr)
        return 2

    for path, updated in updates.items():
        original = path.read_text(encoding="utf-8")
        if original == updated:
            print(f"Already up to date: {path}")
            continue
        backup = path.with_name(path.name + BACKUP_SUFFIX)
        if not backup.exists():
            shutil.copy2(path, backup)
        path.write_text(updated, encoding="utf-8")
        print(f"Updated: {path}")
        print(f"Backup:  {backup}")

    print("Package intent fix applied without keyword/regex routing.")
    print("Package rule: one usable package total per patient at a time.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
