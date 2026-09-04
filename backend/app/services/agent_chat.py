from __future__ import annotations

import json
import logging
from datetime import UTC, datetime, timedelta
from time import perf_counter
from uuid import UUID, uuid4
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from langchain_core.messages import AIMessage, BaseMessage, HumanMessage
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.agents.availability_presentation import format_availability_windows_reply
from app.agents.capability_policy import (
    CapabilityPolicyDecision,
    ToolAuthorizationError,
    authorize_tool_execution,
    resolve_capability_policy,
)
from app.agents.clinic_grounding import (
    build_clinic_catalog,
    choice_snapshot_from_grounded_facts,
    grounded_catalog_facts,
)
from app.agents.flow_interpreter import FlowTurnDecision, interpret_active_flow_turn
from app.agents.grounded_response import compose_grounded_customer_reply
from app.agents.llm_runtime import LLMProviderError
from app.agents.response_guard import sanitize_customer_reply
from app.agents.semantic_actions import (
    booking_tool_args,
    format_booking_success,
    format_handoff_reply,
    format_verified_tool_fallback,
    reschedule_tool_args,
    select_slot_from_structured_selection,
)
from app.agents.semantic_router import (
    SemanticCapabilityDecision,
    route_customer_message,
)
from app.agents.tia_customer_agent import run_tia_customer_agent
from app.agents.tools.clinic_tools import AgentToolContext, build_clinic_tools
from app.agents.turn_interpreter import interpret_customer_turn
from app.core.config import settings
from app.models.agent_action import AgentAction
from app.models.appointment import Appointment
from app.models.conversation import Conversation
from app.models.conversation_flow_state import ConversationFlowState
from app.models.message import Message
from app.models.patient import Patient
from app.models.patient_package import PatientPackage
from app.models.workspace import Workspace
from app.schemas.agent import AgentChatRequest, AgentChatResponse
from app.services.conversation_flows import (
    FlowStateConflictError,
    cancel_flow,
    complete_flow,
    get_active_flow,
    interrupt_flow,
    record_write_authorized,
    record_write_completed,
    start_flow,
    sync_flow_from_agent_run,
    transition_flow,
)
from app.services.conversation_ownership import (
    OWNER_HUMAN,
    agent_can_reply,
    lock_conversation_ownership,
    record_customer_inbound,
    return_to_ai,
)
from app.services.handoff_intelligence import build_handoff_context
from app.services.handoffs import get_active_handoff
from app.services.patient_packages import (
    _package_financial_rows,
    list_patient_packages,
    reserve_package_usage,
    validate_package_for_booking,
)

logger = logging.getLogger(__name__)


class AgentChatError(ValueError):
    pass


def _workspace_clock(workspace: Workspace) -> tuple[str, datetime]:
    timezone_name = (workspace.timezone or "Africa/Cairo").strip()
    try:
        tz = ZoneInfo(timezone_name)
    except ZoneInfoNotFoundError:
        timezone_name = "Africa/Cairo"
        tz = ZoneInfo(timezone_name)
    return timezone_name, datetime.now(tz)

def _uuid_from_metadata(value: object) -> UUID | None:
    if value is None:
        return None
    try:
        return UUID(str(value))
    except (TypeError, ValueError):
        return None


def _existing_agent_response_for_inbound(
    db: Session,
    *,
    conversation: Conversation,
    inbound: Message,
    run_id: UUID,
) -> AgentChatResponse | None:
    """Recover a committed outbound response when event finalization is retried.
    `_run_after_inbound` commits the outbound message before the channel event is
    marked processed. If queue/event finalization fails afterwards, a retry must
    reuse that response instead of producing a second AI reply or replaying writes.
    """
    rows = list(
        db.scalars(
            select(Message)
            .where(
                Message.workspace_id == conversation.workspace_id,
                Message.conversation_id == conversation.id,
                Message.sender_type == "ai",
                Message.direction == "outbound",
            )
            .order_by(Message.created_at.desc())
            .limit(25)
        )
    )
    inbound_id = str(inbound.id)
    for outbound in rows:
        metadata = outbound.metadata_json or {}
        if str(metadata.get("in_reply_to_message_id") or "") != inbound_id:
            continue
        return AgentChatResponse(
            run_id=_uuid_from_metadata(metadata.get("agent_run_id")) or run_id,
            conversation_id=conversation.id,
            inbound_message_id=inbound.id,
            outbound_message_id=outbound.id,
            reply=outbound.content,
            handoff_required=conversation.owner_type == OWNER_HUMAN,
            agent_paused=False,
            model=metadata.get("model"),
        )
    return None

def _current_run_can_send_handoff_ack(
    db: Session,
    *,
    workspace_id: UUID,
    conversation_id: UUID,
    run_id: UUID,
    active_handoff: object | None,
) -> bool:
    """Allow one acknowledgement when this AI run itself transferred ownership.
    The final ownership guard must suppress stale AI replies after a staff takeover,
    but an AI-triggered handoff still needs to tell the customer that a team member
    will continue. Once a staff user has claimed the handoff, even that acknowledgement
    is suppressed to avoid racing a human reply.
    """
    if active_handoff is None:
        return False
    if getattr(active_handoff, "source", None) != "ai":
        return False
    if getattr(active_handoff, "status", None) != "pending":
        return False
    if getattr(active_handoff, "assigned_user_id", None) is not None:
        return False
    action_id = db.scalar(
        select(AgentAction.id)
        .where(
            AgentAction.workspace_id == workspace_id,
            AgentAction.conversation_id == conversation_id,
            AgentAction.run_id == run_id,
            AgentAction.tool_name == "escalate_to_human",
            AgentAction.status == "success",
        )
        .limit(1)
    )
    return action_id is not None

def _get_patient(db: Session, workspace_id: UUID, patient_id: UUID) -> Patient:
    patient = db.scalar(
        select(Patient).where(
            Patient.workspace_id == workspace_id,
            Patient.id == patient_id,
        )
    )
    if patient is None:
        raise AgentChatError("Patient not found in this workspace.")
    if patient.status == "blocked":
        raise AgentChatError("Blocked patients cannot use the automated customer agent.")
    return patient

def _get_or_create_conversation(
    db: Session,
    *,
    workspace: Workspace,
    patient: Patient,
    payload: AgentChatRequest,
    now: datetime,
) -> Conversation:
    if payload.conversation_id is not None:
        conversation = db.scalar(
            select(Conversation)
            .where(
                Conversation.workspace_id == workspace.id,
                Conversation.id == payload.conversation_id,
                Conversation.patient_id == patient.id,
            )
            .with_for_update()
        )
        if conversation is None:
            raise AgentChatError("Conversation not found for this patient.")
        if conversation.status == "closed":
            return_to_ai(conversation, now=datetime.now(UTC))
        return conversation
    conversation = Conversation(
        workspace_id=workspace.id,
        patient_id=patient.id,
        channel=payload.channel,
        status="open",
        owner_type="ai",
        unread_count=0,
        ownership_changed_at=now,
        started_at=now,
        last_message_at=now,
    )
    db.add(conversation)
    db.flush()
    return conversation

def _history_from_db(
    db: Session,
    conversation: Conversation,
    limit: int | None = None,
) -> list[BaseMessage]:
    limit = limit or settings.agent_history_messages
    rows = list(
        db.scalars(
            select(Message)
            .where(
                Message.workspace_id == conversation.workspace_id,
                Message.conversation_id == conversation.id,
                Message.content.is_not(None),
                Message.sender_type.in_(("patient", "ai", "staff")),
            )
            .order_by(Message.created_at.desc())
            .limit(limit)
        )
    )
    rows.reverse()
    history: list[BaseMessage] = []
    for row in rows:
        if not row.content:
            continue
        if row.sender_type == "patient":
            history.append(HumanMessage(content=row.content))
        else:
            history.append(AIMessage(content=row.content))
    return history

def _compact_context_value(
    value: object,
    *,
    list_limit: int = 5,
    depth: int = 0,
) -> object:
    if depth >= 5:
        if isinstance(value, (dict, list)):
            return "[truncated]"
        return value
    if isinstance(value, dict):
        result: dict[str, object] = {}
        for key, item in value.items():
            if key in {"slots", "appointments", "branches", "services", "doctors"} and isinstance(
                item, list
            ):
                result[key] = [
                    _compact_context_value(child, list_limit=list_limit, depth=depth + 1)
                    for child in item[:list_limit]
                ]
            else:
                result[key] = _compact_context_value(
                    item,
                    list_limit=list_limit,
                    depth=depth + 1,
                )
        return result
    if isinstance(value, list):
        return [
            _compact_context_value(child, list_limit=list_limit, depth=depth + 1)
            for child in value[:list_limit]
        ]

    if isinstance(value, str) and len(value) > 1200:
        return value[:1200] + "…"
    return value

def _recent_operational_context(
    db: Session,
    conversation: Conversation,
    flow: ConversationFlowState | None,
) -> str | None:
    context: dict[str, object] = {}
    if flow is not None:
        context["workflow"] = {
            "flow_type": flow.flow_type,
            "status": flow.status,
            "capabilities": flow.capabilities,
            "entity_state": _compact_context_value(flow.entity_state),
            "missing_information": flow.missing_information,
            "option_snapshot": _compact_context_value(flow.option_snapshot),
            "version": flow.version,
        }
    rows = list(
        db.scalars(
            select(AgentAction)
            .where(
                AgentAction.workspace_id == conversation.workspace_id,
                AgentAction.conversation_id == conversation.id,
                AgentAction.status == "success",
                AgentAction.tool_name.in_(
                    (
                        "get_booking_options",
                        "get_reschedule_options",
                        "get_customer_appointments",
                    )
                ),
            )
            .order_by(AgentAction.created_at.desc())
            .limit(max(settings.agent_operational_context_items * 2, 4))
        )
    )
    latest: dict[str, object] = {}
    for row in rows:
        if row.tool_name in latest:
            continue
        latest[row.tool_name] = {
            "input": _compact_context_value(row.input_json),
            "output": _compact_context_value(row.output_json),
        }
        if len(latest) >= settings.agent_operational_context_items:
            break
    if latest:
        context["recent_tools"] = latest

    if not context:
        return None
    encoded = json.dumps(
        context,
        ensure_ascii=False,
        default=str,
        separators=(",", ":"),
    )
    return encoded[: settings.agent_operational_context_max_chars]

def _invoke_tool(
    *,
    tool_context: AgentToolContext,
    tool_name: str,
    arguments: dict,
) -> dict | None:
    tool = next(item for item in build_clinic_tools(tool_context) if item.name == tool_name)
    raw = tool.invoke(arguments)
    try:
        value = json.loads(raw)
    except (TypeError, json.JSONDecodeError):
        return None
    return value if isinstance(value, dict) else None


def _invoke_authorized_tool(
    *,
    tool_context: AgentToolContext,
    policy: CapabilityPolicyDecision,
    tool_name: str,
    arguments: dict,
) -> dict | None:
    authorize_tool_execution(policy, tool_name)
    return _invoke_tool(
        tool_context=tool_context,
        tool_name=tool_name,
        arguments=arguments,
    )

