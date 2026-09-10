from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]


def replace_once(source: str, old: str, new: str, label: str) -> str:
    count = source.count(old)
    if count != 1:
        raise RuntimeError(f"{label}: expected one marker, found {count}")
    return source.replace(old, new, 1)


def patch_interpreter() -> None:
    path = ROOT / "backend/app/agents/turn_interpreter.py"
    source = path.read_text(encoding="utf-8")
    marker = '        "PACKAGES: distinguish one appointment from a package/course of multiple sessions by meaning, "\n'
    insert = (
        '        "COMPOUND REQUESTS: when the latest customer turn clearly asks for two or more independently "\n'
        '        "executable commercial operations, put one operation per requested_items entry in customer order. "\n'
        '        "Supported compound operations are appointment booking and package purchase. Do not create requested_items "\n'
        '        "for alternatives, uncertain service matching, comparisons, or one operation with multiple candidate IDs. "\n'
        '        "Each appointment item owns its own service, doctor, device, date/time constraints, and whether it should "\n'
        '        "use_existing or avoid_existing package entitlement. Each package_purchase item owns exactly one service, "\n'
        '        "configured device, and requested 3/6/9 session tier. Preserve explicit shared constraints by copying them "\n'
        '        "onto each affected item. If the customer asks to buy a package and book its first session, emit the package "\n'
        '        "purchase item before the appointment item and set the appointment item package_intent=use_existing. "\n'
        '        "Use at most six requested_items. Leave requested_items empty for ordinary single-operation turns. "\n'
        '        "For a compound request include the union of required capabilities; Python will sequence and authorize "\n'
        '        "each grounded item deterministically. Never collapse two explicitly requested services into ambiguity.\\n\\n"\n'
    )
    source = replace_once(source, marker, insert + marker, "compound interpreter prompt")
    path.write_text(source, encoding="utf-8")


