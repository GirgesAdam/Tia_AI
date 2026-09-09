from pathlib import Path


agent_path = Path("backend/app/services/agent_chat.py")
source = agent_path.read_text(encoding="utf-8")


def replace_once(old: str, new: str) -> None:
    global source
    count = source.count(old)
    if count != 1:
        raise RuntimeError(f"Expected one marker, found {count}: {old[:100]!r}")
    source = source.replace(old, new, 1)


def replace_function(name: str, replacement: str) -> None:
    global source
    start = source.index(f"def {name}(")
    next_def = source.find("\ndef ", start + 1)
    if next_def < 0:
        raise RuntimeError(f"Could not find end of function {name}")
    source = source[:start] + replacement.rstrip() + "\n" + source[next_def + 1 :]


replace_once(
    "from app.services.handoffs import get_active_handoff\nfrom app.services.patient_packages import (\n",
    "from app.services.handoffs import get_active_handoff\n"
    "from app.services.package_offers import (\n"
    "    PackageOfferError,\n"
    "    list_package_offers,\n"
    "    purchase_package_offer,\n"
    ")\n"
    "from app.services.patient_packages import (\n",
)
replace_once(
    "    _package_financial_rows,\n    list_patient_packages,\n",
    "    PackageOperationError,\n    _package_financial_rows,\n    list_patient_packages,\n",
)

replace_once(
    '''    if "package_information" not in capabilities:\n        capabilities.append("package_information")\n    return decision.model_copy(update={"capabilities": capabilities, "flow_signal": "none"})\n''',
    '''    if "package_information" not in capabilities:\n        capabilities.append("package_information")\n    if intent == "purchase" and "package_purchase" not in capabilities:\n        capabilities.append("package_purchase")\n    return decision.model_copy(update={"capabilities": capabilities, "flow_signal": "none"})\n''',
)

marker = "\ndef _preferred_usable_package(packages: list[object]) -> object | None:\n"
if source.count(marker) != 1:
    raise RuntimeError("Package helper insertion point is not unique")
