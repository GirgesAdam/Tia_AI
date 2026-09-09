from pathlib import Path


def replace_once(text: str, old: str, new: str, label: str) -> str:
    count = text.count(old)
    if count != 1:
        raise RuntimeError(f"{label}: expected one marker, found {count}")
    return text.replace(old, new, 1)


def patch_function(text: str, start_marker: str, end_marker: str, patches: list[tuple[str, str, str]]) -> str:
    start = text.index(start_marker)
    end = text.index(end_marker, start)
    block = text[start:end]
    for old, new, label in patches:
        block = replace_once(block, old, new, label)
    return text[:start] + block + text[end:]


# Canonical adapter contract.
path = Path("backend/app/integrations/clinic/base.py")
text = path.read_text(encoding="utf-8")
text = replace_once(
    text,
    '''class RescheduleAppointmentRequest:\n    patient_id: str\n    appointment_id: str\n    start_at: datetime\n    operation_id: str\n    branch_id: str | None = None\n    doctor_id: str | None = None\n    service_id: str | None = None\n    reason: str = ""\n''',
    '''class RescheduleAppointmentRequest:\n    patient_id: str\n    appointment_id: str\n    start_at: datetime\n    operation_id: str\n    branch_id: str | None = None\n    doctor_id: str | None = None\n    service_id: str | None = None\n    laser_device_key: str | None = None\n    reason: str = ""\n''',
    "canonical reschedule device",
)
path.write_text(text, encoding="utf-8")


# Agent orchestration: package selection and read-prefetch carry device identity.
path = Path("backend/app/services/agent_chat.py")
text = path.read_text(encoding="utf-8")
text = text.replace("    return None\ndef _package_booking_success_reply", "    return None\n\n\ndef _package_booking_success_reply", 1)
text = patch_function(
    text,
    "def _apply_single_matching_package_to_booking(",
    "\ndef _prefetch_read_tools(",
    [(
        '''    usable = list_patient_packages(\n        db,\n        workspace_id=workspace_id,\n        patient_id=patient_id,\n        service_id=appointment.service_id,\n        usable_only=True,\n        on_date=appointment.start_at.date(),\n    )\n    selected = _preferred_usable_package(list(usable))\n''',
        '''    usable = list_patient_packages(\n        db,\n        workspace_id=workspace_id,\n        patient_id=patient_id,\n        service_id=appointment.service_id,\n        usable_only=True,\n        on_date=appointment.start_at.date(),\n    )\n    usable = [\n        item\n        for item in usable\n        if item.laser_device_key is None\n        or item.laser_device_key == appointment.laser_device_key\n    ]\n    selected = _preferred_usable_package(list(usable))\n''',
        "agent package device filter",
    )],
)
text = patch_function(
    text,
    "def _prefetch_read_tools(",
    "\n_DIRECT_COMPOSITE_CAPABILITIES",
    [
        (
            '''    doctor_id = text_value("doctor_id")\n    appointment_id = text_value("appointment_id")\n''',
            '''    doctor_id = text_value("doctor_id")\n    laser_device_key = text_value("laser_device_key")\n    appointment_id = text_value("appointment_id")\n''',
            "prefetch device state",
        ),
        (
            '''                    "service_id": service_id,\n                    "branch_id": branch_id,\n                    "doctor_id": doctor_id,\n                }\n''',
            '''                    "service_id": service_id,\n                    "branch_id": branch_id,\n                    "doctor_id": doctor_id,\n                    "laser_device_key": laser_device_key,\n                }\n''',
            "prefetch booking device",
        ),
        (
            '''                "service_id": service_id,\n                "branch_id": branch_id,\n                "doctor_id": doctor_id,\n                "requested_start_time": requested_start_time,\n''',
            '''                "service_id": service_id,\n                "branch_id": branch_id,\n                "doctor_id": doctor_id,\n                "laser_device_key": laser_device_key,\n                "requested_start_time": requested_start_time,\n''',
            "prefetch next available device",
        ),
        (
            '''            reschedule_arguments["service_id"] = service_id\n            reschedule_arguments["doctor_id"] = doctor_id\n''',
            '''            reschedule_arguments["service_id"] = service_id\n            reschedule_arguments["doctor_id"] = doctor_id\n            reschedule_arguments["laser_device_key"] = laser_device_key\n''',
            "prefetch reschedule device",
        ),
    ],
)
path.write_text(text, encoding="utf-8")


