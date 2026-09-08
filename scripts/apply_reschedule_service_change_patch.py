from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def replace(path: str, old: str, new: str) -> None:
    target = ROOT / path
    text = target.read_text(encoding="utf-8")
    if old not in text:
        raise RuntimeError(f"Expected patch fragment not found in {path}: {old[:120]!r}")
    target.write_text(text.replace(old, new, 1), encoding="utf-8")


# Canonical adapter contract: a reschedule may optionally target a different service.
replace(
    "backend/app/integrations/clinic/base.py",
    '''class RescheduleAppointmentRequest:\n    patient_id: str\n    appointment_id: str\n    start_at: datetime\n    operation_id: str\n    branch_id: str | None = None\n    doctor_id: str | None = None\n    reason: str = ""\n''',
    '''class RescheduleAppointmentRequest:\n    patient_id: str\n    appointment_id: str\n    start_at: datetime\n    operation_id: str\n    branch_id: str | None = None\n    doctor_id: str | None = None\n    service_id: str | None = None\n    reason: str = ""\n''',
)

# Domain operation: service changes are automatic only when no financial/package state exists.
replace(
    "backend/app/services/appointment_operations.py",
    "from app.models.automation_job import AutomationJob\n",
    "from app.models.automation_job import AutomationJob\nfrom app.models.payment_transaction import PaymentAllocation\n",
)
replace(
    "backend/app/services/appointment_operations.py",
    '''class AppointmentOperationForbidden(AppointmentOperationError):\n    pass\n\ndef appointment_allowed_actions(\n''',
    '''class AppointmentOperationForbidden(AppointmentOperationError):\n    pass\n\n\nclass AppointmentServiceChangeRequiresHuman(AppointmentOperationError):\n    pass\n\n\ndef service_change_requires_human(\n    *,\n    payment_status: str,\n    amount_paid_minor: int | None,\n    billing_context: str,\n    patient_package_id: UUID | None,\n    package_external_id: str | None,\n    has_payment_allocation: bool,\n) -> bool:\n    """Fail closed when changing service could alter money or package entitlement."""\n    return bool(\n        patient_package_id is not None\n        or billing_context == "package_prepaid"\n        or package_external_id\n        or payment_status not in {"unknown", "unpaid"}\n        or int(amount_paid_minor or 0) > 0\n        or has_payment_allocation\n    )\n\n\ndef appointment_allowed_actions(\n''',
)
replace(
    "backend/app/services/appointment_operations.py",
    '''    branch_id: UUID | None = None,\n    doctor_id: UUID | None = None,\n    patient_id: UUID | None = None,\n''',
    '''    branch_id: UUID | None = None,\n    doctor_id: UUID | None = None,\n    service_id: UUID | None = None,\n    patient_id: UUID | None = None,\n''',
)
replace(
    "backend/app/services/appointment_operations.py",
    '''    new_branch_id = branch_id or current.branch_id\n    new_doctor_id = doctor_id or current.doctor_id\n    try:\n        slot = find_exact_slot(\n            db=db,\n            workspace=workspace,\n            branch_id=new_branch_id,\n            service_id=current.service_id,\n''',
    '''    new_branch_id = branch_id or current.branch_id\n    new_doctor_id = doctor_id or current.doctor_id\n    new_service_id = service_id or current.service_id\n    service_changed = new_service_id != current.service_id\n    if service_changed:\n        has_payment_allocation = (\n            db.scalar(\n                select(PaymentAllocation.id)\n                .where(\n                    PaymentAllocation.workspace_id == workspace.id,\n                    PaymentAllocation.appointment_id == current.id,\n                )\n                .limit(1)\n            )\n            is not None\n        )\n        if service_change_requires_human(\n            payment_status=current.payment_status,\n            amount_paid_minor=current.amount_paid_minor,\n            billing_context=current.billing_context,\n            patient_package_id=current.patient_package_id,\n            package_external_id=current.package_external_id,\n            has_payment_allocation=has_payment_allocation,\n        ):\n            raise AppointmentServiceChangeRequiresHuman(\n                "Changing the service on this appointment needs staff review because "\n                "payment or package state is attached to the booking."\n            )\n\n    try:\n        slot = find_exact_slot(\n            db=db,\n            workspace=workspace,\n            branch_id=new_branch_id,\n            service_id=new_service_id,\n''',
)
replace(
    "backend/app/services/appointment_operations.py",
    "        service_id=current.service_id,\n        patient_package_id=current.patient_package_id,\n",
    "        service_id=new_service_id,\n        patient_package_id=current.patient_package_id,\n",
)
replace(
    "backend/app/services/appointment_operations.py",
    '''            "new_start_at": replacement.start_at.isoformat(),\n            "new_end_at": replacement.end_at.isoformat(),\n        },\n''',
    '''            "new_start_at": replacement.start_at.isoformat(),\n            "new_end_at": replacement.end_at.isoformat(),\n            "old_service_id": str(current.service_id),\n            "new_service_id": str(replacement.service_id),\n            "service_changed": service_changed,\n        },\n''',
)
replace(
    "backend/app/services/appointment_operations.py",
    '''            "old_start_at": old_start,\n            "new_start_at": replacement.start_at,\n        },\n''',
    '''            "old_start_at": old_start,\n            "new_start_at": replacement.start_at,\n            "old_service_id": current.service_id,\n            "new_service_id": replacement.service_id,\n            "service_changed": service_changed,\n        },\n''',
)