helper = r'''
def _active_package_offer_payload(
    *,
    db: Session,
    workspace_id: UUID,
    service_id: str = "",
) -> dict[str, object]:
    service_uuid = _uuid_from_metadata(service_id) if service_id else None
    offers = list_package_offers(
        db,
        workspace_id=workspace_id,
        service_id=service_uuid,
        active_only=True,
    )
    return {"ok": True, "offers": [item.model_dump(mode="json") for item in offers]}


def _money_minor_label(value: object, currency: object = "EGP") -> str:
    try:
        minor = max(0, int(value or 0))
    except (TypeError, ValueError):
        minor = 0
    whole, cents = divmod(minor, 100)
    amount = f"{whole:,}" if cents == 0 else f"{whole:,}.{cents:02d}"
    code = str(currency or "EGP").upper()
    return f"{amount} جنيه" if code == "EGP" else f"{amount} {code}"


def _package_offer_candidates(
    payload: dict[str, object],
    *,
    decision: SemanticCapabilityDecision,
) -> list[dict[str, object]]:
    raw = payload.get("offers")
    offers = [item for item in raw if isinstance(item, dict)] if isinstance(raw, list) else []
    service_id = str(decision.entity_hints.service_id or "").strip()
    device_key = str(decision.entity_hints.laser_device_key or "").strip()
    sessions = decision.entity_hints.package_sessions_count
    if service_id:
        offers = [item for item in offers if str(item.get("service_id") or "") == service_id]
    if device_key:
        offers = [item for item in offers if str(item.get("device_key") or "") == device_key]
    if sessions is not None:
        offers = [item for item in offers if int(item.get("sessions_count") or 0) == int(sessions)]
    return offers


def _package_offer_options_text(offers: list[dict[str, object]]) -> str:
    rows: list[str] = []
    for item in offers[:12]:
        service_name = str(item.get("service_name") or "الخدمة").strip()
        device_name = str(item.get("device_name") or "الجهاز").strip()
        sessions = int(item.get("sessions_count") or 0)
        price = _money_minor_label(item.get("price_minor"), item.get("currency"))
        rows.append(f"{service_name} · {device_name} · {sessions} جلسات = {price}")
    return " | ".join(rows)


def _verified_package_offer_action(
    *,
    db: Session,
    workspace: Workspace,
    patient: Patient,
    conversation: Conversation,
    run_id: UUID,
    decision: SemanticCapabilityDecision,
    offer_payload: dict[str, object],
    package_payload: dict[str, object] | None,
    allow_purchase: bool,
) -> tuple[str, str] | None:
    intent = str(decision.package_intent)
    if intent not in {"purchase", "inquire"}:
        return None

    candidates = _package_offer_candidates(offer_payload, decision=decision)
    raw_offers = offer_payload.get("offers")
    all_offers = (
        [item for item in raw_offers if isinstance(item, dict)]
        if isinstance(raw_offers, list)
        else []
    )
    service_id = str(decision.entity_hints.service_id or "").strip()
    device_key = str(decision.entity_hints.laser_device_key or "").strip()
    sessions = decision.entity_hints.package_sessions_count

    if intent == "inquire":
        visible = candidates if (service_id or device_key or sessions is not None) else all_offers
        if not visible:
            return (
                "مفيش باكيدج ليزر مسجلة بالمواصفات دي حالياً. أقدر أقولك العروض المتاحة لو تحب.",
                "deterministic:verified-package-offers",
            )
        prefix = "الباكيدجات المسجلة حالياً: "
        if isinstance(package_payload, dict):
            usable = package_payload.get("usable_packages")
            if isinstance(usable, list) and usable and isinstance(usable[0], dict):
                current = usable[0]
                prefix = (
                    f"عندك بالفعل {current.get('name') or 'باكيدج'} وفاضلك "
                    f"{int(current.get('sessions_remaining') or 0)} جلسات. "
                    "والعروض المتاحة حالياً: "
                )
        return (
            prefix + _package_offer_options_text(visible),
            "deterministic:verified-package-offers",
        )

    if not allow_purchase:
        return None
    if not all_offers:
        return (
            "مفيش باكيدجات ليزر مفعلة للبيع حالياً، فمش هاسجل باكيدج غير موجودة في إعدادات العيادة.",
            "deterministic:verified-package-purchase",
        )
    if not service_id:
        return (
            "محتاج تحدد خدمة الليزر اللي عايز الباكيدج ليها. العروض الحالية: "
            + _package_offer_options_text(all_offers),
            "deterministic:verified-package-purchase",
        )
    if sessions is None:
        visible = _package_offer_candidates(offer_payload, decision=decision)
        return (
            "محتاج تحدد عدد جلسات الباكيدج من العروض المسجلة. المتاح للخدمة دي: "
            + (_package_offer_options_text(visible) if visible else "لا توجد عروض مطابقة حالياً."),
            "deterministic:verified-package-purchase",
        )
    if not device_key:
        visible = _package_offer_candidates(offer_payload, decision=decision)
        return (
            "محتاج تحدد جهاز الليزر للباكيدج لأن السعر والاستحقاق مرتبطين بالجهاز. المتاح: "
            + (_package_offer_options_text(visible) if visible else "لا توجد عروض مطابقة حالياً."),
            "deterministic:verified-package-purchase",
        )
    if len(candidates) != 1:
        return (
            "العرض بالمواصفات دي مش موجود أو مش مفعّل حالياً، فمش هاسجل باكيدج بسعر أو جهاز غير موثوق.",
            "deterministic:verified-package-purchase",
        )

    selected = candidates[0]
    offer_id = _uuid_from_metadata(selected.get("id"))
    if offer_id is None:
        return (
            "تعذر التحقق من عرض الباكيدج المسجل. فريق العيادة يقدر يكمل التسجيل يدويًا.",
            "deterministic:verified-package-purchase",
        )
    try:
        package = purchase_package_offer(
            db,
            workspace_id=workspace.id,
            patient_id=patient.id,
            offer_id=offer_id,
            amount_paid_minor=0,
            payment_method="unknown",
            created_by_user_id=None,
            idempotency_key=f"agent-package:{run_id}:{offer_id}"[:128],
            actor_type="ai",
        )
        action_payload = {
            "ok": True,
            "package_id": str(package.id),
            "offer_id": str(offer_id),
            "service_id": str(package.service_id),
            "laser_device_key": package.laser_device_key,
            "sessions_purchased": int(package.sessions_purchased),
            "sale_price_minor": int(package.sale_price_minor),
            "amount_paid_minor": 0,
        }
        db.add(
            AgentAction(
                workspace_id=workspace.id,
                conversation_id=conversation.id,
                patient_id=patient.id,
                appointment_id=None,
                run_id=run_id,
                tool_name="purchase_package_offer",
                action_type="package_purchase",
                status="success",
                input_json={"offer_id": str(offer_id)},
                output_json=action_payload,
            )
        )
        db.commit()
    except (PackageOfferError, PackageOperationError) as exc:
        db.rollback()
        return (
            f"ماقدرتش أسجل الباكيدج لأن بيانات العرض الحالية مش صالحة للتنفيذ: {exc}",
            "deterministic:verified-package-purchase",
        )

    service_name = str(selected.get("service_name") or "الخدمة").strip()
    device_name = str(selected.get("device_name") or "الجهاز").strip()
    price = _money_minor_label(selected.get("price_minor"), selected.get("currency"))
    return (
        f"تمام، اتسجلت باكيدج {service_name} على {device_name}: "
        f"{int(selected.get('sessions_count') or 0)} جلسات بسعر {price}. "
        "أي دفعة بتتسجل فقط لما تكون مؤكدة عند العيادة، ومش افترضت إن مبلغ اتدفع.",
        "deterministic:verified-package-purchase",
    )

'''
source = source.replace(marker, "\n" + helper + marker, 1)

