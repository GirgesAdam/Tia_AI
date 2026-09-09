from pathlib import Path


def replace_once(text: str, old: str, new: str, label: str) -> str:
    count = text.count(old)
    if count != 1:
        raise RuntimeError(f"{label}: expected one marker, found {count}")
    return text.replace(old, new, 1)


# Canonical adapter contract: reschedules carry the chosen laser device explicitly.
path = Path("backend/app/integrations/clinic/base.py")
text = path.read_text(encoding="utf-8")
text = replace_once(
    text,
    '''    doctor_id: str | None = None\n    service_id: str | None = None\n    reason: str = ""\n''',
    '''    doctor_id: str | None = None\n    service_id: str | None = None\n    laser_device_key: str | None = None\n    reason: str = ""\n''',
    "reschedule canonical laser device",
)
path.write_text(text, encoding="utf-8")


# Agent orchestration: choose only package entitlement compatible with the booked device.
path = Path("backend/app/services/agent_chat.py")
text = path.read_text(encoding="utf-8")
text = text.replace("    return None\ndef _package_booking_success_reply", "    return None\n\n\ndef _package_booking_success_reply", 1)
apply_start = text.index("def _apply_single_matching_package_to_booking(")
apply_end = text.index("\ndef _prefetch_read_tools(", apply_start)
block = text[apply_start:apply_end]
block = replace_once(
    block,
    '''    usable = list_patient_packages(\n        db,\n        workspace_id=workspace_id,\n        patient_id=patient_id,\n        service_id=appointment.service_id,\n        usable_only=True,\n        on_date=appointment.start_at.date(),\n    )\n    selected = _preferred_usable_package(list(usable))\n''',
    '''    usable = list_patient_packages(\n        db,\n        workspace_id=workspace_id,\n        patient_id=patient_id,\n        service_id=appointment.service_id,\n        usable_only=True,\n        on_date=appointment.start_at.date(),\n    )\n    usable = [\n        item\n        for item in usable\n        if item.laser_device_key is None\n        or item.laser_device_key == appointment.laser_device_key\n    ]\n    selected = _preferred_usable_package(list(usable))\n''',
    "agent device-compatible package selection",
)
text = text[:apply_start] + block + text[apply_end:]

# Prefetch carries the structured device selected by the semantic interpreter.
text = replace_once(
    text,
    '''    doctor_id = text_value("doctor_id")\n    appointment_id = text_value("appointment_id")\n''',
    '''    doctor_id = text_value("doctor_id")\n    laser_device_key = text_value("laser_device_key")\n    appointment_id = text_value("appointment_id")\n''',
    "agent prefetch device state",
)
text = replace_once(
    text,
    '''                    "doctor_id": doctor_id,\n                }\n''',
    '''                    "doctor_id": doctor_id,\n                    "laser_device_key": laser_device_key,\n                }\n''',
    "agent booking prefetch device",
)
text = replace_once(
    text,
    '''                "doctor_id": doctor_id,\n                "requested_start_time": requested_start_time,\n''',
    '''                "doctor_id": doctor_id,\n                "laser_device_key": laser_device_key,\n                "requested_start_time": requested_start_time,\n''',
    "agent next-available device",
)
text = replace_once(
    text,
    '''            reschedule_arguments["service_id"] = service_id\n            reschedule_arguments["doctor_id"] = doctor_id\n''',
    '''            reschedule_arguments["service_id"] = service_id\n            reschedule_arguments["doctor_id"] = doctor_id\n            reschedule_arguments["laser_device_key"] = laser_device_key\n''',
    "agent reschedule prefetch device",
)
path.write_text(text, encoding="utf-8")