def _merge_flow_entity_state(
    existing_state: dict | None,
    turn: FlowTurnDecision,
) -> dict[str, object]:
    """Merge one semantic flow turn without resurrecting relaxed requirements.
    FlowTurnDecision.clear_entity_fields is produced by the flow interpreter from
    conversational meaning. It lets a follow-up such as broadening availability
    remove a previously persisted time constraint without relying on keywords.
    Null hints alone do not clear state because a customer is not required to repeat
    every known booking requirement on every turn.
    """
    merged: dict[str, object] = dict(existing_state or {})
    clear_fields = set(turn.clear_entity_fields)
    for field_name in clear_fields:
        merged.pop(field_name, None)
    time_fields = {"requested_start_time", "not_before_time", "not_after_time"}
    hints = turn.entity_hints.model_dump(mode="json")
    time_changed = bool(clear_fields.intersection(time_fields)) or any(
        hints.get(field_name) is not None for field_name in time_fields
    )
    if time_changed:
        # requested_time_window is derived from the previous discovery result. If
        # semantic time requirements changed, keeping this nested copy would make
        # prefetch silently restore a stale bound on the next read.
        merged.pop("requested_time_window", None)
    # Exact starts and broad windows are mutually exclusive structured semantics.
    # Keep the persisted state normalized even if an older turn encoded an exact
    # time as equal lower/upper bounds.
    if hints.get("requested_start_time") is not None:
        merged.pop("not_before_time", None)
        merged.pop("not_after_time", None)
    elif hints.get("not_before_time") is not None or hints.get("not_after_time") is not None:
        merged.pop("requested_start_time", None)
    candidate_list_fields = {
        "service_candidate_ids",
        "branch_candidate_ids",
        "doctor_candidate_ids",
    }
    for field_name, value in hints.items():
        if value is None:
            continue
        # Empty candidate lists are schema defaults, not semantic instructions.
        # Persisting them would mutate otherwise-unchanged conversation state and
        # can erase the distinction between "not mentioned this turn" and
        # "explicitly cleared". Clearing remains exclusively driven by
        # clear_entity_fields from the LLM.
        if field_name in candidate_list_fields and not value:
            continue
        merged[field_name] = value
    # Canonical IDs and candidate sets are mutually exclusive grounding states.
    # If the LLM selected one verified catalog ID, discard any stale ambiguity
    # candidates. If it returned multiple verified candidates, discard a stale
    # canonical selection so the customer can choose safely.
    for entity_name in ("service", "branch", "doctor"):
        selected_key = f"{entity_name}_id"
        candidates_key = f"{entity_name}_candidate_ids"
        selected_value = hints.get(selected_key)
        candidates_value = hints.get(candidates_key)
        if selected_value:
            merged.pop(candidates_key, None)
        elif candidates_value:
            merged.pop(selected_key, None)
    return merged


def _customer_package_payload(
    *,
    db: Session,
    workspace_id: UUID,
    patient_id: UUID,
    service_id: str = "",
) -> dict[str, object]:
    service_uuid = _uuid_from_metadata(service_id) if service_id else None
    packages = list_patient_packages(
        db,
        workspace_id=workspace_id,
        patient_id=patient_id,
        service_id=service_uuid,
        usable_only=False,
    )
    rows = [item.model_dump(mode="json") for item in packages]
    usable = [
        row
        for row in rows
        if row.get("effective_status") == "active"
        and int(row.get("sessions_remaining") or 0) > 0
    ]
    return {"ok": True, "packages": rows, "usable_packages": usable}


def _package_refund_quote_payload(
    *,
    db: Session,
    workspace_id: UUID,
    patient_id: UUID,
    service_id: str = "",
) -> dict[str, object]:
    package_data = _customer_package_payload(
        db=db,
        workspace_id=workspace_id,
        patient_id=patient_id,
        service_id=service_id,
    )
    packages = list(package_data.get("packages") or [])
    candidates = [
        row
        for row in packages
        if isinstance(row, dict)
        and row.get("effective_status") in {"active", "exhausted"}
    ]
    if not candidates:
        return {"ok": True, "packages": packages, "quote": None, "reason": "no_active_package"}
    if len(candidates) > 1:
        return {
            "ok": True,
            "packages": candidates,
            "quote": None,
            "needs_package_choice": True,
        }

    selected = candidates[0]
    package_id = _uuid_from_metadata(selected.get("id"))
    if package_id is None:
        return {"ok": False, "reason": "invalid_package_id"}
    package = db.scalar(
        select(PatientPackage).where(
            PatientPackage.workspace_id == workspace_id,
            PatientPackage.patient_id == patient_id,
            PatientPackage.id == package_id,
        )
    )
    if package is None:
        return {"ok": False, "reason": "package_not_found"}

    consumed = int(selected.get("sessions_consumed") or 0)
    if package.opening_sessions_remaining is not None:
        if not package.sessions_total_known:
            return {
                "ok": False,
                "reason": "package_total_unknown",
                "message": "A safe refund quote cannot be calculated for this migrated package.",
            }
        consumed += max(
            0,
            int(package.sessions_purchased) - int(package.opening_sessions_remaining),
        )

    unit_price = package.standalone_session_price_minor_at_purchase
    if unit_price is None and consumed > 0:
        return {
            "ok": False,
            "reason": "standalone_price_missing",
            "message": "Standalone session price at purchase is required for a safe refund quote.",
        }

    payments, refunds = _package_financial_rows(
        db, workspace_id=workspace_id, package=package, for_update=False
    )
    collected_minor = sum(int(row.amount_minor) for row in payments)
    previously_refunded_minor = sum(int(row.amount_minor) for row in refunds)
    consumed_value_minor = consumed * int(unit_price or 0)
    refundable_minor = max(
        collected_minor - consumed_value_minor - previously_refunded_minor,
        0,
    )
    return {
        "ok": True,
        "packages": [selected],
        "quote": {
            "package_id": str(package.id),
            "package_name": package.name,
            "currency": package.currency,
            "consumed_sessions": consumed,
            "standalone_session_price_minor": int(unit_price or 0),
            "collected_minor": collected_minor,
            "consumed_value_minor": consumed_value_minor,
            "previously_refunded_minor": previously_refunded_minor,
            "refundable_minor": refundable_minor,
        },
    }




def _verified_package_refund_reply(payload: dict[str, object]) -> str | None:
    """Format a read-only package refund quote directly from verified DB facts."""
    if payload.get("ok") is not True:
        return None

    quote = payload.get("quote")
    if not isinstance(quote, dict):
        reason = str(payload.get("reason") or "")
        if reason == "no_active_package":
            return "مش لاقي باكدج نشطة للخدمة دي حالياً عشان أحسب مبلغ الاسترداد."
        return None

    refundable_minor = quote.get("refundable_minor")
    standalone_minor = quote.get("standalone_session_price_minor")
    consumed_sessions = quote.get("consumed_sessions")
    currency = str(quote.get("currency") or "EGP")

    try:
        refundable_minor = int(refundable_minor)
        standalone_minor = int(standalone_minor)
        consumed_sessions = int(consumed_sessions)
    except (TypeError, ValueError):
        return None

    def money(minor: int) -> str:
        major = minor / 100
        if major.is_integer():
            return f"{int(major):,}"
        return f"{major:,.2f}"

    currency_label = "جنيه" if currency.upper() == "EGP" else currency
    reply = (
        f"لو لغيت الباكدج دلوقتي، المبلغ المتوقع يرجعلك "
        f"{money(refundable_minor)} {currency_label}."
    )
    if consumed_sessions > 0:
        session_word = "جلسة" if consumed_sessions == 1 else "جلسات"
        reply += (
            f" الحساب خصم {consumed_sessions} {session_word} مستخدمة "
            f"بسعر الجلسة العادية {money(standalone_minor)} {currency_label} للجلسة."
        )
    return reply

def _package_intent_non_booking(decision: SemanticCapabilityDecision) -> SemanticCapabilityDecision:
    """Normalize structured package semantics before capability policy."""
    intent = str(decision.package_intent)
    if intent not in {"purchase", "inquire"}:
        return decision
    blocked = {"availability_discovery", "appointment_creation", "doctor_discovery", "branch_discovery"}
    if intent == "purchase":
        blocked.add("pricing")
    capabilities = [capability for capability in decision.capabilities if str(capability) not in blocked]
    if "package_information" not in capabilities:
        capabilities.append("package_information")
    return decision.model_copy(update={"capabilities": capabilities, "flow_signal": "none"})


def _with_implicit_primary_branch(
    decision: SemanticCapabilityDecision,
    *,
    workspace: Workspace,
    clinic_catalog: dict[str, object],
) -> SemanticCapabilityDecision:
    if workspace.primary_branch_id is None or decision.entity_hints.branch_id:
        return decision
    primary_id = str(workspace.primary_branch_id)
    branch_name: str | None = None
    branches = clinic_catalog.get("branches")
    if isinstance(branches, list):
        for branch in branches:
            if not isinstance(branch, dict) or str(branch.get("id") or "") != primary_id:
                continue
            candidate = branch.get("name") or branch.get("branch_name")
            if isinstance(candidate, str) and candidate.strip():
                branch_name = candidate.strip()
            break
    hints = decision.entity_hints.model_copy(update={
        "branch_id": primary_id,
        "branch_candidate_ids": [],
        **({"branch_query": branch_name} if branch_name else {}),
    })
    return decision.model_copy(update={"entity_hints": hints})


def _verified_package_intent_reply(
    *,
    intent: str,
    package_payload: dict[str, object] | None,
    catalog_payload: dict[str, object] | None = None,
) -> str | None:
    if intent not in {"purchase", "inquire"}:
        return None
    usable: list[dict[str, object]] = []
    if isinstance(package_payload, dict):
        raw = package_payload.get("usable_packages")
        if isinstance(raw, list):
            usable = [item for item in raw if isinstance(item, dict)]
    service_name: str | None = None
    standalone_price: str | None = None
    if isinstance(catalog_payload, dict):
        services = catalog_payload.get("services")
        if isinstance(services, list) and len(services) == 1 and isinstance(services[0], dict):
            service = services[0]
            raw_name = service.get("name")
            raw_price = service.get("price")
            if isinstance(raw_name, str) and raw_name.strip():
                service_name = raw_name.strip()
            if isinstance(raw_price, str) and raw_price.strip():
                standalone_price = raw_price.strip()
                if standalone_price.endswith(" EGP"):
                    standalone_price = standalone_price[:-4] + " جنيه"

    if intent == "purchase":
        if usable:
            current = usable[0]
            remaining = int(current.get("sessions_remaining") or 0)
            name = str(current.get("name") or "الباكدج الحالية")
            return f"عندك {name} لنفس الخدمة شغالة حالياً وفاضلك {remaining} جلسات. استخدم الجلسات المتبقية فيها الأول قبل بدء باكدج جديدة لنفس الخدمة."
        return (
            "فهمت إنك عايز باكدج، مش جلسة واحدة، فمش هاحجز جلسة عادية بدلها. "
            "تفاصيل الباكدجات الجديدة من عدد الجلسات والسعر لازم تكون مسجلة كعرض باكدج "
            "موثوق في إعدادات العيادة قبل ما أقدر أأكد الاشتراك أو سعره."
        )
    if usable:
        current = usable[0]
        remaining = int(current.get("sessions_remaining") or 0)
        name = str(current.get("name") or "الباكدج الحالية")
        return f"عندك {name} شغالة حالياً وفاضلك {remaining} جلسات."
    if service_name and standalone_price:
        return (
            f"لو بتقارن بين جلسة واحدة وباكدج: جلسة {service_name} العادية سعرها "
            f"{standalone_price}. أما تفاصيل الباكدجات الجديدة من عدد الجلسات والسعر "
            "فمش مسجلة عندي كعرض موثوق حالياً، فمش هافترض تفاصيل مش موجودة."
        )
    return (
        "لو بتقارن بين جلسة واحدة وباكدج، تفاصيل الباكدجات الجديدة من عدد الجلسات والسعر "
        "مش مسجلة عندي كعرض موثوق حالياً، فمش هافترض تفاصيل مش موجودة."
    )


