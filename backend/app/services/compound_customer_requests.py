from __future__ import annotations

from dataclasses import dataclass
from uuid import UUID

from sqlalchemy.orm import Session

from app.agents.turn_models import CompoundRequestedItem, SemanticCapabilityDecision
from app.models.agent_action import AgentAction
from app.models.conversation import Conversation
from app.models.patient import Patient
from app.models.workspace import Workspace
from app.services.package_offers import (
    PackageOfferError,
    list_package_offers,
    purchase_package_offer,
)
from app.services.patient_packages import PackageOperationError

MAX_COMPOUND_ITEMS = 6
COMPOUND_QUEUE_KEY = "compound_request_queue"
COMPOUND_TOTAL_KEY = "compound_request_total"
COMPOUND_COMPLETED_KEY = "compound_request_completed"
COMPOUND_CURRENT_SERVICE_KEY = "compound_current_service_name"


@dataclass(frozen=True)
class CompoundPackageBatchResult:
    ok: bool
    reply: str
    purchased_count: int = 0


def _catalog_ids(catalog: dict[str, object], collection: str) -> set[str]:
    rows = catalog.get(collection)
    if not isinstance(rows, list):
        return set()
    return {
        str(row.get("id"))
        for row in rows
        if isinstance(row, dict) and row.get("id")
    }


def _catalog_doctor_service_ids(catalog: dict[str, object], doctor_id: str) -> set[str]:
    rows = catalog.get("doctors")
    if not isinstance(rows, list):
        return set()
    for row in rows:
        if not isinstance(row, dict) or str(row.get("id") or "") != doctor_id:
            continue
        raw = row.get("service_ids")
        if not isinstance(raw, list):
            return set()
        return {str(value) for value in raw if value}
    return set()


def catalog_service_name(catalog: dict[str, object], service_id: str | None) -> str | None:
    if not service_id:
        return None
    rows = catalog.get("services")
    if not isinstance(rows, list):
        return None
    for row in rows:
        if not isinstance(row, dict) or str(row.get("id") or "") != str(service_id):
            continue
        name = row.get("name") or row.get("service_name")
        return str(name).strip() if name else None
    return None


def _catalog_service_laser_policy(
    catalog: dict[str, object],
    service_id: str | None,
) -> tuple[bool | None, set[str]]:
    """Return canonical laser requirements for one grounded service.

    None means the catalog row does not expose laser metadata, so grounding
    leaves the item unchanged rather than guessing.
    """
    if not service_id:
        return None, set()
    rows = catalog.get("services")
    if not isinstance(rows, list):
        return None, set()
    for row in rows:
        if not isinstance(row, dict) or str(row.get("id") or "") != str(service_id):
            continue
        if "requires_laser_device" not in row:
            return None, set()
        requires_laser_device = bool(row.get("requires_laser_device"))
        raw_devices = row.get("laser_devices")
        allowed_devices: set[str] = set()
        if isinstance(raw_devices, list):
            for device in raw_devices:
                if not isinstance(device, dict):
                    continue
                device_key = device.get("device_key")
                if device_key:
                    allowed_devices.add(str(device_key))
        return requires_laser_device, allowed_devices
    return None, set()


def ground_compound_requested_items(
    items: list[CompoundRequestedItem],
    catalog: dict[str, object],
) -> list[CompoundRequestedItem]:
    """Validate every compound item against canonical catalog IDs.

    The LLM identifies semantic operations, but this function is the deterministic
    grounding boundary before any queued request can reach booking or package writes.
    Customer wording is never inspected here.
    """
    service_ids = _catalog_ids(catalog, "services")
    doctor_ids = _catalog_ids(catalog, "doctors")
    grounded: list[CompoundRequestedItem] = []
    for item in items[:MAX_COMPOUND_ITEMS]:
        raw_service_id = str(item.service_id or "")
        service_id = raw_service_id if raw_service_id in service_ids else None
        service_candidates = [
            str(value)
            for value in item.service_candidate_ids
            if str(value) in service_ids
        ]
        service_candidates = list(dict.fromkeys(service_candidates))

        raw_doctor_id = str(item.doctor_id or "")
        doctor_id = raw_doctor_id if raw_doctor_id in doctor_ids else None
        doctor_candidates = [
            str(value)
            for value in item.doctor_candidate_ids
            if str(value) in doctor_ids
        ]
        doctor_candidates = list(dict.fromkeys(doctor_candidates))

        if doctor_id:
            compatible_services = _catalog_doctor_service_ids(catalog, doctor_id)
            if service_id and compatible_services and service_id not in compatible_services:
                service_id = None
            if compatible_services:
                service_candidates = [
                    value for value in service_candidates if value in compatible_services
                ]

        laser_device_key = item.laser_device_key
        if service_id:
            requires_laser_device, allowed_laser_devices = _catalog_service_laser_policy(
                catalog,
                service_id,
            )
            if requires_laser_device is False:
                laser_device_key = None
            elif (
                requires_laser_device is True
                and laser_device_key
                and allowed_laser_devices
                and str(laser_device_key) not in allowed_laser_devices
            ):
                laser_device_key = None

        grounded.append(
            item.model_copy(
                update={
                    "service_id": service_id,
                    "service_candidate_ids": service_candidates,
                    "doctor_id": doctor_id,
                    "doctor_candidate_ids": doctor_candidates,
                    "laser_device_key": laser_device_key,
                }
            )
        )
    return grounded