# Agent tools: carry laser device metadata in verified reads and writes.
path = Path("backend/app/agents/tools/clinic_tools.py")
text = path.read_text(encoding="utf-8")
text = replace_once(
    text,
    '''        "package_external_id": getattr(appointment, "package_external_id", None),\n    }\n''',
    '''        "package_external_id": getattr(appointment, "package_external_id", None),\n        "laser_device_key": getattr(appointment, "laser_device_key", None),\n        "laser_device_name": getattr(appointment, "laser_device_name", None),\n    }\n''',
    "canonical appointment device metadata",
)
text = replace_once(
    text,
    '''    doctor_id: str | None = None,\n    exclude_appointment_id: str | None = None,\n) -> AvailabilityResult:\n''',
    '''    doctor_id: str | None = None,\n    exclude_appointment_id: str | None = None,\n    laser_device_key: str | None = None,\n) -> AvailabilityResult:\n''',
    "adapter availability helper device parameter",
)
text = replace_once(
    text,
    '''            doctor_id=doctor_id,\n            exclude_appointment_id=exclude_appointment_id,\n        )\n''',
    '''            doctor_id=doctor_id,\n            exclude_appointment_id=exclude_appointment_id,\n            laser_device_key=laser_device_key,\n        )\n''',
    "adapter availability request device",
)
text = replace_once(
    text,
    '''    upper_bound: time | None,\n    exclude_appointment_id: str | UUID | None = None,\n) -> dict:\n''',
    '''    upper_bound: time | None,\n    exclude_appointment_id: str | UUID | None = None,\n    laser_device_key: str | None = None,\n) -> dict:\n''',
    "availability payload device parameter",
)
text = replace_once(
    text,
    '''        exclude_appointment_id=(\n            str(exclude_appointment_id) if exclude_appointment_id is not None else None\n        ),\n    )\n''',
    '''        exclude_appointment_id=(\n            str(exclude_appointment_id) if exclude_appointment_id is not None else None\n        ),\n        laser_device_key=laser_device_key,\n    )\n''',
    "availability payload adapter device",
)
# Both verified slot renderers carry device identity.
slot_price = '                "price": _money(slot.price_minor, slot.currency),\n'
if text.count(slot_price) != 2:
    raise RuntimeError(f"slot device metadata: expected two markers, found {text.count(slot_price)}")
text = text.replace(
    slot_price,
    slot_price
    + '                "laser_device_key": getattr(slot, "laser_device_key", None),\n'
    + '                "laser_device_name": getattr(slot, "laser_device_name", None),\n',
)

# Booking discovery accepts a grounded device key and constrains availability to it.
text = replace_once(
    text,
    '''        doctor_id: str = "",\n        requested_start_time: str = "",\n''',
    '''        doctor_id: str = "",\n        laser_device_key: str = "",\n        requested_start_time: str = "",\n''',
    "booking tool device parameter",
)
text = replace_once(
    text,
    '''            "doctor_id": doctor_id,\n            "branch_search": branch_search,\n''',
    '''            "doctor_id": doctor_id,\n            "laser_device_key": laser_device_key or None,\n            "branch_search": branch_search,\n''',
    "booking tool input device",
)
text = replace_once(
    text,
    '''                requested_start=requested_start,\n                lower_bound=lower_bound,\n                upper_bound=upper_bound,\n            )\n''',
    '''                requested_start=requested_start,\n                lower_bound=lower_bound,\n                upper_bound=upper_bound,\n                laser_device_key=laser_device_key or None,\n            )\n''',
    "booking availability device",
)

# Reschedule discovery carries the current/new device explicitly.
text = replace_once(
    text,
    '''        service_id: str = "",\n        doctor_id: str = "",\n        service_search: str = "",\n''',
    '''        service_id: str = "",\n        doctor_id: str = "",\n        laser_device_key: str = "",\n        service_search: str = "",\n''',
    "reschedule discovery device parameter",
)
text = replace_once(
    text,
    '''            "doctor_id": doctor_id or None,\n            "service_search": service_search,\n''',
    '''            "doctor_id": doctor_id or None,\n            "laser_device_key": laser_device_key or None,\n            "service_search": service_search,\n''',
    "reschedule discovery input device",
)
text = replace_once(
    text,
    '''                upper_bound=upper_bound,\n                exclude_appointment_id=current.appointment_id,\n            )\n''',
    '''                upper_bound=upper_bound,\n                exclude_appointment_id=current.appointment_id,\n                laser_device_key=(laser_device_key or current.laser_device_key),\n            )\n''',
    "reschedule availability device",
)