def _booking_package_requirement_reply(
    *, db: Session, workspace_id: UUID, patient_id: UUID, service_id: UUID | None,
    start_at: datetime | None, package_intent: str,
) -> str | None:
    if package_intent != "use_existing":
        return None
    if service_id is None:
        return "محتاج أحدد الخدمة الأول عشان أتأكد إن عندك باكدج نشطة ليها قبل الحجز."
    usable = list_patient_packages(
        db, workspace_id=workspace_id, patient_id=patient_id, service_id=service_id,
        usable_only=True, on_date=start_at.date() if start_at is not None else None,
    )
    if len(usable) != 1:
        return "مش لاقي باكدج نشطة لنفس الخدمة أقدر أحجز منها، فمش هحوّل الطلب تلقائياً لحجز عادي مدفوع."
    if start_at is not None:
        try:
            validate_package_for_booking(
                db, workspace_id=workspace_id, package_id=usable[0].id, patient_id=patient_id,
                service_id=service_id, appointment_start_at=start_at, sessions=1,
            )
        except ValueError:
            return "الباكدج الموجودة مش صالحة للميعاد المطلوب، فمش هحوّل الطلب لحجز عادي من غير موافقتك."
    return None


def _package_booking_success_reply(appointment_payload: dict[str, object], package_result: dict[str, object] | None) -> str:
    reply = format_booking_success(appointment_payload)
    if not package_result:
        return reply
    remaining = int(package_result.get("sessions_remaining") or 0)
    return f"{reply} الحجز اتحسب من الباكدج، وفاضلك {remaining} جلسات فيها."


def _apply_single_matching_package_to_booking(
    *,
    db: Session,
    workspace_id: UUID,
    patient_id: UUID,
    appointment_payload: dict[str, object],
) -> dict[str, object] | None:
    """Reserve one session from the customer's only usable same-service package.

    Package selection is deterministic domain logic, not an LLM decision: each
    package belongs to one service, and the product allows at most one usable
    package for that patient/service at a time.
    """
    appointment_id = _uuid_from_metadata(
        appointment_payload.get("appointment_id") or appointment_payload.get("id")
    )
    if appointment_id is None:
        return None

    appointment = db.scalar(
        select(Appointment).where(
            Appointment.workspace_id == workspace_id,
            Appointment.patient_id == patient_id,
            Appointment.id == appointment_id,
        )
    )
    if appointment is None or appointment.patient_package_id is not None:
        return None

    usable = list_patient_packages(
        db,
        workspace_id=workspace_id,
        patient_id=patient_id,
        service_id=appointment.service_id,
        usable_only=True,
        on_date=appointment.start_at.date(),
    )
    if len(usable) != 1:
        return None

    package = validate_package_for_booking(
        db,
        workspace_id=workspace_id,
        package_id=usable[0].id,
        patient_id=patient_id,
        service_id=appointment.service_id,
        appointment_start_at=appointment.start_at,
        sessions=1,
    )
    reserve_package_usage(
        db,
        appointment=appointment,
        package=package,
        sessions=1,
    )
    db.flush()

    # Keep the deterministic success payload aligned with the persisted booking.
    appointment_payload["patient_package_id"] = str(package.id)
    appointment_payload["billing_context"] = appointment.billing_context
    appointment_payload["payment_status"] = appointment.payment_status
    appointment_payload["package_external_id"] = appointment.package_external_id

    refreshed = list_patient_packages(
        db, workspace_id=workspace_id, patient_id=patient_id,
        service_id=appointment.service_id, usable_only=False,
    )
    package_summary = next((item for item in refreshed if item.id == package.id), None)
    return {
        "package_id": str(package.id),
        "package_name": package.name,
        "sessions_remaining": int(package_summary.sessions_remaining if package_summary is not None else 0),
    }

def _prefetch_read_tools(
    *,
    tool_context: AgentToolContext,
    policy: CapabilityPolicyDecision,
    decision: SemanticCapabilityDecision,
    flow: ConversationFlowState | None,
    use_flow_state: bool = True,
    grounded_mode: bool = False,
) -> tuple[dict[str, object], set[str]]:
    """Execute safe read tools deterministically from semantic state.
    The semantic router/flow interpreter has already decided the capabilities.
    For common read-heavy turns we can fetch PostgreSQL source-of-truth data
    directly instead of spending an extra LLM round asking the agent which read
    tool to call. No write tool is ever prefetched here.
    """
    if not settings.agent_prefetch_reads_enabled or policy.requires_human:
        return {}, set()
    state: dict[str, object] = {}
    if use_flow_state and flow is not None and isinstance(flow.entity_state, dict):
        state.update(flow.entity_state)
    state.update(decision.entity_hints.model_dump(mode="json", exclude_none=True))

    def text_value(key: str) -> str:
        value = state.get(key)
        return value.strip() if isinstance(value, str) else ""
    service_query = text_value("service_query")
    branch_query = text_value("branch_query")
    doctor_query = text_value("doctor_query")
    service_id = text_value("service_id")
    branch_id = text_value("branch_id")
    doctor_id = text_value("doctor_id")
    requested_date = text_value("requested_date") or text_value("date")
    requested_start_time = text_value("requested_start_time")
    not_before_time = text_value("not_before_time")
    not_after_time = text_value("not_after_time")
    window = state.get("requested_time_window")
    if isinstance(window, dict):
        if not not_before_time and isinstance(window.get("not_before_time"), str):
            not_before_time = str(window["not_before_time"])
        if not not_after_time and isinstance(window.get("not_after_time"), str):
            not_after_time = str(window["not_after_time"])
    # Backward compatibility for persisted v0.18/v0.19-experimental flows where
    # one exact clock time was represented as a zero-width window. The new tool
    # contract keeps exact starts separate so appointment duration is not compared
    # against a zero-length range.
    if (
        not requested_start_time
        and not_before_time
        and not_after_time
        and not_before_time == not_after_time
    ):
        requested_start_time = not_before_time
        not_before_time = ""
        not_after_time = ""
    service_state = state.get("service")
    if isinstance(service_state, dict):
        if not service_id and isinstance(service_state.get("service_id"), str):
            service_id = str(service_state["service_id"]).strip()
        if not service_query:
            candidate = service_state.get("service_name") or service_state.get("name")
            if isinstance(candidate, str):
                service_query = candidate.strip()
    branch_state = state.get("branch")
    if isinstance(branch_state, dict):
        if not branch_id and isinstance(branch_state.get("branch_id"), str):
            branch_id = str(branch_state["branch_id"]).strip()
        if not branch_query:
            candidate = branch_state.get("branch_name") or branch_state.get("name")
            if isinstance(candidate, str):
                branch_query = candidate.strip()
    doctor_state = state.get("doctor")
    if isinstance(doctor_state, dict) and not doctor_id and isinstance(doctor_state.get("doctor_id"), str):
        doctor_id = str(doctor_state["doctor_id"]).strip()

    results: dict[str, object] = {}
    prefetched: set[str] = set()
    reusable_reads = (
        "get_booking_options",
        "get_reschedule_options",
        "search_services",
        "list_branches",
        "list_doctors",
        "get_available_slots",
        "get_customer_appointments",
        "get_customer_profile",
        "get_customer_history",
    )
    existing_actions: list[AgentAction] = []
    if all(
        getattr(tool_context, attribute, None) is not None
        for attribute in ("db", "workspace", "conversation", "run_id")
    ):
        existing_actions = list(
            tool_context.db.scalars(
                select(AgentAction)
                .where(
                    AgentAction.workspace_id == tool_context.workspace.id,
                    AgentAction.conversation_id == tool_context.conversation.id,
                    AgentAction.run_id == tool_context.run_id,
                    AgentAction.status == "success",
                    AgentAction.tool_name.in_(reusable_reads),
                )
                .order_by(AgentAction.created_at.desc())
            )
        )
    for action in existing_actions:
        if action.tool_name in prefetched or not isinstance(action.output_json, dict):
            continue
        prefetched.add(action.tool_name)
        results[action.tool_name] = _compact_context_value(action.output_json)
        logger.info(
            "Tia turn run_id=%s stage=prefetch-reuse tool=%s",
            tool_context.run_id,
            action.tool_name,
        )
    def run(tool_name: str, arguments: dict) -> dict | None:
        if tool_name not in policy.allowed_tools or tool_name in prefetched:
            return None
        stage_started = perf_counter()
        result = _invoke_authorized_tool(
            tool_context=tool_context,
            policy=policy,
            tool_name=tool_name,
            arguments=arguments,
        )
        prefetched.add(tool_name)
        if result is not None:
            results[tool_name] = _compact_context_value(result)
        logger.info(
            "Tia turn run_id=%s stage=prefetch tool=%s duration_ms=%s ok=%s",
            tool_context.run_id,
            tool_name,
            int((perf_counter() - stage_started) * 1000),
            bool(result and result.get("ok") is True),
        )
        return result
    capabilities = set(policy.capabilities)

    booking_prefetched = "get_booking_options" in prefetched
    booking_result = results.get("get_booking_options")
    if (
        not grounded_mode
        and isinstance(booking_result, dict)
        and booking_result.get("ok") is True
    ):
        prefetched.update(
            tool_name
            for tool_name in ("search_services", "list_branches", "list_doctors")
            if tool_name in policy.allowed_tools
        )
    if grounded_mode:
        can_prefetch_booking = bool(
            service_id
            and requested_date
            and (not branch_query or branch_id)
            and (not doctor_query or doctor_id)
        )
    else:
        can_prefetch_booking = bool(service_query and requested_date)
    if (
        not booking_prefetched
        and capabilities.intersection({"availability_discovery", "appointment_creation"})
        and can_prefetch_booking
    ):
        booking_arguments = {
            "booking_date": requested_date,
            "requested_start_time": requested_start_time,
            "not_before_time": not_before_time,
            "not_after_time": not_after_time,
        }
        if grounded_mode:
            booking_arguments.update(
                {
                    "service_id": service_id,
                    "branch_id": branch_id,
                    "doctor_id": doctor_id,
                }
            )
        else:
            booking_arguments.update(
                {
                    "service_search": service_query,
                    "branch_search": branch_query,
                    "doctor_search": doctor_query,
                }
            )
        booking = run("get_booking_options", booking_arguments)
        booking_prefetched = booking is not None
        if booking and booking.get("ok") is True and not grounded_mode:
            # Legacy rollback path: a successful composite booking read covers
            # lower-level discovery reads. In grounded mode canonical IDs have
            # already been selected by the LLM from the PostgreSQL catalog, so
            # get_booking_options is the only read executed/prefetched here.
            prefetched.update(
                tool_name
                for tool_name in ("search_services", "list_branches", "list_doctors")
                if tool_name in policy.allowed_tools
            )
    if (
        not booking_prefetched
        and grounded_mode
        and "availability_discovery" in capabilities
        and service_id
        and not requested_date
        and (not branch_query or branch_id)
        and (not doctor_query or doctor_id)
    ):
        _timezone_name, local_now = _workspace_clock(tool_context.workspace)
        horizon_days = max(1, int(getattr(settings, "booking_horizon_days", 60)))
        first_date = local_now.date()
        last_checked = first_date
        selected_result: dict | None = None
        for offset in range(horizon_days + 1):
            candidate_date = first_date + timedelta(days=offset)
            last_checked = candidate_date
            arguments = {
                "booking_date": candidate_date.isoformat(),
                "service_id": service_id,
                "branch_id": branch_id,
                "doctor_id": doctor_id,
                "requested_start_time": requested_start_time,
                "not_before_time": not_before_time,
                "not_after_time": not_after_time,
            }
            result = _invoke_authorized_tool(
                tool_context=tool_context,
                policy=policy,
                tool_name="get_booking_options",
                arguments=arguments,
            )
            if not isinstance(result, dict):
                continue
            if result.get("ok") is not True:
                selected_result = result
                break
            if any(
                bool(result.get(key))
                for key in ("needs_service_choice", "needs_branch_choice", "needs_doctor_choice")
            ):
                selected_result = result
                break
            slots = result.get("slots")
            if isinstance(slots, list) and slots:
                selected_result = dict(result)
                selected_result["next_available_search"] = {
                    "from_date": first_date.isoformat(),
                    "matched_date": candidate_date.isoformat(),
                    "days_scanned": offset + 1,
                }
                break
        if selected_result is None:
            selected_result = {
                "ok": True,
                "slots": [],
                "next_available_search": {
                    "from_date": first_date.isoformat(),
                    "through_date": last_checked.isoformat(),
                    "days_scanned": horizon_days + 1,
                },
            }
        results["get_booking_options"] = _compact_context_value(selected_result)
        results["get_next_available_options"] = _compact_context_value(selected_result)
        prefetched.add("get_booking_options")
        booking_prefetched = True

    if "appointment_reschedule" in capabilities and requested_date:
        reschedule_arguments = {
            "booking_date": requested_date,
            "requested_start_time": requested_start_time,
            "not_before_time": not_before_time,
            "not_after_time": not_after_time,
        }
        if grounded_mode:
            reschedule_arguments["service_id"] = service_id
        else:
            reschedule_arguments["service_search"] = service_query
        run("get_reschedule_options", reschedule_arguments)
    if (
        not grounded_mode
        and {"service_information", "pricing"}.intersection(capabilities)
        and not booking_prefetched
    ):
        run("search_services", {"search": service_query})

    if not grounded_mode and "branch_discovery" in capabilities and not booking_prefetched:
        run("list_branches", {})
    if not grounded_mode and "doctor_discovery" in capabilities:
        # When the request is unfiltered, listing doctors is a direct read. If
        # the user named a service/branch, keep the tool available to the agent
        # because resolving those names to internal IDs is a dependent lookup.
        if not service_query and not branch_query:
            run("list_doctors", {})
    if capabilities.intersection(
        {"appointment_list", "appointment_confirmation", "appointment_cancellation"}
    ):
        run("get_customer_appointments", {"include_past": False})

    if "customer_profile" in capabilities:
        run("get_customer_profile", {})

    if "customer_history" in capabilities:
        run("get_customer_history", {"recent_limit": 20})

    if capabilities.intersection({"package_information", "package_refund_quote"}):
        package_payload = _customer_package_payload(
            db=tool_context.db,
            workspace_id=tool_context.workspace.id,
            patient_id=tool_context.patient.id,
            service_id=service_id,
        )
        results["customer_packages"] = package_payload
        prefetched.add("customer_packages")
        if "package_refund_quote" in capabilities:
            quote_payload = _package_refund_quote_payload(
                db=tool_context.db,
                workspace_id=tool_context.workspace.id,
                patient_id=tool_context.patient.id,
                service_id=service_id,
            )
            results["package_refund_quote"] = quote_payload
            prefetched.add("package_refund_quote")

    return results, prefetched

