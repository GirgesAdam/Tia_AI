from pathlib import Path


def replace_once(text: str, old: str, new: str, label: str) -> str:
    count = text.count(old)
    if count != 1:
        raise RuntimeError(f"{label}: expected one marker, found {count}")
    return text.replace(old, new, 1)


# Preserve adapter compatibility with older/non-laser slot implementations.
path = Path("backend/app/integrations/clinic/tia_database.py")
text = path.read_text(encoding="utf-8")
text = replace_once(
    text,
    '''                laser_device_key=slot.laser_device_key,\n                laser_device_name=slot.laser_device_name,\n            )\n            for slot in native_slots\n''',
    '''                laser_device_key=getattr(slot, "laser_device_key", None),\n                laser_device_name=getattr(slot, "laser_device_name", None),\n            )\n            for slot in native_slots\n''',
    "availability slot backwards compatibility",
)
path.write_text(text, encoding="utf-8")


# Do not add an empty optional device argument to ordinary grounded bookings.
path = Path("backend/app/services/agent_chat.py")
text = path.read_text(encoding="utf-8")
text = replace_once(
    text,
    '''            booking_arguments.update(\n                {\n                    "service_id": service_id,\n                    "branch_id": branch_id,\n                    "doctor_id": doctor_id,\n                    "laser_device_key": laser_device_key,\n                }\n            )\n''',
    '''            booking_arguments.update(\n                {\n                    "service_id": service_id,\n                    "branch_id": branch_id,\n                    "doctor_id": doctor_id,\n                    **(\n                        {"laser_device_key": laser_device_key}\n                        if laser_device_key\n                        else {}\n                    ),\n                }\n            )\n''',
    "omit empty grounded booking device",
)
path.write_text(text, encoding="utf-8")


# Keep financial reads opt-in so package entitlement/usage reads stay lightweight.
path = Path("backend/app/services/patient_packages.py")
text = path.read_text(encoding="utf-8")
text = replace_once(
    text,
    '''def package_read(db: Session, package: PatientPackage, *, on_date: date | None = None) -> PatientPackageRead:\n''',
    '''def package_read(\n    db: Session,\n    package: PatientPackage,\n    *,\n    on_date: date | None = None,\n    include_financials: bool = False,\n) -> PatientPackageRead:\n''',
    "package read financial opt-in signature",
)
text = replace_once(
    text,
    '''    payments, refunds = _package_financial_rows(\n        db, workspace_id=package.workspace_id, package=package, for_update=False\n    )\n    amount_paid_minor = sum(int(row.amount_minor) for row in payments)\n    amount_refunded_minor = sum(int(row.amount_minor) for row in refunds)\n    balance_due_minor = (\n        max(int(package.sale_price_minor) - amount_paid_minor, 0)\n        if effective == "active"\n        else 0\n    )\n''',
    '''    amount_paid_minor = 0\n    amount_refunded_minor = 0\n    balance_due_minor = 0\n    if include_financials:\n        payments, refunds = _package_financial_rows(\n            db, workspace_id=package.workspace_id, package=package, for_update=False\n        )\n        amount_paid_minor = sum(int(row.amount_minor) for row in payments)\n        amount_refunded_minor = sum(int(row.amount_minor) for row in refunds)\n        balance_due_minor = (\n            max(int(package.sale_price_minor) - amount_paid_minor, 0)\n            if effective == "active"\n            else 0\n        )\n''',
    "package read conditional financial query",
)
text = replace_once(
    text,
    '''    usable_only: bool = False,\n    on_date: date | None = None,\n) -> list[PatientPackageRead]:\n''',
    '''    usable_only: bool = False,\n    on_date: date | None = None,\n    include_financials: bool = False,\n) -> list[PatientPackageRead]:\n''',
    "list packages financial opt-in",
)
text = replace_once(
    text,
    '''    reads = [package_read(db, package, on_date=on_date) for package in packages]\n''',
    '''    reads = [\n        package_read(\n            db,\n            package,\n            on_date=on_date,\n            include_financials=include_financials,\n        )\n        for package in packages\n    ]\n''',
    "list packages forwards financial opt-in",
)
path.write_text(text, encoding="utf-8")


# API responses that staff see include financial facts explicitly.
path = Path("backend/app/api/routes/booking.py")
text = path.read_text(encoding="utf-8")
text = replace_once(
    text,
    '''        service_id=service_id,\n        usable_only=usable_only,\n    )\n''',
    '''        service_id=service_id,\n        usable_only=usable_only,\n        include_financials=True,\n    )\n''',
    "patient packages route financials",
)
if text.count("return package_read(db, package)\n") != 2:
    raise RuntimeError("package write response markers mismatch")
text = text.replace(
    "return package_read(db, package)\n",
    "return package_read(db, package, include_financials=True)\n",
)
text = replace_once(
    text,
    '''        read = package_read(db, package)\n''',
    '''        read = package_read(db, package, include_financials=True)\n''',
    "package refund response financials",
)
path.write_text(text, encoding="utf-8")

path = Path("backend/app/api/routes/package_offers.py")
text = path.read_text(encoding="utf-8")
text = replace_once(
    text,
    '''        return package_read(db, package)\n''',
    '''        return package_read(db, package, include_financials=True)\n''',
    "offer purchase response financials",
)
path.write_text(text, encoding="utf-8")


# Preserve the existing audit reason for a service change; use a distinct reason for device-only change.
path = Path("backend/app/services/staff_appointment_edits.py")
text = path.read_text(encoding="utf-8")
text = replace_once(
    text,
    '''                    reason="staff_service_or_device_changed",\n''',
    '''                    reason=(\n                        "staff_service_changed"\n                        if service_changed\n                        else "staff_laser_device_changed"\n                    ),\n''',
    "staff package release reason",
)
path.write_text(text, encoding="utf-8")