# Actual writes also carry the selected device through the canonical adapter request.
text = replace_once(
    text,
    '''                    customer_note=customer_note,\n                    patient_package_id=patient_package_id.strip() or None,\n                )\n''',
    '''                    customer_note=customer_note,\n                    patient_package_id=patient_package_id.strip() or None,\n                    laser_device_key=current_laser_device_key(),\n                )\n''',
    "booking write device",
)
text = replace_once(
    text,
    "from app.services.handoffs import create_handoff\nfrom app.services.patient_history import build_patient_history_context\n",
    "from app.services.handoffs import create_handoff\nfrom app.services.laser_booking_context import current_laser_device_key\nfrom app.services.patient_history import build_patient_history_context\n",
    "tool laser context import",
)
text = replace_once(
    text,
    '''                    service_id=service_id or None,\n                    reason=reason,\n                )\n''',
    '''                    service_id=service_id or None,\n                    laser_device_key=current_laser_device_key(),\n                    reason=reason,\n                )\n''',
    "reschedule write device",
)
path.write_text(text, encoding="utf-8")


# Native DB adapter: pass device identity into booking engine/package validation.
path = Path("backend/app/integrations/clinic/tia_database.py")
text = path.read_text(encoding="utf-8")
text = replace_once(
    text,
    '''            exclude_appointment_id=exclude_appointment_id,\n            now=request.now,\n            preloaded_branch=branch,\n''',
    '''            exclude_appointment_id=exclude_appointment_id,\n            now=request.now,\n            laser_device_key=request.laser_device_key,\n            preloaded_branch=branch,\n''',
    "adapter availability device",
)
text = replace_once(
    text,
    '''                price_minor=slot.price_minor,\n                currency=slot.currency,\n            )\n''',
    '''                price_minor=slot.price_minor,\n                currency=slot.currency,\n                laser_device_key=slot.laser_device_key,\n                laser_device_name=slot.laser_device_name,\n            )\n''',
    "adapter availability slot device",
)
text = replace_once(
    text,
    '''                else None\n            ),\n        )\n\n    def _add_status_history''',
    '''                else None\n            ),\n            laser_device_key=getattr(appointment, "laser_device_key", None),\n            laser_device_name=getattr(appointment, "laser_device_name", None),\n        )\n\n    def _add_status_history''',
    "adapter appointment record device",
)
create_start = text.index("    def create_appointment(")
create_end = text.index("\n    def confirm_appointment(", create_start)
block = text[create_start:create_end]
block = replace_once(
    block,
    '''            doctor_id=doctor_id,\n            requested_start_at=requested_start,\n        )\n''',
    '''            doctor_id=doctor_id,\n            requested_start_at=requested_start,\n            laser_device_key=request.laser_device_key,\n        )\n''',
    "adapter create exact slot device",
)
block = replace_once(
    block,
    '''                    service_id=service_id,\n                    appointment_start_at=slot.start_at,\n                )\n''',
    '''                    service_id=service_id,\n                    appointment_start_at=slot.start_at,\n                    laser_device_key=slot.laser_device_key,\n                )\n''',
    "adapter package validation device",
)
block = replace_once(
    block,
    '''            price_minor=slot.price_minor,\n            currency=slot.currency,\n            customer_note=request.customer_note.strip() or None,\n''',
    '''            price_minor=slot.price_minor,\n            currency=slot.currency,\n            laser_device_key=slot.laser_device_key,\n            laser_device_name=slot.laser_device_name,\n            customer_note=request.customer_note.strip() or None,\n''',
    "adapter created appointment device",
)
text = text[:create_start] + block + text[create_end:]
reschedule_start = text.index("    def reschedule_appointment(")
reschedule_end = text.index("\n    def get_patient(", reschedule_start)
block = text[reschedule_start:reschedule_end]
block = replace_once(
    block,
    '''            f"{new_doctor_id or 'same'}:{new_service_id or 'same'}:{requested_start.isoformat()}"\n''',
    '''            f"{new_doctor_id or 'same'}:{new_service_id or 'same'}:"\n            f"{request.laser_device_key or 'same'}:{requested_start.isoformat()}"\n''',
    "adapter reschedule idempotency device",
)
block = replace_once(
    block,
    '''                doctor_id=new_doctor_id,\n                service_id=new_service_id,\n                changed_by_user_id=None,\n''',
    '''                doctor_id=new_doctor_id,\n                service_id=new_service_id,\n                laser_device_key=request.laser_device_key,\n                changed_by_user_id=None,\n''',
    "adapter reschedule operation device",
)
text = text[:reschedule_start] + block + text[reschedule_end:]
path.write_text(text, encoding="utf-8")