_DIRECT_COMPOSITE_CAPABILITIES: dict[str, frozenset[str]] = {
    "get_booking_options": frozenset(
        {"availability_discovery", "appointment_creation"}
    ),
    "get_reschedule_options": frozenset({"appointment_reschedule"}),
}
_GROUNDED_RESPONSE_CAPABILITIES = frozenset(
    {
        "service_information",
        "pricing",
        "branch_discovery",
        "doctor_discovery",
        "availability_discovery",
        "appointment_creation",
        "appointment_list",
        "appointment_reschedule",
        "customer_profile",
        "customer_history",
        "package_information",
        "package_refund_quote",
    }
)
_GROUNDED_RESPONSE_EVIDENCE: dict[str, frozenset[str]] = {
    "service_information": frozenset({"clinic_catalog"}),
    "pricing": frozenset({"clinic_catalog"}),
    "branch_discovery": frozenset({"clinic_catalog"}),
    "doctor_discovery": frozenset({"clinic_catalog"}),
    "availability_discovery": frozenset({"get_booking_options"}),
    "appointment_creation": frozenset({"get_booking_options"}),
    "appointment_list": frozenset({"get_customer_appointments"}),
    "appointment_reschedule": frozenset({"get_reschedule_options"}),
    "customer_profile": frozenset({"get_customer_profile"}),
    "customer_history": frozenset({"get_customer_history"}),
    "package_information": frozenset({"customer_packages"}),
    "package_refund_quote": frozenset({"package_refund_quote"}),
}

def _grounded_response_can_cover(
    policy: CapabilityPolicyDecision,
    verified_data: dict[str, object],
) -> bool:
    if policy.requires_human or not verified_data:
        return False
    capabilities = set(policy.capabilities)
    if not capabilities or not capabilities.issubset(_GROUNDED_RESPONSE_CAPABILITIES):
        return False
    verified_sources = {
        source
        for source, payload in verified_data.items()
        if isinstance(payload, dict) and payload.get("ok") is True
    }
    return all(
        bool(_GROUNDED_RESPONSE_EVIDENCE[capability].intersection(verified_sources))
        for capability in capabilities
    )



def _verified_booking_slots_reply(
    payload: dict[str, object],
    *,
    booking_authorized: bool,
) -> str | None:
    """Present adapter-verified availability as natural free-time windows."""
    if payload.get("ok") is False:
        return None
    if any(
        bool(payload.get(key))
        for key in (
            "needs_service_choice",
            "needs_branch_choice",
            "needs_doctor_choice",
            "needs_appointment_choice",
        )
    ):
        return None
    return format_availability_windows_reply(
        payload,
        booking_authorized=booking_authorized,
    )

def _exact_action_selection_index(
    *,
    decision: SemanticCapabilityDecision,
    payload: dict[str, object],
    required_capability: str,
) -> int | None:
    """Return one verified slot index for one semantically authorized exact-time action.

    The interpreter owns intent; Python only verifies that the exact structured
    clock time maps to exactly one adapter slot before a write can execute.
    """
    if required_capability not in set(decision.capabilities):
        return None
    requested_date = decision.entity_hints.requested_date
    requested_time = decision.entity_hints.requested_start_time
    if not requested_date or not requested_time:
        return None
    if payload.get("ok") is False:
        return None
    if any(
        bool(payload.get(key))
        for key in (
            "needs_service_choice",
            "needs_branch_choice",
            "needs_doctor_choice",
            "needs_appointment_choice",
        )
    ):
        return None
    slots = payload.get("slots")
    if not isinstance(slots, list) or not slots:
        return None

    requested_hhmm = str(requested_time).strip()[:5]
    matches: list[int] = []
    for index, slot in enumerate(slots, start=1):
        if not isinstance(slot, dict):
            continue
        slot_time = slot.get("start_time_24h")
        if not isinstance(slot_time, str) or not slot_time.strip():
            start_local = slot.get("start_local")
            if isinstance(start_local, str):
                try:
                    slot_time = datetime.fromisoformat(start_local).strftime("%H:%M")
                except ValueError:
                    slot_time = None
        if isinstance(slot_time, str) and slot_time.strip()[:5] == requested_hhmm:
            matches.append(index)
    return matches[0] if len(matches) == 1 else None


def _exact_action_flow_turn(
    decision: SemanticCapabilityDecision,
    *,
    selection_index: int,
) -> FlowTurnDecision:
    """Convert an already-structured exact appointment action into a verified slot choice."""
    return FlowTurnDecision(
        action="select_option",
        capabilities=list(decision.capabilities),
        risk_flags=list(decision.risk_flags),
        package_intent=decision.package_intent,
        entity_hints=decision.entity_hints,
        clear_entity_fields=[],
        selection_index=selection_index,
        selection_time=None,
        missing_information=list(decision.missing_information),
        recommended_handoff_category=decision.recommended_handoff_category,
        recommended_handoff_priority=decision.recommended_handoff_priority,
        confidence=decision.confidence,
        reason=(
            "The current turn semantically authorizes an appointment action at an exact "
            "date/time and exactly one verified adapter slot matches it."
        ),
    )

def _verified_prefetch_direct_reply(
    *,
    policy: CapabilityPolicyDecision,
    prefetched_results: dict[str, object],
) -> tuple[str, str] | None:
    """Return a fast customer-safe reply for fully covered composite reads.
    Semantic routing has already happened before this point. This function never
    inspects customer wording and never authorizes a write; it only formats a
    verified PostgreSQL composite-read result when that result covers every
    capability in the current turn.
    """
    if policy.requires_human:
        return None
    capabilities = set(policy.capabilities)
    for tool_name, covered_capabilities in _DIRECT_COMPOSITE_CAPABILITIES.items():
        if not capabilities or not capabilities.issubset(covered_capabilities):
            continue
        payload = prefetched_results.get(tool_name)
        if not isinstance(payload, dict):
            continue
        reply = format_verified_tool_fallback(tool_name, payload)
        if reply:
            return reply, f"deterministic:verified-{tool_name}"
    return None