# Native adapter: pass the optional target service through and map financial sensitivity to human review.
replace(
    "backend/app/integrations/clinic/tia_database.py",
    '''    AppointmentOperationNotFound,\n    cancel_appointment_operation,\n''',
    '''    AppointmentOperationNotFound,\n    AppointmentServiceChangeRequiresHuman,\n    cancel_appointment_operation,\n''',
)
replace(
    "backend/app/integrations/clinic/tia_database.py",
    '''        new_branch_id = self._native_uuid(request.branch_id, "branch_id") if request.branch_id else None\n        new_doctor_id = self._native_uuid(request.doctor_id, "doctor_id") if request.doctor_id else None\n        idempotency_key = (\n            f"agent:{request.operation_id}:reschedule:{appointment_id}:"\n            f"{new_doctor_id or 'same'}:{requested_start.isoformat()}"\n        )[:128]\n''',
    '''        new_branch_id = self._native_uuid(request.branch_id, "branch_id") if request.branch_id else None\n        new_doctor_id = self._native_uuid(request.doctor_id, "doctor_id") if request.doctor_id else None\n        new_service_id = self._native_uuid(request.service_id, "service_id") if request.service_id else None\n        idempotency_key = (\n            f"agent:{request.operation_id}:reschedule:{appointment_id}:"\n            f"{new_doctor_id or 'same'}:{new_service_id or 'same'}:{requested_start.isoformat()}"\n        )[:128]\n''',
)
replace(
    "backend/app/integrations/clinic/tia_database.py",
    '''                branch_id=new_branch_id,\n                doctor_id=new_doctor_id,\n                changed_by_user_id=None,\n''',
    '''                branch_id=new_branch_id,\n                doctor_id=new_doctor_id,\n                service_id=new_service_id,\n                changed_by_user_id=None,\n''',
)
replace(
    "backend/app/integrations/clinic/tia_database.py",
    '''        except AppointmentOperationNotFound as exc:\n            raise ValueError("Appointment not found for this customer.") from exc\n        except AppointmentOperationError as exc:\n            raise BookingRuleError(str(exc)) from exc\n\n        return AppointmentMutationResult(\n            appointment=self._appointment_record(appointment_id=replacement.id),\n''',
    '''        except AppointmentServiceChangeRequiresHuman as exc:\n            raise ClinicActionRequiresHuman(\n                str(exc),\n                appointment_id=str(appointment_id),\n            ) from exc\n        except AppointmentOperationNotFound as exc:\n            raise ValueError("Appointment not found for this customer.") from exc\n        except AppointmentOperationError as exc:\n            raise BookingRuleError(str(exc)) from exc\n\n        return AppointmentMutationResult(\n            appointment=self._appointment_record(appointment_id=replacement.id),\n''',
)