# Appointment operation: changing service OR device on financially-sensitive bookings needs staff review.
path = Path("backend/app/services/appointment_operations.py")
text = path.read_text(encoding="utf-8")
text = replace_once(
    text,
    "from app.models.payment_transaction import PaymentAllocation\nfrom app.models.workspace import Workspace\n",
    "from app.models.payment_transaction import PaymentAllocation\nfrom app.models.service import Service\nfrom app.models.workspace import Workspace\n",
    "appointment operation service import",
)
text = replace_once(
    text,
    '''    doctor_id: UUID | None = None,\n    service_id: UUID | None = None,\n    patient_id: UUID | None = None,\n''',
    '''    doctor_id: UUID | None = None,\n    service_id: UUID | None = None,\n    laser_device_key: str | None = None,\n    patient_id: UUID | None = None,\n''',
    "appointment operation device parameter",
)
old_logic = '''    new_branch_id = branch_id or current.branch_id\n    new_doctor_id = doctor_id or current.doctor_id\n    new_service_id = service_id or current.service_id\n    service_changed = new_service_id != current.service_id\n    if service_changed:\n        has_payment_allocation = (\n            db.scalar(\n                select(PaymentAllocation.id)\n                .where(\n                    PaymentAllocation.workspace_id == workspace.id,\n                    PaymentAllocation.appointment_id == current.id,\n                )\n                .limit(1)\n            )\n            is not None\n        )\n        if service_change_requires_human(\n            payment_status=current.payment_status,\n            amount_paid_minor=current.amount_paid_minor,\n            billing_context=current.billing_context,\n            patient_package_id=current.patient_package_id,\n            package_external_id=current.package_external_id,\n            has_payment_allocation=has_payment_allocation,\n        ):\n            raise AppointmentServiceChangeRequiresHuman(\n                "Changing the service on this appointment needs staff review because "\n                "payment or package state is attached to the booking."\n            )\n\n    try:\n        slot = find_exact_slot(\n            db=db,\n            workspace=workspace,\n            branch_id=new_branch_id,\n            service_id=new_service_id,\n            doctor_id=new_doctor_id,\n            requested_start_at=requested_start_at,\n            exclude_appointment_id=current.id,\n        )\n'''
new_logic = '''    new_branch_id = branch_id or current.branch_id\n    new_doctor_id = doctor_id or current.doctor_id\n    new_service_id = service_id or current.service_id\n    target_service = db.scalar(\n        select(Service).where(\n            Service.workspace_id == workspace.id,\n            Service.id == new_service_id,\n            Service.is_active.is_(True),\n        )\n    )\n    if target_service is None:\n        raise AppointmentOperationError("Replacement service not found or inactive.")\n    new_laser_device_key = (\n        laser_device_key or current.laser_device_key\n        if bool(getattr(target_service, "requires_laser_device", False))\n        else None\n    )\n    service_changed = new_service_id != current.service_id\n    device_changed = new_laser_device_key != current.laser_device_key\n    if service_changed or device_changed:\n        has_payment_allocation = (\n            db.scalar(\n                select(PaymentAllocation.id)\n                .where(\n                    PaymentAllocation.workspace_id == workspace.id,\n                    PaymentAllocation.appointment_id == current.id,\n                )\n                .limit(1)\n            )\n            is not None\n        )\n        if service_change_requires_human(\n            payment_status=current.payment_status,\n            amount_paid_minor=current.amount_paid_minor,\n            billing_context=current.billing_context,\n            patient_package_id=current.patient_package_id,\n            package_external_id=current.package_external_id,\n            has_payment_allocation=has_payment_allocation,\n        ):\n            raise AppointmentServiceChangeRequiresHuman(\n                "Changing the service or laser device on this appointment needs staff review because "\n                "payment or package state is attached to the booking."\n            )\n\n    try:\n        slot = find_exact_slot(\n            db=db,\n            workspace=workspace,\n            branch_id=new_branch_id,\n            service_id=new_service_id,\n            doctor_id=new_doctor_id,\n            requested_start_at=requested_start_at,\n            exclude_appointment_id=current.id,\n            laser_device_key=new_laser_device_key,\n        )\n'''
text = replace_once(text, old_logic, new_logic, "appointment operation service/device logic")
text = replace_once(
    text,
    '''        price_minor=slot.price_minor,\n        currency=slot.currency,\n        payment_status=current.payment_status,\n''',
    '''        price_minor=slot.price_minor,\n        currency=slot.currency,\n        laser_device_key=slot.laser_device_key,\n        laser_device_name=slot.laser_device_name,\n        payment_status=current.payment_status,\n''',
    "replacement appointment device",
)
text = replace_once(
    text,
    '''            "old_service_id": str(current.service_id),\n            "new_service_id": str(replacement.service_id),\n            "service_changed": service_changed,\n        },\n    )\n    add_appointment_history(\n''',
    '''            "old_service_id": str(current.service_id),\n            "new_service_id": str(replacement.service_id),\n            "service_changed": service_changed,\n            "old_laser_device_key": current.laser_device_key,\n            "new_laser_device_key": replacement.laser_device_key,\n            "laser_device_changed": device_changed,\n        },\n    )\n    add_appointment_history(\n''',
    "appointment history device metadata",
)
text = replace_once(
    text,
    '''            "old_service_id": current.service_id,\n            "new_service_id": replacement.service_id,\n            "service_changed": service_changed,\n        },\n    )\n    db.flush()\n    return replacement, current\n''',
    '''            "old_service_id": current.service_id,\n            "new_service_id": replacement.service_id,\n            "service_changed": service_changed,\n            "old_laser_device_key": current.laser_device_key,\n            "new_laser_device_key": replacement.laser_device_key,\n            "laser_device_changed": device_changed,\n        },\n    )\n    db.flush()\n    return replacement, current\n''',
    "appointment activity device metadata",
)
path.write_text(text, encoding="utf-8")