def _sync_flow_from_verified_prefetch(
    *,
    db: Session,
    flow: ConversationFlowState | None,
    prefetched_results: dict[str, object],
    run_id: UUID,
) -> ConversationFlowState | None:
    """Sync a read-only flow directly from the verified in-memory tool result.
    The tool already persisted its AgentAction before returning. Querying that same
    action twice again (discovery + write) adds remote-DB round trips but no new
    information on the grounded prefetch-direct path. Writes still use the existing
    sync_flow_from_agent_run path.
    """
    if flow is None or not flow.is_active:
        return flow
    if flow.flow_type == "booking":
        tool_name = "get_booking_options"
    elif flow.flow_type == "appointment_reschedule":
        tool_name = "get_reschedule_options"
    else:
        return flow

    output = prefetched_results.get(tool_name)
    if not isinstance(output, dict):
        return flow
    slots = output.get("slots")
    has_slots = isinstance(slots, list) and bool(slots)
    needs_choice = any(
        bool(output.get(key))
        for key in (
            "needs_service_choice",
            "needs_branch_choice",
            "needs_doctor_choice",
            "needs_appointment_choice",
        )
    )
    status = (
        "awaiting_option_selection"
        if has_slots and not needs_choice
        else "collecting_requirements"
    )
    entity_state = dict(flow.entity_state or {})
    for key in ("service", "branch", "current_appointment", "date", "requested_time_window"):
        if key in output:
            entity_state[key] = output[key]
    package_payload = prefetched_results.get("customer_packages")
    if isinstance(package_payload, dict):
        usable_packages = package_payload.get("usable_packages")
        if isinstance(usable_packages, list) and len(usable_packages) == 1:
            selected_package = usable_packages[0]
            if isinstance(selected_package, dict) and selected_package.get("id"):
                entity_state["patient_package_id"] = str(selected_package["id"])

    return transition_flow(
        db,
        flow,
        actor_type="agent",
        event_type="options_presented" if has_slots else "updated",
        run_id=run_id,
        status=status,
        option_snapshot=output if has_slots else {},
        entity_state=entity_state,
    )

def _decision_payload(decision: SemanticCapabilityDecision) -> dict:
    return decision.model_dump(mode="json")


def _latest_customer_text(history: list[BaseMessage]) -> str | None:
    for message in reversed(history):
        if isinstance(message, HumanMessage) and isinstance(message.content, str):
            text = message.content.strip()
            if text:
                return text
    return None

def _handoff_context_for_turn(
    *,
    decision: SemanticCapabilityDecision,
    flow: ConversationFlowState | None,
    history: list[BaseMessage],
    trigger: str,
) -> dict:
    return build_handoff_context(
        trigger=trigger,
        semantic_reason=decision.reason,
        confidence=decision.confidence,
        risk_flags=decision.risk_flags,
        capabilities=decision.capabilities,
        latest_customer_message=_latest_customer_text(history),
        flow_type=flow.flow_type if flow is not None else None,
        flow_status=flow.status if flow is not None else None,
        missing_information=(
            flow.missing_information
            if flow is not None
            else decision.missing_information
        ),
    )

def _flow_turn_as_capability_decision(
    turn: FlowTurnDecision,
) -> SemanticCapabilityDecision:
    return SemanticCapabilityDecision(
        domains=[],
        capabilities=turn.capabilities,
        risk_flags=turn.risk_flags,
        flow_signal="interrupt" if turn.action == "interrupt" else "none",
        package_intent=turn.package_intent,
        entity_hints=turn.entity_hints,
        missing_information=turn.missing_information,
        recommended_handoff_category=turn.recommended_handoff_category,
        recommended_handoff_priority=turn.recommended_handoff_priority,
        confidence=turn.confidence,
        reason=turn.reason,
    )

def _flow_type_from_capabilities(capabilities: set[str]) -> str | None:
    if "appointment_reschedule" in capabilities:
        return "appointment_reschedule"
    if "availability_discovery" in capabilities or "appointment_creation" in capabilities:
        return "booking"
    return None


_PERSISTENT_FLOW_CAPABILITIES: dict[str, frozenset[str]] = {
    "booking": frozenset({"availability_discovery", "appointment_creation"}),
    "appointment_reschedule": frozenset({"appointment_reschedule"}),
}

def _persistent_flow_capabilities(
    flow_type: str,
    capabilities: object,
) -> list[str]:
    """Keep only workflow-core capabilities across turns.
    Semantic read capabilities such as doctor_discovery/pricing are turn-local.
    Persisting them makes later turns inherit stale tool access even when the
    flow interpreter no longer requested those reads. This filter is purely a
    post-AI workflow policy boundary; it does not inspect customer text.
    """
    allowed = _PERSISTENT_FLOW_CAPABILITIES.get(flow_type, frozenset())
    if not isinstance(capabilities, (list, tuple, set, frozenset)):
        return []
    return sorted({str(item) for item in capabilities if str(item) in allowed})


_TURN_LOCAL_READ_CAPABILITIES = frozenset(
    {
        "service_information",
        "pricing",
        "branch_discovery",
        "doctor_discovery",
        "appointment_list",
        "customer_profile",
        "customer_history",
        "package_information",
        "package_refund_quote",
    }
)


def _turn_is_local_side_read(
    flow: ConversationFlowState | None,
    turn: FlowTurnDecision | None,
) -> bool:
    """Keep informational detours turn-local while an operational flow stays alive.

    Only read-only informational capabilities qualify. Operational capabilities such
    as booking/reschedule/cancellation never take this shortcut, so an ambiguous
    request that can reasonably continue a reschedule keeps the existing behavior.
    """
    if flow is None or turn is None or turn.action != "continue":
        return False
    capabilities = {str(item) for item in turn.capabilities}
    # Capability-free conversational turns (language change, greeting, recall) are
    # also turn-local: keep the workflow alive but do not inherit/mutate it.
    return not capabilities or capabilities.issubset(_TURN_LOCAL_READ_CAPABILITIES)

def _handoff_direct(
    *,
    db: Session,
    tool_context: AgentToolContext,
    policy: CapabilityPolicyDecision,
    reason: str,
    run_id: UUID,
    flow: ConversationFlowState | None,
) -> tuple[str, str] | None:
    try:
        result = _invoke_authorized_tool(
            tool_context=tool_context,
            policy=policy,
            tool_name="escalate_to_human",
            arguments={
                "reason": reason or "Semantic safety policy requested human ownership.",
                "category": policy.handoff_category,
                "priority": policy.handoff_priority,
            },
        )
    except ToolAuthorizationError:
        return None
    if not result or result.get("ok") is not True:
        return None
    if flow is not None and flow.is_active:
        try:
            interrupt_flow(
                db,
                flow,
                run_id=run_id,
                reason=f"handoff:{policy.handoff_category}",
            )
        except FlowStateConflictError:
            # The handoff itself is already authoritative and pauses the agent.
            # Re-load the newest active flow version and interrupt that version so
            # resolving the handoff later cannot accidentally resume stale work.
            latest = get_active_flow(
                db,
                workspace_id=flow.workspace_id,
                conversation_id=flow.conversation_id,
                patient_id=flow.patient_id,
                run_id=run_id,
            )
            if latest is not None:
                interrupt_flow(
                    db,
                    latest,
                    run_id=run_id,
                    reason=f"handoff:{policy.handoff_category}",
                )
    return (
        format_handoff_reply(policy.handoff_category),
        "capability-policy:handoff",
    )

def _apply_prerequisite_option_selection(
    *,
    db: Session,
    flow: ConversationFlowState,
    turn: FlowTurnDecision,
    decision: SemanticCapabilityDecision,
    run_id: UUID,
) -> tuple[ConversationFlowState, FlowTurnDecision, SemanticCapabilityDecision]:
    """Apply a grounded prerequisite choice without authorizing a write.
    The unified LLM may resolve a customer's free-form selection directly to a
    canonical catalog ID, or may return an explicit numbered selection. Python
    only maps that already-grounded selection back to the persisted option
    snapshot. It never interprets customer text.
    """
    snapshot = flow.option_snapshot if isinstance(flow.option_snapshot, dict) else {}
    specs = (
        (
            "needs_service_choice",
            "services",
            "service_query",
            "service_id",
            ("service_name", "name"),
        ),
        (
            "needs_branch_choice",
            "branches",
            "branch_query",
            "branch_id",
            ("branch_name", "name"),
        ),
        (
            "needs_doctor_choice",
            "doctors",
            "doctor_query",
            "doctor_id",
            ("doctor_name", "name"),
        ),
    )
    for flag, collection_name, entity_key, id_key, name_keys in specs:
        if not snapshot.get(flag):
            continue
        choices = snapshot.get(collection_name)
        if not isinstance(choices, list):
            continue
        selected_choice: dict | None = None
        grounded_id = getattr(decision.entity_hints, id_key, None)
        if grounded_id:
            selected_choice = next(
                (
                    choice
                    for choice in choices
                    if isinstance(choice, dict)
                    and str(
                        choice.get(id_key)
                        or choice.get("id")
                        or ""
                    )
                    == str(grounded_id)
                ),
                None,
            )
        if selected_choice is None and turn.action == "select_option" and turn.selection_index is not None:
            index = turn.selection_index - 1
            if 0 <= index < len(choices) and isinstance(choices[index], dict):
                selected_choice = choices[index]

        if selected_choice is None:
            continue
        display_value = next(
            (selected_choice.get(key) for key in name_keys if selected_choice.get(key)),
            None,
        )
        selected_id = selected_choice.get(id_key) or selected_choice.get("id")
        if not isinstance(display_value, str) or not display_value.strip() or not selected_id:
            continue
        selected = display_value.strip()
        selected_id_text = str(selected_id)
        entity_state = dict(flow.entity_state or {})
        entity_state[entity_key] = selected
        entity_state[id_key] = selected_id_text
        candidate_key = id_key.replace("_id", "_candidate_ids")
        entity_state.pop(candidate_key, None)
        flow = transition_flow(
            db,
            flow,
            actor_type="flow_interpreter",
            event_type="requirement_selected",
            run_id=run_id,
            status="collecting_requirements",
            option_snapshot={},
            entity_state=entity_state,
        )
        hints = decision.entity_hints.model_copy(
            update={
                entity_key: selected,
                id_key: selected_id_text,
                candidate_key: [],
            }
        )
        decision = decision.model_copy(update={"entity_hints": hints})
        turn_hints = turn.entity_hints.model_copy(
            update={
                entity_key: selected,
                id_key: selected_id_text,
                candidate_key: [],
            }
        )
        turn = turn.model_copy(
            update={
                "action": "continue",
                "entity_hints": turn_hints,
                "selection_index": None,
                "selection_time": None,
            }
        )
        logger.info(
            "Tia turn run_id=%s stage=requirement-selection field=%s id=%s value=%s",
            run_id,
            entity_key,
            selected_id_text,
            selected,
        )
        return flow, turn, decision
    return flow, turn, decision