def has_compound_request(items: list[CompoundRequestedItem]) -> bool:
    return len(items) >= 2


def package_items(items: list[CompoundRequestedItem]) -> list[CompoundRequestedItem]:
    return [item for item in items if item.kind == "package_purchase"]


def appointment_items(items: list[CompoundRequestedItem]) -> list[CompoundRequestedItem]:
    return [item for item in items if item.kind == "appointment"]


def compound_union_decision(
    base: SemanticCapabilityDecision,
    items: list[CompoundRequestedItem],
) -> SemanticCapabilityDecision:
    """Derive the smallest union capability set from structured compound items."""
    capabilities = {str(value) for value in base.capabilities}
    if package_items(items):
        capabilities.update({"package_information", "package_purchase"})
    if appointment_items(items):
        capabilities.update({"availability_discovery", "appointment_creation"})
    hints = base.entity_hints.model_copy(update={"requested_items": list(items)})
    return base.model_copy(
        update={
            "capabilities": sorted(capabilities),
            "flow_signal": "start_booking" if appointment_items(items) else "none",
            "package_intent": "none",
            "entity_hints": hints,
        }
    )


def appointment_decision_from_item(
    base: SemanticCapabilityDecision,
    item: CompoundRequestedItem,
) -> SemanticCapabilityDecision:
    hints = base.entity_hints.model_copy(
        update={
            "service_query": item.service_query,
            "service_id": item.service_id,
            "service_candidate_ids": list(item.service_candidate_ids),
            "doctor_query": item.doctor_query,
            "doctor_id": item.doctor_id,
            "doctor_candidate_ids": list(item.doctor_candidate_ids),
            "laser_device_key": item.laser_device_key,
            "package_sessions_count": None,
            "requested_date": item.requested_date,
            "requested_start_time": item.requested_start_time,
            "not_before_time": item.not_before_time,
            "not_after_time": item.not_after_time,
            "appointment_reference": None,
            "appointment_id": None,
            "requested_items": [],
        }
    )
    capabilities = ["availability_discovery", "appointment_creation"]
    if item.package_intent == "use_existing":
        capabilities.append("package_information")
    return base.model_copy(
        update={
            "domains": ["booking"],
            "capabilities": capabilities,
            "flow_signal": "start_booking",
            "package_intent": item.package_intent,
            "entity_hints": hints,
            "missing_information": list(item.missing_information),
            "reason": f"Compound request appointment item: {base.reason}",
        }
    )


def appointment_item_state(
    item: CompoundRequestedItem,
    *,
    remaining: list[CompoundRequestedItem],
    total: int,
    completed: int,
    catalog: dict[str, object],
) -> dict[str, object]:
    state: dict[str, object] = {
        "service_candidate_ids": list(item.service_candidate_ids),
        "doctor_candidate_ids": list(item.doctor_candidate_ids),
        COMPOUND_QUEUE_KEY: [entry.model_dump(mode="json") for entry in remaining],
        COMPOUND_TOTAL_KEY: int(total),
        COMPOUND_COMPLETED_KEY: int(completed),
    }
    optional = {
        "service_query": item.service_query,
        "service_id": item.service_id,
        "doctor_query": item.doctor_query,
        "doctor_id": item.doctor_id,
        "laser_device_key": item.laser_device_key,
        "requested_date": item.requested_date,
        "requested_start_time": item.requested_start_time,
        "not_before_time": item.not_before_time,
        "not_after_time": item.not_after_time,
    }
    for key, value in optional.items():
        if value not in (None, ""):
            state[key] = value
    if item.package_intent in {"use_existing", "avoid_existing"}:
        state["package_intent"] = item.package_intent
    service_name = catalog_service_name(catalog, item.service_id)
    if service_name:
        state[COMPOUND_CURRENT_SERVICE_KEY] = service_name
    return state


def queue_from_flow_state(state: dict[str, object] | None) -> list[CompoundRequestedItem]:
    if not isinstance(state, dict):
        return []
    raw = state.get(COMPOUND_QUEUE_KEY)
    if not isinstance(raw, list):
        return []
    result: list[CompoundRequestedItem] = []
    for value in raw[:MAX_COMPOUND_ITEMS]:
        if not isinstance(value, dict):
            continue
        try:
            result.append(CompoundRequestedItem.model_validate(value))
        except ValueError:
            continue
    return result


def compound_progress(state: dict[str, object] | None) -> tuple[int, int]:
    if not isinstance(state, dict):
        return 0, 0
    try:
        total = int(state.get(COMPOUND_TOTAL_KEY) or 0)
        completed = int(state.get(COMPOUND_COMPLETED_KEY) or 0)
    except (TypeError, ValueError):
        return 0, 0
    return max(0, completed), max(0, total)