replace_function(
    "_booking_package_requirement_reply",
    r'''def _booking_package_requirement_reply(
    *,
    db: Session,
    workspace_id: UUID,
    patient_id: UUID,
    service_id: UUID | None,
    start_at: datetime | None,
    package_intent: str,
    laser_device_key: str | None = None,
) -> str | None:
    if package_intent != "use_existing":
        return None
    if service_id is None:
        return "محتاج أحدد الخدمة الأول عشان أتأكد إن عندك باكدج نشطة ليها قبل الحجز."
    usable = list_patient_packages(
        db,
        workspace_id=workspace_id,
        patient_id=patient_id,
        service_id=service_id,
        usable_only=True,
        on_date=start_at.date() if start_at is not None else None,
    )
    usable = [
        item
        for item in usable
        if item.laser_device_key is None or item.laser_device_key == laser_device_key
    ]
    selected = _preferred_usable_package(list(usable))
    if selected is None:
        return "مش لاقي باكدج نشطة لنفس الخدمة والجهاز أقدر أحجز منها، فمش هحوّل الطلب تلقائياً لحجز عادي مدفوع."
    if start_at is not None:
        try:
            validate_package_for_booking(
                db,
                workspace_id=workspace_id,
                package_id=selected.id,
                patient_id=patient_id,
                service_id=service_id,
                appointment_start_at=start_at,
                sessions=1,
                laser_device_key=laser_device_key,
            )
        except ValueError:
            return "الباكدج الموجودة مش صالحة للميعاد أو الجهاز المطلوب، فمش هحوّل الطلب لحجز عادي من غير موافقتك."
    return None
''',
)

