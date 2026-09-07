from __future__ import annotations

"""Apply the small product fixes found by the daily conversation review.

This is intentionally an exact-anchor patcher for the review branch. It does not
introduce keyword routing or change availability/payment accounting rules.
"""

from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]


def replace_once(path: str, old: str, new: str) -> None:
    target = ROOT / path
    text = target.read_text(encoding="utf-8")
    if old not in text:
        raise RuntimeError(f"Expected anchor not found in {path}: {old[:100]!r}")
    if text.count(old) != 1:
        raise RuntimeError(f"Expected exactly one anchor in {path}, found {text.count(old)}")
    target.write_text(text.replace(old, new, 1), encoding="utf-8")


def insert_before(path: str, anchor: str, block: str) -> None:
    replace_once(path, anchor, block + anchor)


def main() -> int:
    # 1) Multiple active packages are allowed, including the same service.
    replace_once(
        "backend/app/services/patient_packages.py",
        '''    existing_usable = list_patient_packages(\n        db, workspace_id=workspace_id, patient_id=patient_id, service_id=service_id,\n        usable_only=True, on_date=purchased_at.date(),\n    )\n    if existing_usable:\n        raise PackageOperationError(\n            "Patient already has an active package for this service."\n        )\n\n''',
        "",
    )

    # 2) Own-customer payment status is a safe read; disputes/complaints still hand off.
    replace_once(
        "backend/app/agents/capability_policy.py",
        '    "service_information": frozenset({"search_services"}),\n',
        '    "service_information": frozenset({"search_services"}),\n    "clinic_information": frozenset(),\n',
    )
    replace_once(
        "backend/app/agents/capability_policy.py",
        '''    if "payment" in risks and "package_refund_quote" not in decision.capabilities:\n        return True, "payment", decision.recommended_handoff_priority\n''',
        '''    safe_payment_reads = {\n        "customer_history",\n        "appointment_list",\n        "package_information",\n        "package_refund_quote",\n    }\n    if "payment" in risks and not safe_payment_reads.intersection(decision.capabilities):\n        return True, "payment", decision.recommended_handoff_priority\n''',
    )

    replace_once(
        "backend/app/agents/turn_models.py",
        '    "service_information",\n',
        '    "service_information",\n    "clinic_information",\n',
    )

    replace_once(
        "backend/app/agents/turn_interpreter.py",
        '''        "CUSTOMER DATA: past visits/services/payments for the current customer use customer_history. "\n        "Remaining package sessions or existing-package usage use package_information. Requests for another "\n''',
        '''        "CUSTOMER DATA: past visits/services/payments for the current customer use customer_history. "\n        "A simple read-only question about whether the current customer's appointment is paid, how it was paid, "\n        "or how much was paid is customer_history and must not set payment risk by itself. Payment disputes, "\n        "charge corrections, failed-payment problems, refunds other than the verified package quote, or requests "\n        "to change financial records may use payment risk/handoff. "\n        "Clinic address, phone, and opening/working hours use clinic_information and are read-only. "\n        "Remaining package sessions or existing-package usage use package_information. Requests for another "\n''',
    )
    replace_once(
        "backend/app/agents/turn_interpreter.py",
        '''        "For an active reschedule flow, select_option is only for a replacement slot that the assistant already presented. "\n        "If the customer instead supplies a new exact target date/time in their own words and clearly commands "\n        "the change now, action=modify, keep appointment_reschedule, and put the exact target in requested_date "\n''',
        '''        "For an active reschedule flow, select_option is only for a replacement slot that the assistant already presented. "\n        "If the customer instead supplies a new exact target date/time in their own words and clearly commands "\n        "the change now, action MUST be modify (never continue and never ask for a second confirmation), keep "\n        "appointment_reschedule, and put the exact target in requested_date "\n''',
    )

    # 3) Verified appointment history exposes payment status/method so the answer can be factual.
    replace_once(
        "backend/app/schemas/patient_history.py",
        '''    price_minor: int\n    currency: str\n    net_paid_minor: int\n''',
        '''    price_minor: int\n    currency: str\n    net_paid_minor: int\n    payment_status: str\n    payment_method: str\n    billing_context: str\n''',
    )
    replace_once(
        "backend/app/services/patient_history.py",
        '''                currency=appointment.currency,\n                net_paid_minor=net_by_appointment.get(appointment.id, 0),\n''',
        '''                currency=appointment.currency,\n                net_paid_minor=net_by_appointment.get(appointment.id, 0),\n                payment_status=appointment.payment_status,\n                payment_method=appointment.payment_method,\n                billing_context=appointment.billing_context,\n''',
    )

    # 4) Single-location public clinic information: use primary-location address/hours without exposing branches.
    replace_once(
        "backend/app/services/agent_chat.py",
        '''from app.models.appointment import Appointment\nfrom app.models.conversation import Conversation\n''',
        '''from app.models.appointment import Appointment\nfrom app.models.branch import Branch\nfrom app.models.conversation import Conversation\n''',
    )
    replace_once(
        "backend/app/services/agent_chat.py",
        '''from app.models.workspace import Workspace\n''',
        '''from app.models.working_hours import BranchWorkingHour\nfrom app.models.workspace import Workspace\n''',
    )

    helper = '''def _clinic_public_info_payload(\n    *,\n    db: Session,\n    workspace: Workspace,\n) -> dict[str, object]:\n    """Verified customer-facing facts for the one clinic location."""\n    if workspace.primary_branch_id is None:\n        return {"ok": False, "reason": "primary_location_missing"}\n    location = db.scalar(\n        select(Branch).where(\n            Branch.workspace_id == workspace.id,\n            Branch.id == workspace.primary_branch_id,\n            Branch.is_active.is_(True),\n        )\n    )\n    if location is None:\n        return {"ok": False, "reason": "primary_location_missing"}\n\n    address_parts: list[str] = []\n    seen: set[str] = set()\n    for raw in (location.address_line1, location.address_line2, location.city, location.state):\n        value = str(raw or "").strip()\n        key = value.casefold()\n        if value and key not in seen:\n            seen.add(key)\n            address_parts.append(value)\n\n    rows = list(\n        db.scalars(\n            select(BranchWorkingHour)\n            .where(\n                BranchWorkingHour.workspace_id == workspace.id,\n                BranchWorkingHour.branch_id == location.id,\n            )\n            .order_by(\n                BranchWorkingHour.weekday,\n                BranchWorkingHour.start_time,\n                BranchWorkingHour.end_time,\n            )\n        )\n    )\n    weekday_names = (\n        "الاثنين", "الثلاثاء", "الأربعاء", "الخميس", "الجمعة", "السبت", "الأحد"\n    )\n    grouped: dict[int, list[str]] = {}\n    for row in rows:\n        grouped.setdefault(int(row.weekday), []).append(\n            f"{row.start_time.strftime('%H:%M')}–{row.end_time.strftime('%H:%M')}"\n        )\n    working_hours = [\n        {"day": weekday_names[weekday], "periods": periods}\n        for weekday, periods in sorted(grouped.items())\n        if 0 <= weekday <= 6\n    ]\n    return {\n        "ok": True,\n        "address": "، ".join(address_parts) or None,\n        "phone": location.phone,\n        "email": location.email,\n        "working_hours": working_hours,\n    }\n\n\n'''
    insert_before(
        "backend/app/services/agent_chat.py",
        "def _customer_package_payload(\n",
        helper,
    )

    replace_once(
        "backend/app/services/agent_chat.py",
        '''    if capabilities.intersection({"package_information", "package_refund_quote"}):\n''',
        '''    if "clinic_information" in capabilities:\n        results["clinic_public_info"] = _clinic_public_info_payload(\n            db=tool_context.db,\n            workspace=tool_context.workspace,\n        )\n        prefetched.add("clinic_public_info")\n\n    if capabilities.intersection({"package_information", "package_refund_quote"}):\n''',
    )
    replace_once(
        "backend/app/services/agent_chat.py",
        '''        "service_information",\n        "pricing",\n''',
        '''        "service_information",\n        "clinic_information",\n        "pricing",\n''',
    )
    replace_once(
        "backend/app/services/agent_chat.py",
        '''    "service_information": frozenset({"clinic_catalog"}),\n    "pricing": frozenset({"clinic_catalog"}),\n''',
        '''    "service_information": frozenset({"clinic_catalog"}),\n    "clinic_information": frozenset({"clinic_public_info"}),\n    "pricing": frozenset({"clinic_catalog"}),\n''',
    )
    replace_once(
        "backend/app/services/agent_chat.py",
        '''        "service_information",\n        "pricing",\n        "branch_discovery",\n''',
        '''        "service_information",\n        "clinic_information",\n        "pricing",\n        "branch_discovery",\n''',
    )

    # 5) Allow multiple usable same-service packages and consume deterministically.
    helper2 = '''def _preferred_usable_package(packages: list[object]) -> object | None:\n    """Pick one usable package deterministically: earliest expiry, then oldest purchase."""\n    if not packages:\n        return None\n\n    def key(item: object) -> tuple[object, ...]:\n        expires_at = getattr(item, "expires_at", None)\n        purchased_at = getattr(item, "purchased_at", None)\n        return (\n            expires_at is None,\n            str(expires_at or "9999-12-31"),\n            str(purchased_at or ""),\n            str(getattr(item, "id", "")),\n        )\n\n    return min(packages, key=key)\n\n\n'''
    insert_before(
        "backend/app/services/agent_chat.py",
        "def _booking_package_requirement_reply(\n",
        helper2,
    )
    replace_once(
        "backend/app/services/agent_chat.py",
        '''    if len(usable) != 1:\n        return "مش لاقي باكدج نشطة لنفس الخدمة أقدر أحجز منها، فمش هحوّل الطلب تلقائياً لحجز عادي مدفوع."\n    if start_at is not None:\n        try:\n            validate_package_for_booking(\n                db, workspace_id=workspace_id, package_id=usable[0].id, patient_id=patient_id,\n''',
        '''    selected = _preferred_usable_package(list(usable))\n    if selected is None:\n        return "مش لاقي باكدج نشطة لنفس الخدمة أقدر أحجز منها، فمش هحوّل الطلب تلقائياً لحجز عادي مدفوع."\n    if start_at is not None:\n        try:\n            validate_package_for_booking(\n                db, workspace_id=workspace_id, package_id=selected.id, patient_id=patient_id,\n''',
    )
    replace_once(
        "backend/app/services/agent_chat.py",
        '''def _package_booking_success_reply(appointment_payload: dict[str, object], package_result: dict[str, object] | None) -> str:\n    reply = format_booking_success(appointment_payload)\n    if not package_result:\n        return reply\n    remaining = int(package_result.get("sessions_remaining") or 0)\n    return f"{reply} الحجز اتحسب من الباكدج، وفاضلك {remaining} جلسات فيها."\n''',
        '''def _package_booking_success_reply(appointment_payload: dict[str, object], package_result: dict[str, object] | None) -> str:\n    if not package_result:\n        return format_booking_success(appointment_payload)\n\n    date_text = ""\n    time_text = ""\n    try:\n        start = datetime.fromisoformat(str(appointment_payload.get("start_local")))\n        end = datetime.fromisoformat(str(appointment_payload.get("end_local")))\n        date_text = start.strftime("%d/%m/%Y")\n        time_text = f"{start.strftime('%H:%M')}–{end.strftime('%H:%M')}"\n    except (TypeError, ValueError):\n        pass\n    status = str(appointment_payload.get("status") or "")\n    opening = "تمام، الحجز اتأكد" if status == "confirmed" else "تمام، الحجز اتسجل ومستني التأكيد"\n    details = [\n        appointment_payload.get("service"),\n        appointment_payload.get("doctor"),\n        " ".join(part for part in (date_text, time_text) if part) or None,\n    ]\n    suffix = "، ".join(str(item) for item in details if item)\n    remaining = int(package_result.get("sessions_remaining") or 0)\n    package_name = str(package_result.get("package_name") or "الباكدج").strip()\n    return (\n        opening\n        + (f": {suffix}." if suffix else ".")\n        + f" الجلسة اتحسبت من {package_name}، وفاضلك {remaining} جلسات فيها، ومفيش مبلغ جديد مطلوب للجلسة دي."\n    )\n''',
    )
    replace_once(
        "backend/app/services/agent_chat.py",
        '''    Package selection is deterministic domain logic, not an LLM decision: each\n    package belongs to one service, and the product allows at most one usable\n    package for that patient/service at a time.\n''',
        '''    Package selection is deterministic domain logic, not an LLM decision.\n    When several same-service packages are usable, consume the one that expires\n    first (then the oldest purchase) so entitlement is not wasted.\n''',
    )
    replace_once(
        "backend/app/services/agent_chat.py",
        '''    if len(usable) != 1:\n        return None\n\n    package = validate_package_for_booking(\n        db,\n        workspace_id=workspace_id,\n        package_id=usable[0].id,\n''',
        '''    selected = _preferred_usable_package(list(usable))\n    if selected is None:\n        return None\n\n    package = validate_package_for_booking(\n        db,\n        workspace_id=workspace_id,\n        package_id=selected.id,\n''',
    )
    replace_once(
        "backend/app/services/agent_chat.py",
        '''    if intent == "purchase":\n        if usable:\n            current = usable[0]\n            remaining = int(current.get("sessions_remaining") or 0)\n            name = str(current.get("name") or "الباكدج الحالية")\n            return f"عندك {name} لنفس الخدمة شغالة حالياً وفاضلك {remaining} جلسات. استخدم الجلسات المتبقية فيها الأول قبل بدء باكدج جديدة لنفس الخدمة."\n        return (\n''',
        '''    if intent == "purchase":\n        if usable:\n            current = usable[0]\n            remaining = int(current.get("sessions_remaining") or 0)\n            name = str(current.get("name") or "الباكدج الحالية")\n            return (\n                f"عندك {name} لنفس الخدمة شغالة حالياً وفاضلك {remaining} جلسات، "\n                "وينفع يبقى عندك باكدج تانية كمان. "\n                "بس تفاصيل أي باكدج جديدة من عدد الجلسات والسعر لازم تكون مسجلة كعرض موثوق في إعدادات العيادة."\n            )\n        return (\n''',
    )

    # Compile touched Python files so the patch fails before committing bad code.
    touched = [
        "backend/app/services/patient_packages.py",
        "backend/app/agents/capability_policy.py",
        "backend/app/agents/turn_models.py",
        "backend/app/agents/turn_interpreter.py",
        "backend/app/schemas/patient_history.py",
        "backend/app/services/patient_history.py",
        "backend/app/services/agent_chat.py",
    ]
    for rel in touched:
        source = (ROOT / rel).read_text(encoding="utf-8")
        compile(source, rel, "exec")

    print("Applied daily-review product fixes successfully.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