# Agent tools: explicit device metadata and canonical device parameters.
path = Path("backend/app/agents/tools/clinic_tools.py")
text = path.read_text(encoding="utf-8")
text = replace_once(
    text,
    "from app.services.handoffs import create_handoff\nfrom app.services.patient_history import build_patient_history_context\n",
    "from app.services.handoffs import create_handoff\nfrom app.services.laser_booking_context import current_laser_device_key\nfrom app.services.patient_history import build_patient_history_context\n",
    "tool laser context import",
)
text = replace_once(
    text,
    '''        "package_external_id": getattr(appointment, "package_external_id", None),\n    }\n''',
    '''        "package_external_id": getattr(appointment, "package_external_id", None),\n        "laser_device_key": getattr(appointment, "laser_device_key", None),\n        "laser_device_name": getattr(appointment, "laser_device_name", None),\n    }\n''',
    "appointment read device metadata",
)
text = patch_function(
    text,
    "def _adapter_availability(",
    "\ndef _adapter_patient_appointments(",
    [
        (
            '''    doctor_id: str | None = None,\n    exclude_appointment_id: str | None = None,\n) -> AvailabilityResult:\n''',
            '''    doctor_id: str | None = None,\n    exclude_appointment_id: str | None = None,\n    laser_device_key: str | None = None,\n) -> AvailabilityResult:\n''',
            "adapter availability device parameter",
        ),
        (
            '''            doctor_id=doctor_id,\n            exclude_appointment_id=exclude_appointment_id,\n        )\n''',
            '''            doctor_id=doctor_id,\n            exclude_appointment_id=exclude_appointment_id,\n            laser_device_key=laser_device_key,\n        )\n''',
            "adapter availability device request",
        ),
    ],
)
text = patch_function(
    text,
    "def _availability_payload(",
    "\ndef _record_action(",
    [
        (
            '''    upper_bound: time | None,\n    exclude_appointment_id: str | UUID | None = None,\n) -> dict:\n''',
            '''    upper_bound: time | None,\n    exclude_appointment_id: str | UUID | None = None,\n    laser_device_key: str | None = None,\n) -> dict:\n''',
            "availability payload device parameter",
        ),
        (
            '''        exclude_appointment_id=(\n            str(exclude_appointment_id) if exclude_appointment_id is not None else None\n        ),\n    )\n''',
            '''        exclude_appointment_id=(\n            str(exclude_appointment_id) if exclude_appointment_id is not None else None\n        ),\n        laser_device_key=laser_device_key,\n    )\n''',
            "availability payload adapter device",
        ),
        (
            '''                "price": _money(slot.price_minor, slot.currency),\n            }\n''',
            '''                "price": _money(slot.price_minor, slot.currency),\n                "laser_device_key": getattr(slot, "laser_device_key", None),\n                "laser_device_name": getattr(slot, "laser_device_name", None),\n            }\n''',
            "availability payload slot device",
        ),
    ],
)
text = patch_function(
    text,
    "    @tool\n    def get_booking_options(",
    "\n    @tool\n    def get_reschedule_options(",
    [
        (
            '''        branch_id: str = "",\n        doctor_id: str = "",\n        requested_start_time: str = "",\n''',
            '''        branch_id: str = "",\n        doctor_id: str = "",\n        laser_device_key: str = "",\n        requested_start_time: str = "",\n''',
            "booking tool device parameter",
        ),
        (
            '''            "branch_id": branch_id,\n            "doctor_id": doctor_id,\n            "branch_search": branch_search,\n''',
            '''            "branch_id": branch_id,\n            "doctor_id": doctor_id,\n            "laser_device_key": laser_device_key or None,\n            "branch_search": branch_search,\n''',
            "booking tool input device",
        ),
        (
            '''                requested_start=requested_start,\n                lower_bound=lower_bound,\n                upper_bound=upper_bound,\n            )\n''',
            '''                requested_start=requested_start,\n                lower_bound=lower_bound,\n                upper_bound=upper_bound,\n                laser_device_key=laser_device_key or None,\n            )\n''',
            "booking availability device",
        ),
    ],
)
text = patch_function(
    text,
    "    @tool\n    def get_reschedule_options(",
    "\n    @tool\n    def get_available_slots(",
    [
        (
            '''        service_id: str = "",\n        doctor_id: str = "",\n        service_search: str = "",\n''',
            '''        service_id: str = "",\n        doctor_id: str = "",\n        laser_device_key: str = "",\n        service_search: str = "",\n''',
            "reschedule tool device parameter",
        ),
        (
            '''            "service_id": service_id,\n            "doctor_id": doctor_id or None,\n            "service_search": service_search,\n''',
            '''            "service_id": service_id,\n            "doctor_id": doctor_id or None,\n            "laser_device_key": laser_device_key or None,\n            "service_search": service_search,\n''',
            "reschedule tool input device",
        ),
        (
            '''                upper_bound=upper_bound,\n                exclude_appointment_id=current.appointment_id,\n            )\n''',
            '''                upper_bound=upper_bound,\n                exclude_appointment_id=current.appointment_id,\n                laser_device_key=(laser_device_key or current.laser_device_key),\n            )\n''',
            "reschedule availability device",
        ),
    ],
)
text = patch_function(
    text,
    "    @tool\n    def get_available_slots(",
    "\n    @tool\n    def get_customer_appointments(",
    [(
        '''                        "price": _money(slot.price_minor, slot.currency),\n                    }\n''',
        '''                        "price": _money(slot.price_minor, slot.currency),\n                        "laser_device_key": getattr(slot, "laser_device_key", None),\n                        "laser_device_name": getattr(slot, "laser_device_name", None),\n                    }\n''',
        "legacy available slot device",
    )],
)
text = patch_function(
    text,
    "    @tool\n    def book_appointment(",
    "\n    @tool\n    def confirm_appointment(",
    [(
        '''                    customer_note=customer_note,\n                    patient_package_id=patient_package_id.strip() or None,\n                )\n''',
        '''                    customer_note=customer_note,\n                    patient_package_id=patient_package_id.strip() or None,\n                    laser_device_key=current_laser_device_key(),\n                )\n''',
        "booking write device",
    )],
)
text = patch_function(
    text,
    "    @tool\n    def reschedule_appointment(",
    "\n    @tool\n    def create_follow_up_task(",
    [(
        '''                    doctor_id=doctor_id or None,\n                    service_id=service_id or None,\n                    reason=reason,\n                )\n''',
        '''                    doctor_id=doctor_id or None,\n                    service_id=service_id or None,\n                    laser_device_key=current_laser_device_key(),\n                    reason=reason,\n                )\n''',
        "reschedule write device",
    )],
)
path.write_text(text, encoding="utf-8")