# Laser adapter: pass the selected device into the canonical reschedule request.
path = Path("backend/app/integrations/clinic/tia_database_laser.py")
text = path.read_text(encoding="utf-8")
text = replace_once(
    text,
    '''        result = super().reschedule_appointment(request)\n''',
    '''        effective_request = replace(\n            request,\n            laser_device_key=(device_price.device_key if device_price is not None else None),\n        )\n        result = super().reschedule_appointment(effective_request)\n''',
    "laser adapter reschedule device propagation",
)
path.write_text(text, encoding="utf-8")


# Sold package names include service context and read models expose financial facts as information only.
path = Path("backend/app/services/package_offers.py")
text = path.read_text(encoding="utf-8")
text = replace_once(
    text,
    '''    if device_price is None or device_price.price_minor is None:\n        raise PackageOfferError("Standalone device price is unavailable for this package offer.")\n    name = f"{offer.sessions_count} sessions · {offer.device_name}"\n''',
    '''    if device_price is None or device_price.price_minor is None:\n        raise PackageOfferError("Standalone device price is unavailable for this package offer.")\n    service = db.scalar(\n        select(Service).where(\n            Service.workspace_id == workspace_id,\n            Service.id == offer.service_id,\n            Service.is_active.is_(True),\n        )\n    )\n    if service is None:\n        raise PackageOfferNotFound("Package service not found or inactive.")\n    name = f"{service.name} · {offer.device_name} · {offer.sessions_count} sessions"\n''',
    "package sold name",
)
path.write_text(text, encoding="utf-8")


path = Path("backend/app/schemas/patient_packages.py")
text = path.read_text(encoding="utf-8")
text = replace_once(
    text,
    '''    sale_price_minor: int\n    standalone_session_price_minor_at_purchase: int | None = None\n''',
    '''    sale_price_minor: int\n    amount_paid_minor: int = 0\n    amount_refunded_minor: int = 0\n    balance_due_minor: int = 0\n    standalone_session_price_minor_at_purchase: int | None = None\n''',
    "package financial read fields",
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