# Agent discovery: explicit appointment identifies the old booking; service_id is the requested replacement service.
replace(
    "backend/app/agents/tools/clinic_tools.py",
    '''            if service_id:\n                appointments = [\n                    appointment\n                    for appointment in appointments\n                    if appointment.service_id == service_id\n                ]\n            elif service_search.strip():\n''',
    '''            if service_id and not appointment_id:\n                appointments = [\n                    appointment\n                    for appointment in appointments\n                    if appointment.service_id == service_id\n                ]\n            elif service_search.strip() and not appointment_id:\n''',
)
replace(
    "backend/app/agents/tools/clinic_tools.py",
    '''            current = appointments[0]\n            availability = _availability_payload(\n                ctx,\n                branch_id=current.branch_id,\n                service_id=current.service_id,\n''',
    '''            current = appointments[0]\n            target_service_id = service_id or current.service_id\n            availability = _availability_payload(\n                ctx,\n                branch_id=current.branch_id,\n                service_id=target_service_id,\n''',
)
replace(
    "backend/app/agents/tools/clinic_tools.py",
    '''        branch_id: str = "",\n        doctor_id: str = "",\n        reason: str = "",\n    ) -> str:\n''',
    '''        branch_id: str = "",\n        doctor_id: str = "",\n        service_id: str = "",\n        reason: str = "",\n    ) -> str:\n''',
)
replace(
    "backend/app/agents/tools/clinic_tools.py",
    '''            "branch_id": branch_id,\n            "doctor_id": doctor_id,\n            "reason": reason,\n''',
    '''            "branch_id": branch_id,\n            "doctor_id": doctor_id,\n            "service_id": service_id,\n            "reason": reason,\n''',
)
replace(
    "backend/app/agents/tools/clinic_tools.py",
    '''                    branch_id=branch_id or None,\n                    doctor_id=doctor_id or None,\n                    reason=reason,\n''',
    '''                    branch_id=branch_id or None,\n                    doctor_id=doctor_id or None,\n                    service_id=service_id or None,\n                    reason=reason,\n''',
)
replace(
    "backend/app/agents/tools/clinic_tools.py",
    '''            return _json(payload)\n        except (ValueError, BookingRuleError, IntegrityError) as exc:\n            ctx.db.rollback()\n            payload = {"ok": False, "error": str(exc)}\n            _record_action(\n                ctx,\n                tool_name="reschedule_appointment",\n''',
    '''            return _json(payload)\n        except ClinicActionRequiresHuman as exc:\n            ctx.db.rollback()\n            payload = {\n                "ok": False,\n                "requires_human": True,\n                "handoff_category": "payment",\n                "handoff_priority": "normal",\n                "error": str(exc),\n            }\n            _record_action(\n                ctx,\n                tool_name="reschedule_appointment",\n                action_type="appointment_reschedule",\n                status="blocked",\n                input_payload=inputs,\n                output_payload=payload,\n                appointment_id=_native_action_appointment_id(exc.appointment_id or appointment_id),\n                error_message=str(exc),\n            )\n            return _json(payload)\n        except (ValueError, BookingRuleError, IntegrityError) as exc:\n            ctx.db.rollback()\n            payload = {"ok": False, "error": str(exc)}\n            _record_action(\n                ctx,\n                tool_name="reschedule_appointment",\n''',
)

# Structured selection sends the verified service id selected in the slot.
replace(
    "backend/app/agents/semantic_actions.py",
    '''        "branch_id": str(slot.get("branch_id") or ""),\n        "doctor_id": str(slot.get("doctor_id") or ""),\n        "reason": "Customer selected a replacement slot in the active workflow.",\n''',
    '''        "branch_id": str(slot.get("branch_id") or ""),\n        "doctor_id": str(slot.get("doctor_id") or ""),\n        "service_id": str(slot.get("service_id") or ""),\n        "reason": "Customer selected a replacement slot in the active workflow.",\n''',
)
replace(
    "backend/app/agents/semantic_actions.py",
    '''    doctor = str(\n        appointment.get("doctor") or appointment.get("doctor_name") or ""\n    ).strip()\n    details: list[str] = []\n''',
    '''    doctor = str(\n        appointment.get("doctor") or appointment.get("doctor_name") or ""\n    ).strip()\n    service = str(\n        appointment.get("service") or appointment.get("service_name") or ""\n    ).strip()\n    details: list[str] = []\n    if service:\n        details.append(f"لـ{service}")\n''',
)

# Prefetch must retain the old appointment identity while allowing the target service to change.
replace(
    "backend/app/services/agent_chat.py",
    '''    appointment_id = text_value("appointment_id")\n    if not appointment_id and flow is not None and getattr(flow, "flow_type", None) == "appointment_reschedule":\n        appointment_reference = text_value("appointment_reference")\n''',
    '''    appointment_id = text_value("appointment_id")\n    if not appointment_id and flow is not None and getattr(flow, "flow_type", None) == "appointment_reschedule":\n        current_appointment = state.get("current_appointment")\n        if isinstance(current_appointment, dict) and current_appointment.get("appointment_id"):\n            appointment_id = str(current_appointment["appointment_id"])\n        elif isinstance(flow.option_snapshot, dict):\n            snapshot_current = flow.option_snapshot.get("current_appointment")\n            if isinstance(snapshot_current, dict) and snapshot_current.get("appointment_id"):\n                appointment_id = str(snapshot_current["appointment_id"])\n    if not appointment_id and flow is not None and getattr(flow, "flow_type", None) == "appointment_reschedule":\n        appointment_reference = text_value("appointment_reference")\n''',
)
replace(
    "backend/app/services/agent_chat.py",
    '''    result = _invoke_tool(\n        tool_context=tool_context,\n        tool_name=tool_name,\n        arguments=arguments,\n    )\n    if not result or result.get("ok") is not True:\n        return None\n\n    record_write_completed(\n''',
    '''    result = _invoke_tool(\n        tool_context=tool_context,\n        tool_name=tool_name,\n        arguments=arguments,\n    )\n    if result and result.get("requires_human") is True:\n        handoff_reason = str(result.get("error") or "Changing this booking needs staff review.")\n        handoff_result = _invoke_tool(\n            tool_context=tool_context,\n            tool_name="escalate_to_human",\n            arguments={\n                "reason": handoff_reason,\n                "category": str(result.get("handoff_category") or "payment"),\n                "priority": str(result.get("handoff_priority") or "normal"),\n            },\n        )\n        if handoff_result and handoff_result.get("ok") is True:\n            interrupt_flow(\n                db,\n                flow,\n                run_id=run_id,\n                reason="reschedule_service_change_requires_human",\n            )\n            return (\n                "تغيير الخدمة في الحجز ده محتاج مراجعة من فريق العيادة بسبب حالة الدفع أو الباكدج، فحوّلت المحادثة للفريق عشان يكملوا معاك.",\n                "flow-interpreter:reschedule-service-change-handoff",\n            )\n        return None\n    if not result or result.get("ok") is not True:\n        return None\n\n    record_write_completed(\n''',
)