# Native Tia adapter: propagate device identity through reads/writes/package validation.
path = Path("backend/app/integrations/clinic/tia_database.py")
text = path.read_text(encoding="utf-8")
text = patch_function(
    text,
    "    def get_availability(",
    "\n    def _patient_appointment(",
    [
        (
            '''            exclude_appointment_id=exclude_appointment_id,\n            now=request.now,\n            preloaded_branch=branch,\n''',
            '''            exclude_appointment_id=exclude_appointment_id,\n            now=request.now,\n            laser_device_key=request.laser_device_key,\n            preloaded_branch=branch,\n''',
            "native availability device",
        ),
        (
            '''                price_minor=slot.price_minor,\n                currency=slot.currency,\n            )\n''',
            '''                price_minor=slot.price_minor,\n                currency=slot.currency,\n                laser_device_key=slot.laser_device_key,\n                laser_device_name=slot.laser_device_name,\n            )\n''',
            "native availability slot device",
        ),
    ],
)
text = patch_function(
    text,
    "    def _appointment_record(",
    "\n    def _add_status_history(",
    [(
        '''            patient_package_id=(\n                str(appointment.patient_package_id)\n                if getattr(appointment, "patient_package_id", None)\n                else None\n            ),\n        )\n''',
        '''            patient_package_id=(\n                str(appointment.patient_package_id)\n                if getattr(appointment, "patient_package_id", None)\n                else None\n            ),\n            laser_device_key=getattr(appointment, "laser_device_key", None),\n            laser_device_name=getattr(appointment, "laser_device_name", None),\n        )\n''',
        "native appointment record device",
    )],
)
text = patch_function(
    text,
    "    def create_appointment(",
    "\n    def confirm_appointment(",
    [
        (
            '''            doctor_id=doctor_id,\n            requested_start_at=requested_start,\n        )\n''',
            '''            doctor_id=doctor_id,\n            requested_start_at=requested_start,\n            laser_device_key=request.laser_device_key,\n        )\n''',
            "native create slot device",
        ),
        (
            '''                    service_id=service_id,\n                    appointment_start_at=slot.start_at,\n                )\n''',
            '''                    service_id=service_id,\n                    appointment_start_at=slot.start_at,\n                    laser_device_key=slot.laser_device_key,\n                )\n''',
            "native package validation device",
        ),
        (
            '''            price_minor=slot.price_minor,\n            currency=slot.currency,\n            customer_note=request.customer_note.strip() or None,\n''',
            '''            price_minor=slot.price_minor,\n            currency=slot.currency,\n            laser_device_key=slot.laser_device_key,\n            laser_device_name=slot.laser_device_name,\n            customer_note=request.customer_note.strip() or None,\n''',
            "native appointment persistence device",
        ),
    ],
)
text = patch_function(
    text,
    "    def reschedule_appointment(",
    "\n    def get_patient(",
    [
        (
            '''            f"{new_doctor_id or 'same'}:{new_service_id or 'same'}:{requested_start.isoformat()}"\n''',
            '''            f"{new_doctor_id or 'same'}:{new_service_id or 'same'}:"\n            f"{request.laser_device_key or 'same'}:{requested_start.isoformat()}"\n''',
            "native reschedule idempotency device",
        ),
        (
            '''                doctor_id=new_doctor_id,\n                service_id=new_service_id,\n                changed_by_user_id=None,\n''',
            '''                doctor_id=new_doctor_id,\n                service_id=new_service_id,\n                laser_device_key=request.laser_device_key,\n                changed_by_user_id=None,\n''',
            "native reschedule operation device",
        ),
    ],
)
path.write_text(text, encoding="utf-8")