replace_once(
    '        + f" الجلسة اتحسبت من {package_name}، وفاضلك {remaining} جلسات فيها، ومفيش مبلغ جديد مطلوب للجلسة دي."\n',
    '        + f" الجلسة اتحسبت من {package_name}، وفاضلك {remaining} جلسات فيها، "\n'
    '        + "وما اتضافش سعر جلسة منفصل على الحجز ده."\n',
)

apply_start = source.index("def _apply_single_matching_package_to_booking(")
apply_end = source.index("\ndef _prefetch_read_tools(", apply_start)
apply_block = source[apply_start:apply_end]
old_validate = '''        service_id=appointment.service_id,\n        appointment_start_at=appointment.start_at,\n        sessions=1,\n    )\n'''
new_validate = '''        service_id=appointment.service_id,\n        appointment_start_at=appointment.start_at,\n        sessions=1,\n        laser_device_key=appointment.laser_device_key,\n    )\n'''
if apply_block.count(old_validate) != 1:
    raise RuntimeError("Agent package auto-use validate marker mismatch")
apply_block = apply_block.replace(old_validate, new_validate, 1)
source = source[:apply_start] + apply_block + source[apply_end:]

replace_once(
    '    if capabilities.intersection({"package_information", "package_refund_quote"}):\n',
    '    if capabilities.intersection({"package_information", "package_purchase", "package_refund_quote"}):\n',
)
replace_once(
    '''        results["customer_packages"] = package_payload\n        prefetched.add("customer_packages")\n        if "package_refund_quote" in capabilities:\n''',
    '''        results["customer_packages"] = package_payload\n        prefetched.add("customer_packages")\n        if capabilities.intersection({"package_information", "package_purchase"}):\n            results["package_offers"] = _active_package_offer_payload(\n                db=tool_context.db,\n                workspace_id=tool_context.workspace.id,\n                service_id=service_id,\n            )\n            prefetched.add("package_offers")\n        if "package_refund_quote" in capabilities:\n''',
)
replace_once(
    '''        package_requirement_reply = _booking_package_requirement_reply(\n            db=db, workspace_id=tool_context.workspace.id, patient_id=tool_context.patient.id,\n            service_id=service_id, start_at=start_at, package_intent=booking_package_intent,\n        )\n''',
    '''        package_requirement_reply = _booking_package_requirement_reply(\n            db=db, workspace_id=tool_context.workspace.id, patient_id=tool_context.patient.id,\n            service_id=service_id, start_at=start_at, package_intent=booking_package_intent,\n            laser_device_key=str((flow.entity_state or {}).get("laser_device_key") or "") or None,\n        )\n''',
)

purchase_marker = '''        if (\n            prefetch_direct is None\n            and "package_refund_quote" not in policy.capabilities\n            and str(semantic_decision.package_intent) == "purchase"\n        ):\n'''
if source.count(purchase_marker) != 1:
    raise RuntimeError("Package direct-response insertion marker mismatch")
offer_action = '''        if (\n            prefetch_direct is None\n            and str(semantic_decision.package_intent) in {"purchase", "inquire"}\n        ):\n            offer_payload = prefetched_results.get("package_offers")\n            if isinstance(offer_payload, dict):\n                package_offer_action = _verified_package_offer_action(\n                    db=db,\n                    workspace=workspace,\n                    patient=patient,\n                    conversation=conversation,\n                    run_id=run_id,\n                    decision=semantic_decision,\n                    offer_payload=offer_payload,\n                    package_payload=(\n                        prefetched_results.get("customer_packages")\n                        if isinstance(prefetched_results.get("customer_packages"), dict)\n                        else None\n                    ),\n                    allow_purchase="package_purchase" in policy.capabilities,\n                )\n                if package_offer_action is not None:\n                    prefetch_direct = package_offer_action\n\n'''
source = source.replace(purchase_marker, offer_action + purchase_marker, 1)
agent_path.write_text(source, encoding="utf-8")


interpreter_path = Path("backend/app/agents/turn_interpreter.py")
interpreter = interpreter_path.read_text(encoding="utf-8")n