def _offer_candidates(
    offers: list[object],
    item: CompoundRequestedItem,
) -> list[object]:
    if not item.service_id or item.package_sessions_count is None or not item.laser_device_key:
        return []
    return [
        offer
        for offer in offers
        if str(getattr(offer, "service_id", "")) == str(item.service_id)
        and int(getattr(offer, "sessions_count", 0)) == int(item.package_sessions_count)
        and str(getattr(offer, "device_key", "")) == str(item.laser_device_key)
    ]


def _money_label(minor: int, currency: str) -> str:
    whole, cents = divmod(max(0, int(minor)), 100)
    amount = f"{whole:,}" if cents == 0 else f"{whole:,}.{cents:02d}"
    return f"{amount} جنيه" if currency.upper() == "EGP" else f"{amount} {currency.upper()}"


def purchase_compound_package_batch(
    db: Session,
    *,
    workspace: Workspace,
    patient: Patient,
    conversation: Conversation,
    run_id: UUID,
    items: list[CompoundRequestedItem],
) -> CompoundPackageBatchResult:
    """Validate all requested package offers before creating any of them.

    All writes share one transaction. If any later package creation fails, rollback
    removes the earlier package creations too. No customer-reported payment is
    recorded by this path; every package starts with amount_paid_minor=0.
    """
    if not items:
        return CompoundPackageBatchResult(ok=True, reply="", purchased_count=0)

    offers = list_package_offers(
        db,
        workspace_id=workspace.id,
        active_only=True,
    )
    resolved: list[tuple[CompoundRequestedItem, object]] = []
    for index, item in enumerate(items, start=1):
        if not item.service_id:
            return CompoundPackageBatchResult(
                ok=False,
                reply=f"محتاج تحدد خدمة الباكيدج رقم {index} قبل ما أسجل أي باكيدج من الطلب.",
            )
        if item.package_sessions_count is None:
            return CompoundPackageBatchResult(
                ok=False,
                reply=f"محتاج تحدد عدد جلسات الباكيدج رقم {index} (3 أو 6 أو 9) قبل التنفيذ.",
            )
        if not item.laser_device_key:
            return CompoundPackageBatchResult(
                ok=False,
                reply=f"محتاج تحدد جهاز الليزر للباكيدج رقم {index} قبل التنفيذ لأن العرض مرتبط بالجهاز.",
            )
        matches = _offer_candidates(offers, item)
        if len(matches) != 1:
            return CompoundPackageBatchResult(
                ok=False,
                reply=(
                    f"الباكيدج رقم {index} بالمواصفات المطلوبة مش موجودة أو مش مفعلة حالياً، "
                    "فمش هاسجل أي جزء من الطلب لحد ما كل العروض تبقى موثقة."
                ),
            )
        resolved.append((item, matches[0]))

    created: list[tuple[object, object]] = []
    try:
        for index, (_item, offer) in enumerate(resolved, start=1):
            offer_id = UUID(str(offer.id))
            package = purchase_package_offer(
                db,
                workspace_id=workspace.id,
                patient_id=patient.id,
                offer_id=offer_id,
                amount_paid_minor=0,
                payment_method="unknown",
                created_by_user_id=None,
                idempotency_key=f"agent-compound-package:{run_id}:{index}:{offer_id}"[:128],
                actor_type="ai",
            )
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
                    input_json={"offer_id": str(offer_id), "compound_index": index},
                    output_json={
                        "ok": True,
                        "package_id": str(package.id),
                        "offer_id": str(offer_id),
                        "service_id": str(package.service_id),
                        "laser_device_key": package.laser_device_key,
                        "sessions_purchased": int(package.sessions_purchased),
                        "sale_price_minor": int(package.sale_price_minor),
                        "amount_paid_minor": 0,
                    },
                )
            )
            created.append((offer, package))
        db.commit()
    except (PackageOfferError, PackageOperationError, ValueError) as exc:
        db.rollback()
        return CompoundPackageBatchResult(
            ok=False,
            reply=f"ماقدرتش أسجل الباكيدجات بأمان، فتم إلغاء العملية كلها بدون تسجيل جزئي: {exc}",
        )

    summaries: list[str] = []
    for offer, _package in created:
        summaries.append(
            f"{getattr(offer, 'service_name', 'الخدمة')} · {getattr(offer, 'device_name', 'الجهاز')} · "
            f"{int(getattr(offer, 'sessions_count', 0))} جلسات = "
            f"{_money_label(int(getattr(offer, 'price_minor', 0)), str(getattr(offer, 'currency', 'EGP')))}"
        )
    reply = "تم تسجيل الباكيدجات المطلوبة: " + " | ".join(summaries)
    reply += ". ما سجلتش أي دفعة؛ الدفع بيتسجل فقط لما يكون مؤكد عند العيادة."
    return CompoundPackageBatchResult(ok=True, reply=reply, purchased_count=len(created))