# Core reschedule business rule: device changes use the same financial handoff boundary as service changes.
path = Path("backend/app/services/appointment_operations.py")
text = path.read_text(encoding="utf-8")
text = replace_once(
    text,
    "from app.models.payment_transaction import PaymentAllocation\nfrom app.models.workspace import Workspace\n",
    "from app.models.payment_transaction import PaymentAllocation\nfrom app.models.service import Service\nfrom app.models.workspace import Workspace\n",
    "reschedule service import",
)
text = patch_function(
    text,
    "def reschedule_appointment_operation(",
    "\ndef update_operational_status_operation(",
    [
        (
            '''    doctor_id: UUID | None = None,\n    service_id: UUID | None = None,\n    patient_id: UUID | None = None,\n''',
            '''    doctor_id: UUID | None = None,\n    service_id: UUID | None = None,\n    laser_device_key: str | None = None,\n    patient_id: UUID | None = None,\n''',
            "reschedule operation device parameter",
        ),
        (
            '''    new_branch_id = branch_id or current.branch_id\n    new_doctor_id = doctor_id or current.doctor_id\n    new_service_id = service_id or current.service_id\n    service_changed = new_service_id != current.service_id\n    if service_changed:\n        has_payment_allocation = (\n            db.scalar(\n                select(PaymentAllocation.id)\n                .where(\n                    PaymentAllocation.workspace_id == workspace.id,\n                    PaymentAllocation.appointment_id == current.id,\n                )\n                .limit(1)\n            )\n            is not None\n        )\n        if service_change_requires_human(\n            payment_status=current.payment_status,\n            amount_paid_minor=current.amount_paid_minor,\n            billing_context=current.billing_context,\n            patient_package_id=current.patient_package_id,\n            package_external_id=current.package_external_id,\n            has_payment_allocation=has_payment_allocation,\n        ):\n            raise AppointmentServiceChangeRequiresHuman(\n                "Changing the service on this appointment needs staff review because "\n                "payment or package state is attached to the booking."\n            )\n\n    try:\n        slot = find_exact_slot(\n            db=db,\n            workspace=workspace,\n            branch_id=new_branch_id,\n            service_id=new_service_id,\n            doctor_id=new_doctor_id,\n            requested_start_at=requested_start_at,\n            exclude_appointment_id=current.id,\n        )\n''',
            '''    new_branch_id = branch_id or current.branch_id\n    new_doctor_id = doctor_id or current.doctor_id\n    new_service_id = service_id or current.service_id\n    target_service = db.scalar(\n        select(Service).where(\n            Service.workspace_id == workspace.id,\n            Service.id == new_service_id,\n            Service.is_active.is_(True),\n        )\n    )\n    if target_service is None:\n        raise AppointmentOperationError("Replacement service not found or inactive.")\n    new_laser_device_key = (\n        laser_device_key or current.laser_device_key\n        if bool(getattr(target_service, "requires_laser_device", False))\n        else None\n    )\n    service_changed = new_service_id != current.service_id\n    device_changed = new_laser_device_key != current.laser_device_key\n    if service_changed or device_changed:\n        has_payment_allocation = (\n            db.scalar(\n                select(PaymentAllocation.id)\n                .where(\n                    PaymentAllocation.workspace_id == workspace.id,\n                    PaymentAllocation.appointment_id == current.id,\n                )\n                .limit(1)\n            )\n            is not None\n        )\n        if service_change_requires_human(\n            payment_status=current.payment_status,\n            amount_paid_minor=current.amount_paid_minor,\n            billing_context=current.billing_context,\n            patient_package_id=current.patient_package_id,\n            package_external_id=current.package_external_id,\n            has_payment_allocation=has_payment_allocation,\n        ):\n            raise AppointmentServiceChangeRequiresHuman(\n                "Changing the service or laser device on this appointment needs staff review because "\n                "payment or package state is attached to the booking."\n            )\n\n    try:\n        slot = find_exact_slot(\n            db=db,\n            workspace=workspace,\n            branch_id=new_branch_id,\n            service_id=new_service_id,\n            doctor_id=new_doctor_id,\n            requested_start_at=requested_start_at,\n            exclude_appointment_id=current.id,\n            laser_device_key=new_laser_device_key,\n        )\n''',
            "reschedule service/device business rule",
        ),
        (
            '''        price_minor=slot.price_minor,\n        currency=slot.currency,\n        payment_status=current.payment_status,\n''',
            '''        price_minor=slot.price_minor,\n        currency=slot.currency,\n        laser_device_key=slot.laser_device_key,\n        laser_device_name=slot.laser_device_name,\n        payment_status=current.payment_status,\n''',
            "replacement device persistence",
        ),
        (
            '''            "old_service_id": str(current.service_id),\n            "new_service_id": str(replacement.service_id),\n            "service_changed": service_changed,\n        },\n    )\n    add_appointment_history(\n''',
            '''            "old_service_id": str(current.service_id),\n            "new_service_id": str(replacement.service_id),\n            "service_changed": service_changed,\n            "old_laser_device_key": current.laser_device_key,\n            "new_laser_device_key": replacement.laser_device_key,\n            "laser_device_changed": device_changed,\n        },\n    )\n    add_appointment_history(\n''',
            "reschedule history device metadata",
        ),
        (
            '''            "old_service_id": current.service_id,\n            "new_service_id": replacement.service_id,\n            "service_changed": service_changed,\n        },\n    )\n    db.flush()\n    return replacement, current\n''',
            '''            "old_service_id": current.service_id,\n            "new_service_id": replacement.service_id,\n            "service_changed": service_changed,\n            "old_laser_device_key": current.laser_device_key,\n            "new_laser_device_key": replacement.laser_device_key,\n            "laser_device_changed": device_changed,\n        },\n    )\n    db.flush()\n    return replacement, current\n''',
            "reschedule activity device metadata",
        ),
    ],
)
path.write_text(text, encoding="utf-8")