def _normalize_unambiguous_slot_selection(
    flow: ConversationFlowState,
    turn: FlowTurnDecision,
) -> FlowTurnDecision:
    """Fill the index only when the persisted choice is objectively unique.

    Multiple-slot booking remains the normal path: the flow interpreter must map
    the customer's choice to an index/time. This fallback does not inspect wording;
    it only prevents an already-confirmed one-slot snapshot from failing because the
    interpreter omitted a redundant ``selection_index=1``.
    """
    if flow.flow_type != "booking" or turn.action != "select_option":
        return turn
    if turn.selection_index is not None or turn.selection_time:
        return turn
    snapshot = flow.option_snapshot if isinstance(flow.option_snapshot, dict) else {}
    if any(
        bool(snapshot.get(key))
        for key in (
            "needs_service_choice",
            "needs_branch_choice",
            "needs_doctor_choice",
            "needs_appointment_choice",
        )
    ):
        return turn
    slots = snapshot.get("slots")
    if not isinstance(slots, list) or len(slots) != 1 or not isinstance(slots[0], dict):
        return turn
    return turn.model_copy(update={"selection_index": 1, "selection_time": None})


def _effective_booking_package_intent(flow: ConversationFlowState, turn: FlowTurnDecision) -> str:
    current = str(turn.package_intent)
    if current in {"use_existing", "avoid_existing"}:
        return current
    persisted = (flow.entity_state or {}).get("package_intent")
    if persisted in {"use_existing", "avoid_existing"}:
        return str(persisted)
    return "none"


def _structured_flow_write(
    *,
    db: Session,
    flow: ConversationFlowState,
    turn: FlowTurnDecision,
    policy: CapabilityPolicyDecision,
    tool_context: AgentToolContext,
    run_id: UUID,
) -> tuple[str, str] | None:
    if turn.action != "select_option":
        return None
    selected_doctor_id = getattr(turn.entity_hints, "doctor_id", None) or (
        (flow.entity_state or {}).get("doctor_id")
    )
    slot = select_slot_from_structured_selection(
        flow.option_snapshot,
        selection_index=turn.selection_index,
        selection_time=turn.selection_time,
        doctor_id=str(selected_doctor_id) if selected_doctor_id else None,
    )
    if slot is None and turn.selection_time:
        normalized_time = str(turn.selection_time).strip()
        if len(normalized_time) == 4 and normalized_time[1] == ":":
            normalized_time = "0" + normalized_time
        matching_doctors = []
        seen_doctors: set[str] = set()
        snapshot_slots = (flow.option_snapshot or {}).get("slots")
        if isinstance(snapshot_slots, list):
            for candidate in snapshot_slots:
                if not isinstance(candidate, dict):
                    continue
                if str(candidate.get("start_time_24h") or "") != normalized_time:
                    continue
                doctor_name = str(candidate.get("doctor_name") or "الدكتور المتاح").strip()
                doctor_key = str(candidate.get("doctor_id") or doctor_name)
                if doctor_key in seen_doctors:
                    continue
                seen_doctors.add(doctor_key)
                matching_doctors.append(doctor_name)
        if len(matching_doctors) > 1:
            names = "، ".join(matching_doctors[:4])
            return (
                f"الساعة {normalized_time} متاحة مع أكتر من دكتور: {names}. "
                "قولي تفضّل مين عشان أحجز من غير ما أختار مكانك.",
                "flow-interpreter:deterministic-slot-ambiguity",
            )
    if slot is None:
        return None
    if flow.flow_type == "booking":
        tool_name = "book_appointment"
        arguments = booking_tool_args(slot)
        service_id = _uuid_from_metadata((flow.entity_state or {}).get("service_id"))
        start_at: datetime | None = None
        start_local = slot.get("start_local")
        if isinstance(start_local, str) and start_local.strip():
            try:
                start_at = datetime.fromisoformat(start_local)
            except ValueError:
                start_at = None
        booking_package_intent = _effective_booking_package_intent(flow, turn)
        package_requirement_reply = _booking_package_requirement_reply(
            db=db, workspace_id=tool_context.workspace.id, patient_id=tool_context.patient.id,
            service_id=service_id, start_at=start_at, package_intent=booking_package_intent,
        )
        if package_requirement_reply is not None:
            cancel_flow(db, flow, run_id=run_id, reason="explicit_package_requirement_not_met")
            return (package_requirement_reply, "flow-interpreter:deterministic-package-requirement")
    elif flow.flow_type == "appointment_reschedule":
        current = (flow.option_snapshot or {}).get("current_appointment")
        if not isinstance(current, dict) or not current.get("appointment_id"):
            return None
        tool_name = "reschedule_appointment"
        arguments = reschedule_tool_args(
            current_appointment_id=str(current["appointment_id"]),
            slot=slot,
        )
    else:
        return None
    # The active structured flow is the write-authority boundary here:
    # a customer-selected adapter-verified slot plus the optimistic flow-state
    # guard below is sufficient. Do not re-authorize the same booking decision
    # through the current turn's LLM capability/tool surface.
    if policy.requires_human:
        return None
    # Optimistic state guard BEFORE the write. If another turn changed the
    # workflow after the interpreter saw it, this CAS fails and no booking /
    # reschedule tool is executed against stale state.
    flow = transition_flow(
        db,
        flow,
        actor_type="flow_interpreter",
        event_type="updated",
        run_id=run_id,
        status="ready_to_execute",
        pending_action={
            "tool_name": tool_name,
            "selection_index": turn.selection_index,
            "selection_time": turn.selection_time,
            "start_local": slot.get("start_local"),
        },
        last_decision=turn.model_dump(mode="json"),
    )
    record_write_authorized(
        db,
        flow,
        run_id=run_id,
        tool_name=tool_name,
    )
    result = _invoke_tool(
        tool_context=tool_context,
        tool_name=tool_name,
        arguments=arguments,
    )
    if not result or result.get("ok") is not True:
        return None

    record_write_completed(
        db,
        flow,
        run_id=run_id,
        tool_name=tool_name,
        result=result,
    )
    if flow.flow_type == "booking":
        appointment = result.get("appointment")
        if not isinstance(appointment, dict):
            return None
        package_result: dict[str, object] | None = None
        if booking_package_intent != "avoid_existing":
            package_result = _apply_single_matching_package_to_booking(
                db=db, workspace_id=tool_context.workspace.id,
                patient_id=tool_context.patient.id, appointment_payload=appointment,
            )
        complete_flow(
            db,
            flow,
            run_id=run_id,
            result={"tool": tool_name, "output": result},
        )
        return (
            _package_booking_success_reply(appointment, package_result),
            "flow-interpreter:deterministic-booking",
        )
    complete_flow(
        db,
        flow,
        run_id=run_id,
        result={"tool": tool_name, "output": result},
    )
    return (
        "تمام، الموعد اتغيّر للميعاد الجديد بنجاح.",
        "flow-interpreter:deterministic-reschedule",
    )