# Focused regressions: contract propagation + deterministic financial guard.
test_path = ROOT / "backend/tests/test_reschedule_service_change_contract.py"
test_path.write_text(
    '''from pathlib import Path\n\nfrom app.services.appointment_operations import service_change_requires_human\n\n\ndef test_unpaid_standard_booking_can_change_service() -> None:\n    assert service_change_requires_human(\n        payment_status="unknown",\n        amount_paid_minor=None,\n        billing_context="standard",\n        patient_package_id=None,\n        package_external_id=None,\n        has_payment_allocation=False,\n    ) is False\n    assert service_change_requires_human(\n        payment_status="unpaid",\n        amount_paid_minor=0,\n        billing_context="standard",\n        patient_package_id=None,\n        package_external_id=None,\n        has_payment_allocation=False,\n    ) is False\n\n\ndef test_paid_or_package_booking_service_change_requires_human() -> None:\n    base = dict(\n        payment_status="unknown",\n        amount_paid_minor=None,\n        billing_context="standard",\n        patient_package_id=None,\n        package_external_id=None,\n        has_payment_allocation=False,\n    )\n    cases = [\n        {"payment_status": "paid"},\n        {"payment_status": "partial"},\n        {"amount_paid_minor": 100},\n        {"billing_context": "package_prepaid"},\n        {"package_external_id": "PKG-1"},\n        {"has_payment_allocation": True},\n    ]\n    for override in cases:\n        payload = {**base, **override}\n        assert service_change_requires_human(**payload) is True\n\n\ndef test_reschedule_service_id_flows_from_verified_slot_to_native_operation() -> None:\n    backend = Path(__file__).resolve().parent.parent\n    semantic = (backend / "app/agents/semantic_actions.py").read_text(encoding="utf-8")\n    tools = (backend / "app/agents/tools/clinic_tools.py").read_text(encoding="utf-8")\n    adapter = (backend / "app/integrations/clinic/tia_database.py").read_text(encoding="utf-8")\n    operations = (backend / "app/services/appointment_operations.py").read_text(encoding="utf-8")\n\n    assert '\"service_id\": str(slot.get(\"service_id\") or \"\")' in semantic\n    assert 'service_id: str = ""' in tools\n    assert 'service_id=service_id or None' in tools\n    assert 'service_id=new_service_id' in adapter\n    assert 'service_id=new_service_id' in operations\n    assert 'AppointmentServiceChangeRequiresHuman' in operations\n\n\ndef test_reschedule_discovery_keeps_current_appointment_separate_from_target_service() -> None:\n    backend = Path(__file__).resolve().parent.parent\n    tools = (backend / "app/agents/tools/clinic_tools.py").read_text(encoding="utf-8")\n    chat = (backend / "app/services/agent_chat.py").read_text(encoding="utf-8")\n\n    assert "if service_id and not appointment_id:" in tools\n    assert "target_service_id = service_id or current.service_id" in tools\n    assert "service_id=target_service_id" in tools\n    assert 'snapshot_current = flow.option_snapshot.get("current_appointment")' in chat\n\n\ndef test_financially_sensitive_service_change_escalates_instead_of_faking_failure() -> None:\n    backend = Path(__file__).resolve().parent.parent\n    tools = (backend / "app/agents/tools/clinic_tools.py").read_text(encoding="utf-8")\n    chat = (backend / "app/services/agent_chat.py").read_text(encoding="utf-8")\n\n    assert '\"requires_human\": True' in tools\n    assert 'tool_name="escalate_to_human"' in chat\n    assert "reschedule_service_change_requires_human" in chat\n''',
    encoding="utf-8",
)

print("Applied reschedule service-change patch successfully.")