# Laser adapter forwards the selected device into the canonical reschedule request.
path = Path("backend/app/integrations/clinic/tia_database_laser.py")
text = path.read_text(encoding="utf-8")
text = patch_function(
    text,
    "    def reschedule_appointment(",
    "\n",
    [],
) if False else text
text = replace_once(
    text,
    '''        result = super().reschedule_appointment(request)\n''',
    '''        effective_request = replace(\n            request,\n            laser_device_key=(device_price.device_key if device_price is not None else None),\n        )\n        result = super().reschedule_appointment(effective_request)\n''',
    "laser adapter reschedule propagation",
)
path.write_text(text, encoding="utf-8")


# Package display name and informational financial snapshots.
path = Path("backend/app/services/package_offers.py")
text = path.read_text(encoding="utf-8")
text = replace_once(
    text,
    '''    if device_price is None or device_price.price_minor is None:\n        raise PackageOfferError("Standalone device price is unavailable for this package offer.")\n    name = f"{offer.sessions_count} sessions · {offer.device_name}"\n''',
    '''    if device_price is None or device_price.price_minor is None:\n        raise PackageOfferError("Standalone device price is unavailable for this package offer.")\n    service = db.scalar(\n        select(Service).where(\n            Service.workspace_id == workspace_id,\n            Service.id == offer.service_id,\n            Service.is_active.is_(True),\n        )\n    )\n    if service is None:\n        raise PackageOfferNotFound("Package service not found or inactive.")\n    name = f"{service.name} · {offer.device_name} · {offer.sessions_count} sessions"\n''',
    "package snapshot display name",
)
path.write_text(text, encoding="utf-8")