def _run_after_inbound(
    *,
    db: Session,
    workspace: Workspace,
    patient: Patient,
    conversation: Conversation,
    inbound: Message,
    run_id: UUID,
    outbound_delivery_status: str,
    source: str,
) -> AgentChatResponse:
    turn_started = perf_counter()
    active_handoff = get_active_handoff(
        db,
        workspace_id=workspace.id,
        conversation_id=conversation.id,
    )
    if not agent_can_reply(conversation) or active_handoff is not None:
        return AgentChatResponse(
            run_id=run_id,
            conversation_id=conversation.id,
            inbound_message_id=inbound.id,
            outbound_message_id=None,
            reply=None,
            handoff_required=True,
            agent_paused=True,
            model=None,
        )
    history = _history_from_db(db, conversation)
    flow = get_active_flow(
        db,
        workspace_id=workspace.id,
        conversation_id=conversation.id,
        patient_id=patient.id,
        run_id=run_id,
    )
    timezone_name, local_now = _workspace_clock(workspace)
    flow_turn: FlowTurnDecision | None = None
    grounded_mode = settings.agent_unified_turn_interpreter_enabled
    catalog_started = perf_counter()
    clinic_catalog = build_clinic_catalog(db, workspace) if grounded_mode else {}
    if grounded_mode:
        logger.info(
            "Tia turn run_id=%s stage=clinic-catalog services=%s branches=%s doctors=%s duration_ms=%s",
            run_id,
            len(clinic_catalog.get("services", [])),
            len(clinic_catalog.get("branches", [])),
            len(clinic_catalog.get("doctors", [])),
            int((perf_counter() - catalog_started) * 1000),
        )
    semantic_started = perf_counter()
    if grounded_mode:
        unified_turn = interpret_customer_turn(
            flow=flow,
            history=history,
            timezone_name=timezone_name,
            local_now=local_now,
            clinic_catalog=clinic_catalog,
        )
        semantic_decision = _package_intent_non_booking(unified_turn.as_semantic_decision())
        semantic_decision = _with_implicit_primary_branch(
            semantic_decision, workspace=workspace, clinic_catalog=clinic_catalog,
        )
        if flow is not None:
            flow_turn = unified_turn.as_flow_turn_decision().model_copy(update={
                "capabilities": list(semantic_decision.capabilities),
                "package_intent": semantic_decision.package_intent,
                "entity_hints": semantic_decision.entity_hints,
            })
            turn_local_side_read = _turn_is_local_side_read(flow, flow_turn)
            inherited_capabilities = (
                _persistent_flow_capabilities(flow.flow_type, flow.capabilities)
                if flow_turn.action != "interrupt" and not turn_local_side_read
                else []
            )
        else:
            turn_local_side_read = False
            inherited_capabilities = []
        semantic_stage = "unified-turn-interpreter"
    elif flow is not None:
        flow_turn = interpret_active_flow_turn(
            flow=flow,
            history=history,
            timezone_name=timezone_name,
            local_now=local_now,
        )
        semantic_decision = _package_intent_non_booking(_flow_turn_as_capability_decision(flow_turn))
        flow_turn = flow_turn.model_copy(update={
            "capabilities": list(semantic_decision.capabilities),
            "package_intent": semantic_decision.package_intent,
        })
        turn_local_side_read = _turn_is_local_side_read(flow, flow_turn)
        inherited_capabilities = (
            _persistent_flow_capabilities(flow.flow_type, flow.capabilities)
            if flow_turn.action != "interrupt" and not turn_local_side_read
            else []
        )
        semantic_stage = "flow-interpreter"
    else:
        turn_local_side_read = False
        semantic_decision = _package_intent_non_booking(route_customer_message(
            history=history, timezone_name=timezone_name, local_now=local_now,
        ))
        inherited_capabilities = []
        semantic_stage = "semantic-router"
    logger.info(
        "Tia turn run_id=%s stage=%s duration_ms=%s capabilities=%s risks=%s",
        run_id,
        semantic_stage,
        int((perf_counter() - semantic_started) * 1000),
        semantic_decision.capabilities,
        semantic_decision.risk_flags,
    )
    logger.info(
        "Tia turn run_id=%s stage=semantic-entities source=%s entity_hints=%s missing=%s",
        run_id,
        semantic_stage,
        semantic_decision.entity_hints.model_dump(mode="json"),
        semantic_decision.missing_information,
    )
    if str(semantic_decision.package_intent) == "purchase":
        inherited_capabilities = []
        turn_local_side_read = False
    policy = resolve_capability_policy(
        semantic_decision, inherited_capabilities=inherited_capabilities,
    )
    if flow is not None and str(semantic_decision.package_intent) == "purchase":
        cancel_flow(db, flow, run_id=run_id, reason="customer_switched_to_package_purchase")
        flow = None
        flow_turn = None
    if flow is None:
        flow_type = _flow_type_from_capabilities(set(policy.capabilities))
        if flow_type is not None and not policy.requires_human:
            flow = start_flow(
                db,
                workspace_id=workspace.id,
                conversation_id=conversation.id,
                patient_id=patient.id,
                flow_type=flow_type,
                capabilities=_persistent_flow_capabilities(flow_type, policy.capabilities),
                entity_state={
                    **semantic_decision.entity_hints.model_dump(mode="json", exclude_none=True),
                    **(
                        {"package_intent": str(semantic_decision.package_intent)}
                        if str(semantic_decision.package_intent) in {"use_existing", "avoid_existing"}
                        else {}
                    ),
                },
                missing_information=semantic_decision.missing_information,
                last_decision=_decision_payload(semantic_decision),
                run_id=run_id,
            )
    elif (
        flow_turn is not None
        and flow_turn.action in {"continue", "modify"}
        and not turn_local_side_read
    ):
        merged_flow_state = _merge_flow_entity_state(flow.entity_state, flow_turn)
        if str(flow_turn.package_intent) in {"use_existing", "avoid_existing"}:
            merged_flow_state["package_intent"] = str(flow_turn.package_intent)
        flow = transition_flow(
            db, flow, actor_type="flow_interpreter", event_type="updated", run_id=run_id,
            capabilities=_persistent_flow_capabilities(flow.flow_type, policy.capabilities),
            entity_state=merged_flow_state,
            missing_information=flow_turn.missing_information,
            last_decision=flow_turn.model_dump(mode="json"),
        )
        if flow_turn.clear_entity_fields:
            logger.info(
                "Tia turn run_id=%s stage=flow-entity-clear fields=%s",
                run_id,
                sorted(flow_turn.clear_entity_fields),
            )
    tool_context = AgentToolContext(
        db=db,
        workspace=workspace,
        patient=patient,
        conversation=conversation,
        run_id=run_id,
        handoff_context=_handoff_context_for_turn(
            decision=semantic_decision,
            flow=flow,
            history=history,
            trigger="semantic_policy" if policy.requires_human else "agent_tool",
        ),
    )

    direct: tuple[str, str] | None = None
    if policy.requires_human:
        direct = _handoff_direct(
            db=db,
            tool_context=tool_context,
            policy=policy,
            reason=semantic_decision.reason,
            run_id=run_id,
            flow=flow,
        )
    elif flow is not None and flow_turn is not None:
        if flow_turn.action == "cancel_flow":
            cancel_flow(
                db,
                flow,
                run_id=run_id,
                reason=flow_turn.reason or "customer_cancelled_flow",
            )
            direct = (
                "تمام، وقفت العملية الحالية. لو محتاج حاجة تانية أنا معاك.",
                "flow-interpreter:cancelled",
            )
        elif flow_turn.action == "interrupt":
            interrupt_flow(
                db,
                flow,
                run_id=run_id,
                reason=flow_turn.reason or "customer_interrupted_flow",
            )
            flow = None
        elif turn_local_side_read:
            pass
        else:
            flow, flow_turn, semantic_decision = _apply_prerequisite_option_selection(
                db=db,
                flow=flow,
                turn=flow_turn,
                decision=semantic_decision,
                run_id=run_id,
            )
            flow_turn = _normalize_unambiguous_slot_selection(flow, flow_turn)
            if flow_turn.action == "select_option":
                direct = _structured_flow_write(
                    db=db,
                    flow=flow,
                    turn=flow_turn,
                    policy=policy,
                    tool_context=tool_context,
                    run_id=run_id,
                )
    if direct is not None:
        reply, model_name = direct
        # A completed structured booking/reschedule is already a verified customer
        # fact. Do not send it through another model pass after the write.
        if (
            grounded_mode
            and model_name != "capability-policy:handoff"
            and not model_name.startswith("flow-interpreter:deterministic-")
        ):
            try:
                reply, composed_model = compose_grounded_customer_reply(
                    clinic_name=workspace.name,
                    timezone_name=timezone_name,
                    local_now=local_now,
                    history=history,
                    semantic_decision=semantic_decision,
                    verified_data={
                        "executed_action": {
                            "ok": True,
                            "verified_customer_facts": reply,
                            "execution_source": model_name,
                        }
                    },
                )
                model_name = composed_model
                logger.info(
                    "Tia turn run_id=%s stage=grounded-response-composer action_result=true model=%s",
                    run_id,
                    model_name,
                )
            except (LLMProviderError, RuntimeError) as exc:
                logger.warning(
                    "Tia turn run_id=%s stage=grounded-response-composer-fallback action_result=true error=%s",
                    run_id,
                    type(exc).__name__,
                )
    else:
        prefetch_started = perf_counter()
        prefetched_results, prefetched_tool_names = _prefetch_read_tools(
            tool_context=tool_context,
            policy=policy,
            decision=semantic_decision,
            flow=flow,
            use_flow_state=not turn_local_side_read,
            grounded_mode=grounded_mode,
        )
        if grounded_mode:
            catalog_facts = grounded_catalog_facts(
                catalog=clinic_catalog,
                entity_hints=semantic_decision.entity_hints,
                capabilities=policy.capabilities,
            )
            if catalog_facts is not None:
                prefetched_results["clinic_catalog"] = catalog_facts
                snapshot = choice_snapshot_from_grounded_facts(catalog_facts)
                if (
                    snapshot is not None
                    and flow is not None
                    and flow.is_active
                    and not turn_local_side_read
                ):
                    flow = transition_flow(
                        db,
                        flow,
                        actor_type="flow_interpreter",
                        event_type="options_presented",
                        run_id=run_id,
                        status="awaiting_option_selection",
                        option_snapshot=snapshot,
                        last_decision=_decision_payload(semantic_decision),
                    )
        if (
            grounded_mode
            and "clinic_catalog" not in prefetched_results
            and set(policy.capabilities).intersection(
                {
                    "service_information",
                    "pricing",
                    "branch_discovery",
                    "doctor_discovery",
                    "availability_discovery",
                    "appointment_creation",
                }
            )
        ):
            # If the interpreter intentionally left an entity unresolved, the
            # response LLM may still explain/ask from the same verified catalog.
            # Execution remains blocked until canonical IDs are selected.
            prefetched_results["clinic_catalog"] = {
                "ok": True,
                "source": "clinic_adapter_catalog",
                "catalog": clinic_catalog,
                "selection_status": "unresolved",
            }
        logger.info(
            "Tia turn run_id=%s stage=prefetch-summary tools=%s duration_ms=%s",
            run_id,
            sorted(prefetched_tool_names),
            int((perf_counter() - prefetch_started) * 1000),
        )
        # An explicit booking request with an exact date/time is already customer
        # authorization. If the adapter verifies exactly one matching slot, execute
        # it now instead of asking for a redundant confirmation and interpreting a
        # second customer turn. Requests with multiple/no exact options keep the
        # normal deterministic option-selection path below.
        prefetch_direct: tuple[str, str] | None = None
        if flow is not None and flow.is_active and flow.flow_type == "booking":
            payload = prefetched_results.get("get_booking_options")
            if isinstance(payload, dict):
                selection_index = _exact_action_selection_index(
                    decision=semantic_decision,
                    payload=payload,
                    required_capability="appointment_creation",
                )
                if selection_index is not None and not turn_local_side_read:
                    flow = _sync_flow_from_verified_prefetch(
                        db=db,
                        flow=flow,
                        prefetched_results=prefetched_results,
                        run_id=run_id,
                    )
                    prefetch_direct = _structured_flow_write(
                        db=db,
                        flow=flow,
                        turn=_exact_action_flow_turn(
                            semantic_decision,
                            selection_index=selection_index,
                        ),
                        policy=policy,
                        tool_context=tool_context,
                        run_id=run_id,
                    )
                # The deterministic availability renderer is intentionally narrow.
                # The semantic interpreter may identify a compound read such as
                # pricing + availability; in that case let the grounded composer
                # combine all verified facts instead of dropping part of the ask.
                availability_only_request = set(policy.capabilities).issubset(
                    {"availability_discovery", "appointment_creation"}
                )
                if prefetch_direct is None and availability_only_request:
                    verified_reply = _verified_booking_slots_reply(
                        payload,
                        booking_authorized="appointment_creation" in set(policy.capabilities),
                    )
                    if verified_reply:
                        prefetch_direct = (
                            verified_reply,
                            "deterministic:verified-get_booking_options",
                        )

        if (
            prefetch_direct is None
            and flow is not None
            and flow.is_active
            and flow.flow_type == "appointment_reschedule"
            and flow_turn is not None
            and flow_turn.action in {"modify", "select_option"}
            and not turn_local_side_read
        ):
            payload = prefetched_results.get("get_reschedule_options")
            if isinstance(payload, dict):
                selection_index = _exact_action_selection_index(
                    decision=semantic_decision,
                    payload=payload,
                    required_capability="appointment_reschedule",
                )
                if selection_index is not None:
                    flow = _sync_flow_from_verified_prefetch(
                        db=db,
                        flow=flow,
                        prefetched_results=prefetched_results,
                        run_id=run_id,
                    )
                    prefetch_direct = _structured_flow_write(
                        db=db,
                        flow=flow,
                        turn=_exact_action_flow_turn(
                            semantic_decision,
                            selection_index=selection_index,
                        ),
                        policy=policy,
                        tool_context=tool_context,
                        run_id=run_id,
                    )

        if (
            prefetch_direct is None
            and "package_refund_quote" not in policy.capabilities
            and str(semantic_decision.package_intent) == "purchase"
        ):
            package_intent_reply = _verified_package_intent_reply(
                intent=str(semantic_decision.package_intent),
                package_payload=(
                    prefetched_results.get("customer_packages")
                    if isinstance(prefetched_results.get("customer_packages"), dict)
                    else None
                ),
                catalog_payload=(
                    prefetched_results.get("clinic_catalog")
                    if isinstance(prefetched_results.get("clinic_catalog"), dict)
                    else None
                ),
            )
            if package_intent_reply:
                prefetch_direct = (package_intent_reply, "deterministic:package-intent")

        if prefetch_direct is None and "package_refund_quote" in policy.capabilities:
            refund_payload = prefetched_results.get("package_refund_quote")
            if isinstance(refund_payload, dict):
                refund_reply = _verified_package_refund_reply(refund_payload)
                if refund_reply:
                    prefetch_direct = (
                        refund_reply,
                        "deterministic:package-refund-quote",
                    )

        if (
            prefetch_direct is None
            and grounded_mode
            and _grounded_response_can_cover(policy, prefetched_results)
        ):
            composer_started = perf_counter()
            try:
                prefetch_direct = compose_grounded_customer_reply(
                    clinic_name=workspace.name,
                    timezone_name=timezone_name,
                    local_now=local_now,
                    history=history,
                    semantic_decision=semantic_decision,
                    verified_data=prefetched_results,
                )
                logger.info(
                    "Tia turn run_id=%s stage=grounded-response-composer duration_ms=%s model=%s",
                    run_id,
                    int((perf_counter() - composer_started) * 1000),
                    prefetch_direct[1],
                )
            except (LLMProviderError, RuntimeError) as exc:
                logger.warning(
                    "Tia turn run_id=%s stage=grounded-response-composer-fallback error=%s",
                    run_id,
                    type(exc).__name__,
                )
                prefetch_direct = None
        if prefetch_direct is None and not grounded_mode:
            prefetch_direct = _verified_prefetch_direct_reply(
                policy=policy,
                prefetched_results=prefetched_results,
            )
        if prefetch_direct is not None:
            reply, model_name = prefetch_direct
            logger.info(
                "Tia turn run_id=%s stage=prefetch-direct-response model=%s",
                run_id,
                model_name,
            )
            flow_sync_started = perf_counter()
            if grounded_mode:
                flow = flow if turn_local_side_read else _sync_flow_from_verified_prefetch(
                    db=db,
                    flow=flow,
                    prefetched_results=prefetched_results,
                    run_id=run_id,
                )
            else:
                if not turn_local_side_read:
                    flow = sync_flow_from_agent_run(
                        db,
                        flow=flow,
                        workspace_id=workspace.id,
                        conversation_id=conversation.id,
                        run_id=run_id,
                    )
            logger.info(
                "Tia turn run_id=%s stage=flow-sync duration_ms=%s source=%s",
                run_id,
                int((perf_counter() - flow_sync_started) * 1000),
                "verified-prefetch" if grounded_mode else "agent-actions",
            )
        else:
            operational_context = None
            if not turn_local_side_read:
                operational_context = _recent_operational_context(
                    db,
                    conversation,
                    flow,
                )
            if prefetched_results:
                turn_prefetch = json.dumps(
                    {"turn_prefetch": prefetched_results},
                    ensure_ascii=False,
                    default=str,
                    separators=(",", ":"),
                )
                operational_context = (
                    f"{operational_context}\n{turn_prefetch}"
                    if operational_context
                    else turn_prefetch
                )
                operational_context = operational_context[
                    : settings.agent_operational_context_max_chars
                ]
            agent_allowed_tools = set(policy.allowed_tools) - prefetched_tool_names
            if grounded_mode:
                # In the grounded runtime, customer language has already been mapped
                # to canonical PostgreSQL IDs by the unified interpreter. Do not let
                # the fallback conversational agent re-enter lexical/fuzzy entity
                # resolution through legacy discovery tools. It can answer from the
                # verified operational context and may still execute separately
                # authorized non-discovery writes such as confirmation/cancellation.
                agent_allowed_tools.difference_update(
                    {
                        "search_services",
                        "list_branches",
                        "list_doctors",
                        "get_booking_options",
                        "get_reschedule_options",
                        "get_available_slots",
                    }
                )
            # While a persisted booking/reschedule flow is active, write execution
            # is state-driven only. The main LLM can discover/reason, but cannot
            # bypass the workflow snapshot by calling the write tool directly.
            if flow is not None and flow.is_active:
                if flow.flow_type == "booking":
                    agent_allowed_tools.discard("book_appointment")
                elif flow.flow_type == "appointment_reschedule":
                    agent_allowed_tools.discard("reschedule_appointment")
            agent_started = perf_counter()
            reply, model_name = run_tia_customer_agent(
                history=history,
                tool_context=tool_context,
                operational_context=operational_context,
                allowed_tool_names=agent_allowed_tools,
            )
            logger.info(
                "Tia turn run_id=%s stage=customer-agent duration_ms=%s model=%s",
                run_id,
                int((perf_counter() - agent_started) * 1000),
                model_name,
            )
            if not turn_local_side_read:
                flow = sync_flow_from_agent_run(
                    db,
                    flow=flow,
                    workspace_id=workspace.id,
                    conversation_id=conversation.id,
                    run_id=run_id,
                )
    reply = sanitize_customer_reply(reply)
    persistence_started = perf_counter()
    db.refresh(conversation)
    # A staff member may take over while the model is running. Re-lock and
    # refresh ownership immediately before the AI creates an outbound message so
    # a stale in-memory Conversation cannot produce a second reply.
    locked_conversation = lock_conversation_ownership(
        db,
        workspace_id=workspace.id,
        conversation_id=conversation.id,
    )
    if locked_conversation is None:
        raise AgentChatError("Conversation disappeared before the agent response was persisted.")
    conversation = locked_conversation
    active_handoff = get_active_handoff(
        db,
        workspace_id=workspace.id,
        conversation_id=conversation.id,
    )
    handoff_ack_allowed = _current_run_can_send_handoff_ack(
        db,
        workspace_id=workspace.id,
        conversation_id=conversation.id,
        run_id=run_id,
        active_handoff=active_handoff,
    )
    if (not agent_can_reply(conversation) or active_handoff is not None) and not handoff_ack_allowed:
        db.rollback()
        return AgentChatResponse(
            run_id=run_id,
            conversation_id=conversation.id,
            inbound_message_id=inbound.id,
            outbound_message_id=None,
            reply=None,
            handoff_required=True,
            agent_paused=True,
            model=None,
        )
    outbound_now = datetime.now(UTC)
    outbound = Message(
        workspace_id=workspace.id,
        conversation_id=conversation.id,
        channel_connection_id=conversation.channel_connection_id,
        sender_type="ai",
        direction="outbound",
        message_type="text",
        content=reply,
        delivery_status=outbound_delivery_status,
        metadata_json={
            "agent_run_id": str(run_id),
            "model": model_name,
            "source": source,
            "in_reply_to_message_id": str(inbound.id),
            "dispatch_required": outbound_delivery_status == "queued",
            "handoff_ack": handoff_ack_allowed,
            "capabilities": sorted(policy.capabilities),
            "risk_flags": sorted(policy.risk_flags),
            "flow_id": str(flow.id) if flow is not None else None,
            "flow_version": flow.version if flow is not None else None,
        },
    )
    conversation.last_message_at = outbound_now
    db.add(outbound)
    db.commit()
    # SQLAlchemy assigns the generated primary key during flush/commit. The response
    # only needs outbound.id and the already-loaded conversation.status, so two
    # post-commit refresh SELECTs added latency without changing response semantics.
    logger.info(
        "Tia turn run_id=%s stage=outbound-persist duration_ms=%s",
        run_id,
        int((perf_counter() - persistence_started) * 1000),
    )
    logger.info(
        "Tia turn run_id=%s completed total_duration_ms=%s source=%s model=%s",
        run_id,
        int((perf_counter() - turn_started) * 1000),
        source,
        model_name,
    )
    return AgentChatResponse(
        run_id=run_id,
        conversation_id=conversation.id,
        inbound_message_id=inbound.id,
        outbound_message_id=outbound.id,
        reply=reply,
        handoff_required=conversation.owner_type == OWNER_HUMAN,
        agent_paused=False,
        model=model_name,
    )