def patch_agent_chat() -> None:
    path = ROOT / "backend/app/services/agent_chat.py"
    source = path.read_text(encoding="utf-8")

    source = replace_once(
        source,
        "from app.agents.turn_models import FlowTurnDecision, SemanticCapabilityDecision\n",
        "from app.agents.turn_models import (\n"
        "    CompoundRequestedItem,\n"
        "    FlowTurnDecision,\n"
        "    SemanticCapabilityDecision,\n"
        ")\n",
        "turn model imports",
    )
    source = replace_once(
        source,
        "from app.services.handoffs import get_active_handoff\n",
        "from app.services.handoffs import get_active_handoff\n"
        "from app.services.compound_customer_requests import (\n"
        "    COMPOUND_CURRENT_SERVICE_KEY,\n"
        "    appointment_decision_from_item,\n"
        "    appointment_item_state,\n"
        "    appointment_items,\n"
        "    compound_progress,\n"
        "    compound_union_decision,\n"
        "    ground_compound_requested_items,\n"
        "    has_compound_request,\n"
        "    package_items,\n"
        "    purchase_compound_package_batch,\n"
        "    queue_from_flow_state,\n"
        ")\n",
        "compound service imports",
    )

    helper_marker = "def _run_after_inbound(\n"
    helpers = '''def _compound_initial_entity_state(\n    *,\n    decision: SemanticCapabilityDecision,\n    first_item: CompoundRequestedItem,\n    remaining: list[CompoundRequestedItem],\n    total: int,\n    clinic_catalog: dict[str, object],\n) -> dict[str, object]:\n    state = appointment_item_state(\n        first_item,\n        remaining=remaining,\n        total=total,\n        completed=0,\n        catalog=clinic_catalog,\n    )\n    for key in ("branch_query", "branch_id"):\n        value = getattr(decision.entity_hints, key, None)\n        if value:\n            state[key] = value\n    branch_candidates = list(decision.entity_hints.branch_candidate_ids or [])\n    if branch_candidates:\n        state["branch_candidate_ids"] = branch_candidates\n    return state\n\n\ndef _advance_compound_booking_flow(\n    *,\n    db: Session,\n    flow: ConversationFlowState,\n    workspace: Workspace,\n    run_id: UUID,\n    result: dict[str, object],\n) -> tuple[ConversationFlowState | None, CompoundRequestedItem | None]:\n    queue = queue_from_flow_state(flow.entity_state)\n    if not queue:\n        complete_flow(\n            db,\n            flow,\n            run_id=run_id,\n            result={"tool": "book_appointment", "output": result},\n        )\n        return None, None\n\n    completed, total = compound_progress(flow.entity_state)\n    total = max(total, completed + 1 + len(queue))\n    next_item = queue[0]\n    remaining = queue[1:]\n    catalog = build_clinic_catalog(db, workspace)\n    state = appointment_item_state(\n        next_item,\n        remaining=remaining,\n        total=total,\n        completed=completed + 1,\n        catalog=catalog,\n    )\n    if workspace.primary_branch_id is not None:\n        state["branch_id"] = str(workspace.primary_branch_id)\n    flow = transition_flow(\n        db,\n        flow,\n        actor_type="tool",\n        event_type="compound_item_completed",\n        run_id=run_id,\n        status="collecting_requirements",\n        capabilities=["availability_discovery", "appointment_creation"],\n        entity_state=state,\n        missing_information=list(next_item.missing_information),\n        pending_action={"last_completed": result},\n        option_snapshot={},\n    )\n    return flow, next_item\n\n\ndef _continue_compound_booking_flow(\n    *,\n    db: Session,\n    flow: ConversationFlowState,\n    item: CompoundRequestedItem,\n    base_decision: SemanticCapabilityDecision,\n    tool_context: AgentToolContext,\n    run_id: UUID,\n) -> tuple[str, str] | None:\n    decision = appointment_decision_from_item(base_decision, item)\n    catalog = build_clinic_catalog(db, tool_context.workspace)\n    decision = _with_implicit_primary_branch(\n        decision,\n        workspace=tool_context.workspace,\n        clinic_catalog=catalog,\n    )\n    policy = resolve_capability_policy(decision)\n    if policy.requires_human:\n        return _handoff_direct(\n            db=db,\n            tool_context=tool_context,\n            policy=policy,\n            reason=decision.reason,\n            run_id=run_id,\n            flow=flow,\n        )\n\n    service_name = str((flow.entity_state or {}).get(COMPOUND_CURRENT_SERVICE_KEY) or "الخدمة التالية")\n    service_id = str(decision.entity_hints.service_id or "").strip()\n    requested_date = str(decision.entity_hints.requested_date or "").strip()\n    if not service_id:\n        return (\n            f"باقي طلبك هو {service_name}، لكن محتاج تحدد الخدمة المقصودة بدقة قبل ما أكمل الحجز.",\n            "flow-interpreter:compound-needs-service",\n        )\n    if not requested_date:\n        return (\n            f"حجزت الجزء السابق من طلبك. بالنسبة لـ{service_name}، تحب الحجز يوم إيه؟",\n            "flow-interpreter:compound-needs-date",\n        )\n\n    arguments = {\n        "booking_date": requested_date,\n        "service_id": service_id,\n        "branch_id": str(decision.entity_hints.branch_id or ""),\n        "doctor_id": str(decision.entity_hints.doctor_id or ""),\n        "requested_start_time": str(decision.entity_hints.requested_start_time or ""),\n        "not_before_time": str(decision.entity_hints.not_before_time or ""),\n        "not_after_time": str(decision.entity_hints.not_after_time or ""),\n    }\n    if decision.entity_hints.laser_device_key:\n        arguments["laser_device_key"] = str(decision.entity_hints.laser_device_key)\n    result = _invoke_authorized_tool(\n        tool_context=tool_context,\n        policy=policy,\n        tool_name="get_booking_options",\n        arguments=arguments,\n    )\n    if not isinstance(result, dict):\n        return None\n    flow = _sync_flow_from_verified_prefetch(\n        db=db,\n        flow=flow,\n        prefetched_results={"get_booking_options": result},\n        run_id=run_id,\n    ) or flow\n\n    selection_index = _exact_action_selection_index(\n        decision=decision,\n        payload=result,\n        required_capability="appointment_creation",\n    )\n    if selection_index is not None:\n        return _structured_flow_write(\n            db=db,\n            flow=flow,\n            turn=_exact_action_flow_turn(decision, selection_index=selection_index),\n            policy=policy,\n            tool_context=tool_context,\n            run_id=run_id,\n        )\n\n    reply = _verified_booking_slots_reply(result, booking_authorized=True)\n    if reply is None:\n        reply = format_verified_tool_fallback("get_booking_options", result)\n    if reply is None:\n        reply = "محتاج اختيار إضافي عشان أكمل الحجز التالي بأمان."\n    return (\n        f"حجزت الجزء السابق من طلبك. وبالنسبة لـ{service_name}: {reply}",\n        "flow-interpreter:compound-next-booking",\n    )\n\n\n'''
    source = replace_once(source, helper_marker, helpers + helper_marker, "compound flow helpers")

    old_booking_finish = '''        complete_flow(\n            db,\n            flow,\n            run_id=run_id,\n            result={"tool": tool_name, "output": result},\n        )\n        return (\n            _package_booking_success_reply(appointment, package_result),\n            "flow-interpreter:verified-booking",\n        )\n'''
    new_booking_finish = '''        booking_reply = _package_booking_success_reply(appointment, package_result)\n        next_flow, next_item = _advance_compound_booking_flow(\n            db=db,\n            flow=flow,\n            workspace=tool_context.workspace,\n            run_id=run_id,\n            result=result,\n        )\n        if next_flow is not None and next_item is not None:\n            continuation = _continue_compound_booking_flow(\n                db=db,\n                flow=next_flow,\n                item=next_item,\n                base_decision=_flow_turn_as_capability_decision(turn),\n                tool_context=tool_context,\n                run_id=run_id,\n            )\n            if continuation is not None:\n                booking_reply = f"{booking_reply}\\n\\n{continuation[0]}"\n            return (booking_reply, "flow-interpreter:verified-compound-booking")\n        return (booking_reply, "flow-interpreter:verified-booking")\n'''
    source = replace_once(source, old_booking_finish, new_booking_finish, "compound booking completion")

    old_semantic = '''    semantic_decision = _package_intent_non_booking(unified_turn.as_semantic_decision())\n    semantic_decision = _with_implicit_primary_branch(\n        semantic_decision,\n        workspace=workspace,\n        clinic_catalog=clinic_catalog,\n    )\n    if flow is not None:\n'''
    new_semantic = '''    raw_semantic_decision = unified_turn.as_semantic_decision()\n    grounded_compound_items = ground_compound_requested_items(\n        list(raw_semantic_decision.entity_hints.requested_items),\n        clinic_catalog,\n    )\n    compound_active = has_compound_request(grounded_compound_items)\n    if compound_active:\n        semantic_decision = compound_union_decision(\n            raw_semantic_decision, grounded_compound_items\n        )\n        if flow is not None:\n            cancel_flow(\n                db,\n                flow,\n                run_id=run_id,\n                reason="superseded_by_compound_request",\n            )\n            flow = None\n    else:\n        semantic_decision = _package_intent_non_booking(raw_semantic_decision)\n    semantic_decision = _with_implicit_primary_branch(\n        semantic_decision,\n        workspace=workspace,\n        clinic_catalog=clinic_catalog,\n    )\n    compound_first_item: CompoundRequestedItem | None = None\n    compound_remaining_items: list[CompoundRequestedItem] = []\n    compound_total_appointments = 0\n    compound_prefix_reply = ""\n    compound_direct: tuple[str, str] | None = None\n    if flow is not None:\n'''
    source = replace_once(source, old_semantic, new_semantic, "compound semantic normalization")

    old_policy = '''    policy = resolve_capability_policy(\n        semantic_decision, inherited_capabilities=inherited_capabilities,\n    )\n    if flow is not None and str(semantic_decision.package_intent) == "purchase":\n'''
    new_policy = '''    policy = resolve_capability_policy(\n        semantic_decision, inherited_capabilities=inherited_capabilities,\n    )\n    if compound_active and not policy.requires_human:\n        requested_packages = package_items(grounded_compound_items)\n        requested_appointments = appointment_items(grounded_compound_items)\n        if requested_packages:\n            batch_result = purchase_compound_package_batch(\n                db,\n                workspace=workspace,\n                patient=patient,\n                conversation=conversation,\n                run_id=run_id,\n                items=requested_packages,\n            )\n            if not batch_result.ok:\n                compound_direct = (\n                    batch_result.reply,\n                    "deterministic:compound-package-validation",\n                )\n            else:\n                compound_prefix_reply = batch_result.reply\n        if compound_direct is None and requested_appointments:\n            compound_first_item = requested_appointments[0]\n            compound_remaining_items = requested_appointments[1:]\n            compound_total_appointments = len(requested_appointments)\n            semantic_decision = appointment_decision_from_item(\n                semantic_decision, compound_first_item\n            )\n            semantic_decision = _with_implicit_primary_branch(\n                semantic_decision,\n                workspace=workspace,\n                clinic_catalog=clinic_catalog,\n            )\n            policy = resolve_capability_policy(semantic_decision)\n        elif compound_direct is None:\n            compound_direct = (\n                compound_prefix_reply or "تم تنفيذ الطلب المركب الموثق.",\n                "deterministic:compound-package-purchase",\n            )\n    if flow is not None and str(semantic_decision.package_intent) == "purchase":\n'''
    source = replace_once(source, old_policy, new_policy, "compound package batch")

    old_start = '''    if flow is None:\n        flow_type = _flow_type_from_capabilities(set(policy.capabilities))\n        if flow_type is not None and not policy.requires_human:\n            flow = start_flow(\n                db,\n                workspace_id=workspace.id,\n                conversation_id=conversation.id,\n                patient_id=patient.id,\n                flow_type=flow_type,\n                capabilities=_persistent_flow_capabilities(flow_type, policy.capabilities),\n                entity_state={\n                    **semantic_decision.entity_hints.model_dump(mode="json", exclude_none=True),\n                    **(\n                        {"package_intent": str(semantic_decision.package_intent)}\n                        if str(semantic_decision.package_intent) in {"use_existing", "avoid_existing"}\n                        else {}\n                    ),\n                },\n                missing_information=semantic_decision.missing_information,\n                last_decision=_decision_payload(semantic_decision),\n                run_id=run_id,\n            )\n'''
    new_start = '''    if flow is None and compound_direct is None:\n        flow_type = _flow_type_from_capabilities(set(policy.capabilities))\n        if flow_type is not None and not policy.requires_human:\n            initial_entity_state = {\n                **semantic_decision.entity_hints.model_dump(mode="json", exclude_none=True),\n                **(\n                    {"package_intent": str(semantic_decision.package_intent)}\n                    if str(semantic_decision.package_intent) in {"use_existing", "avoid_existing"}\n                    else {}\n                ),\n            }\n            initial_entity_state.pop("requested_items", None)\n            if compound_first_item is not None:\n                initial_entity_state = _compound_initial_entity_state(\n                    decision=semantic_decision,\n                    first_item=compound_first_item,\n                    remaining=compound_remaining_items,\n                    total=compound_total_appointments,\n                    clinic_catalog=clinic_catalog,\n                )\n            flow = start_flow(\n                db,\n                workspace_id=workspace.id,\n                conversation_id=conversation.id,\n                patient_id=patient.id,\n                flow_type=flow_type,\n                capabilities=_persistent_flow_capabilities(flow_type, policy.capabilities),\n                entity_state=initial_entity_state,\n                missing_information=semantic_decision.missing_information,\n                last_decision=_decision_payload(semantic_decision),\n                run_id=run_id,\n            )\n'''
    source = replace_once(source, old_start, new_start, "compound initial flow state")

    source = replace_once(
        source,
        "    direct: tuple[str, str] | None = None\n    if policy.requires_human:\n",
        "    direct: tuple[str, str] | None = compound_direct\n    if policy.requires_human:\n",
        "compound direct response",
    )

    source = replace_once(
        source,
        "    reply = sanitize_customer_reply(reply)\n",
        "    if compound_prefix_reply and not reply.startswith(compound_prefix_reply):\n"
        "        reply = f\"{compound_prefix_reply}\\n\\n{reply}\"\n"
        "    reply = sanitize_customer_reply(reply)\n",
        "compound reply prefix",
    )

    path.write_text(source, encoding="utf-8")


def main() -> None:
    patch_interpreter()
    patch_agent_chat()


if __name__ == "__main__":
    main()