path = Path("backend/app/schemas/patient_packages.py")
text = path.read_text(encoding="utf-8")
text = replace_once(
    text,
    '''    sale_price_minor: int\n    standalone_session_price_minor_at_purchase: int | None = None\n''',
    '''    sale_price_minor: int\n    amount_paid_minor: int = 0\n    amount_refunded_minor: int = 0\n    balance_due_minor: int = 0\n    standalone_session_price_minor_at_purchase: int | None = None\n''',
    "package financial read schema",
)
path.write_text(text, encoding="utf-8")

path = Path("backend/app/services/patient_packages.py")
text = path.read_text(encoding="utf-8")
text = replace_once(
    text,
    '''    if effective == "active" and remaining == 0:\n        effective = "exhausted"\n    return PatientPackageRead(\n''',
    '''    if effective == "active" and remaining == 0:\n        effective = "exhausted"\n    payments, refunds = _package_financial_rows(\n        db, workspace_id=package.workspace_id, package=package, for_update=False\n    )\n    amount_paid_minor = sum(int(row.amount_minor) for row in payments)\n    amount_refunded_minor = sum(int(row.amount_minor) for row in refunds)\n    balance_due_minor = (\n        max(int(package.sale_price_minor) - amount_paid_minor, 0)\n        if effective == "active"\n        else 0\n    )\n    return PatientPackageRead(\n''',
    "package financial read calculation",
)
text = replace_once(
    text,
    '''        sale_price_minor=package.sale_price_minor,\n        standalone_session_price_minor_at_purchase=(\n''',
    '''        sale_price_minor=package.sale_price_minor,\n        amount_paid_minor=amount_paid_minor,\n        amount_refunded_minor=amount_refunded_minor,\n        balance_due_minor=balance_due_minor,\n        standalone_session_price_minor_at_purchase=(\n''',
    "package financial read payload",
)
path.write_text(text, encoding="utf-8")