def run_agent_chat(
    *,
    db: Session,
    workspace: Workspace,
    payload: AgentChatRequest,
) -> AgentChatResponse:
    now = datetime.now(UTC)
    run_id = uuid4()
    patient = _get_patient(db, workspace.id, payload.patient_id)
    conversation = _get_or_create_conversation(
        db,
        workspace=workspace,
        patient=patient,
        payload=payload,
        now=now,
    )
    # Existing conversations are row-locked by `_get_or_create_conversation`.
    # Take the activity timestamp after that lock is acquired so a request that
    # waited behind a staff read/reply cannot overwrite newer inbox activity
    # with a stale pre-lock timestamp.
    activity_now = datetime.now(UTC)
    inbound = Message(
        workspace_id=workspace.id,
        conversation_id=conversation.id,
        channel_connection_id=conversation.channel_connection_id,
        sender_type="patient",
        direction="inbound",
        message_type="text",
        content=payload.message,
        delivery_status="received",
        metadata_json={"agent_run_id": str(run_id), "source": "agent_api"},
    )
    record_customer_inbound(conversation, now=activity_now)
    patient.last_contact_at = activity_now
    db.add(inbound)
    db.commit()
    db.refresh(inbound)
    db.refresh(conversation)
    db.refresh(patient)
    return _run_after_inbound(
        db=db,
        workspace=workspace,
        patient=patient,
        conversation=conversation,
        inbound=inbound,
        run_id=run_id,
        outbound_delivery_status="sent",
        source="agent_api",
    )

def run_agent_for_existing_inbound(
    *,
    db: Session,
    workspace: Workspace,
    patient: Patient,
    conversation: Conversation,
    inbound: Message,
    source: str = "channel_adapter",
) -> AgentChatResponse:
    if inbound.workspace_id != workspace.id:
        raise AgentChatError("Inbound message belongs to another workspace.")
    if inbound.conversation_id != conversation.id:
        raise AgentChatError("Inbound message belongs to another conversation.")
    if conversation.patient_id != patient.id:
        raise AgentChatError("Conversation belongs to another patient.")
    if inbound.sender_type != "patient" or inbound.direction != "inbound":
        raise AgentChatError(
            "Only inbound patient messages can be processed by the customer agent."
        )
    if patient.status == "blocked":
        raise AgentChatError("Blocked patients cannot use the automated customer agent.")
    metadata = dict(inbound.metadata_json or {})
    existing_run_id = _uuid_from_metadata(metadata.get("agent_run_id"))
    run_id = existing_run_id or uuid4()
    metadata["agent_run_id"] = str(run_id)
    try:
        prior_attempts = int(metadata.get("agent_processing_attempts") or 0)
    except (TypeError, ValueError):
        prior_attempts = 0
    metadata["agent_processing_attempts"] = prior_attempts + 1
    inbound.metadata_json = metadata
    patient.last_contact_at = inbound.created_at
    db.commit()
    db.refresh(inbound)
    if existing_run_id is not None:
        logger.info(
            "Tia inbound retry inbound_message_id=%s run_id=%s attempt=%s",
            inbound.id,
            run_id,
            metadata["agent_processing_attempts"],
        )
    existing_response = _existing_agent_response_for_inbound(
        db,
        conversation=conversation,
        inbound=inbound,
        run_id=run_id,
    )
    if existing_response is not None:
        logger.info(
            "Tia inbound recovery inbound_message_id=%s run_id=%s outbound_message_id=%s",
            inbound.id,
            run_id,
            existing_response.outbound_message_id,
        )
        return existing_response
    return _run_after_inbound(
        db=db,
        workspace=workspace,
        patient=patient,
        conversation=conversation,
        inbound=inbound,
        run_id=run_id,
        outbound_delivery_status="queued",
        source=source,
    )
