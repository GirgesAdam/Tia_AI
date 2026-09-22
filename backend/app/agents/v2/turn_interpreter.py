from __future__ import annotations

import json
from datetime import datetime

from langchain_core.messages import AIMessage, BaseMessage, HumanMessage, SystemMessage

from app.agents.llm_runtime import invoke_with_model_chain
from app.agents.model_provider import (
    build_realtime_interpreter_fallback_model,
    build_realtime_interpreter_model,
)
from app.agents.structured_output import StructuredOutputError, invoke_typed_structured_output
from app.agents.v2.semantic_context import SemanticContext, ground_turn_references
from app.agents.v2.time_resolution import resolve_turn_times_by_clinic_hours
from app.agents.v2.turn_contract import (
    DateConstraint,
    EntityReference,
    TiaTurnUnderstanding,
    TimeConstraint,
)
from app.agents.v2.turn_normalization import dedupe_exact_operations
from app.core.config import settings


def _message_text(message: BaseMessage, *, limit: int = 1200) -> str:
    if not isinstance(message.content, str) or not message.content.strip():
        return ""
    text = " ".join(message.content.strip().split())
    return text[:limit] + ("…" if len(text) > limit else "")


def _latest_customer_index(history: list[BaseMessage]) -> int | None:
    for index in range(len(history) - 1, -1, -1):
        if isinstance(history[index], HumanMessage) and _message_text(history[index]):
            return index
    return None


def _native_context_messages(
    history: list[BaseMessage],
    *,
    latest_customer_index: int,
    limit: int = 6,
) -> list[BaseMessage]:
    selected: list[BaseMessage] = []
    for message in history[:latest_customer_index]:
        if not isinstance(message, (HumanMessage, AIMessage)):
            continue
        text = _message_text(message, limit=900)
        if not text:
            continue
        if isinstance(message, HumanMessage):
            selected.append(HumanMessage(content=text))
        else:
            selected.append(AIMessage(content=text))
    return selected[-limit:]


def _interpreter_system_prompt(*, timezone_name: str, local_now: datetime) -> str:
    return f"""You are Tia's semantic turn interpreter for an aesthetic clinic.
Return only the required structured schema. Understand customer meaning; do not answer customers,
choose tools, perform writes, calculate business facts, or invent clinic facts.

CORE SEMANTICS
- Interpret the latest turn using recent dialogue plus supplied active_task, pending_choice,
  recent_verified_read, and semantic catalog refs. Never route by keywords, phrase matching, or
  memorized lexical triggers.
- Use only supplied refs. For one clear entity set ref. For genuine identity ambiguity set ref=null
  with candidate_refs and candidate_mode=ambiguous. For an intentional group/comparison use
  candidate_refs with candidate_mode=set. Never invent refs.
- Comparisons stay informational. For availability comparisons without a fixed date use
  date.mode=next_available; do not force a choice merely to compare candidates.
- continues_previous=true only for a clear continuation of recent_verified_read. Emit only newly
  stated/changed constraints; Python inherits omitted verified scope. A new value replaces the old
  value in that dimension. Use continuation_condition=if_previous_no_availability only for an
  explicitly conditional fallback; otherwise use always.
- execution_intent=execute only when the customer authorizes the action now. Questions,
  comparisons, hypotheticals, consequences/options, and reads are informational.
- Preserve independently meaningful requests as separate operations in customer order; alternatives
  are not separate operations. Deduplicate only exact semantic duplicates.
- Resolve the whole latest message jointly. If one operation refers to the same date/time/doctor/
  device/visit whose value is explicit elsewhere in that same message, copy that value to every
  referring operation; never guess or leave it unresolved when the value is present.
- Package purchase and booking are separate actions. Buying a package plus booking its first session
  emits buy_package + book; package_usage=use_existing when that session should consume it. Other
  requested appointments remain separate book operations.
- Comparing an owned package with standalone payment emits informational package_info + pricing.
  Asking about a past appointment outcome and its effect on current owned-package balance/state
  emits customer_history + package_info. Do not infer current package balance from history alone.
- Harmless/social side turns do not cancel active tasks. On task corrections emit the new semantic
  value only; Python owns state invalidation and persistence. Prefer recent_verified_read over
  assistant prose for verified scope.
- package_usage controls entitlement use, not service identity. Avoiding a package may still book the
  already established service as standalone.
- select_active is valid only when structured pending/active options are supplied. Assistant prose
  alone is not an option snapshot. Otherwise reconstruct the intended primary operation from recent
  dialogue so Python can verify it again.
- continue_active adds requirements to a supplied active task. cancel_active stops an unfinished
  conversational task; cancel_appointment cancels an existing appointment.

OPERATION MEANING
- availability inspects possibilities; book requests creation of a new appointment, even if details
  are missing. reschedule changes an existing appointment; confirm_appointment confirms one.
- appointment_list with broad wording such as a category ("my next laser appointment") must leave
  service null unless one specific service is clearly intended.
- package_info and refund_quote are reads; buy_package is a purchase. A hypothetical package refund
  is refund_quote; an instruction to cancel/refund/terminate a purchased package now is
  human_support.
- clinic_info is clinic-wide information/policy/general guidance or device comparison not tied to one
  service. service_info is information about one specific service.
- customer_history is the customer's prior visits/services/payment facts; a contested payment also
  signals payment_dispute.
- Medical suitability/symptom questions signal medical; acute/emergency-seeming situations signal
  urgent_medical. Explicit requests for a person use human_support.

DATE/TIME
- Resolve clear relative dates using the clinic-local clock; if still underspecified leave null.
- exact date: mode=exact + start_date. range: mode=range + start_date/end_date. starting from:
  mode=from_date + start_date. nearest date: mode=next_available with no invented date.
- exact time: mode=exact + start_time. after/before use their modes + start_time (inclusive boundary).
  range uses start_time/end_time. nearest uses mode=nearest; supply an anchor only if stated now,
  otherwise Python may inherit a previous verified exact-time anchor.
- If wording or a 24-hour clock fixes AM/PM, use time_ambiguity=none. For a 1–12 clock that could be
  AM or PM, use twelve_hour and one 12-hour-form candidate; never use clinic hours to guess. Apply
  the same rule independently to start/end time ambiguity and time selections. Python resolves
  ambiguous candidates against clinic_operating_hours.
- follow_up_at_local is an ISO local datetime only when the customer supplied enough meaning for a
  specific future time; otherwise null.

SERVICE DETAILS
- requested_service_details contains only explicitly requested facts: price, duration, description,
  devices. pricing implies price. Generic service information implies description. Explaining or
  comparing devices for one service implies devices + description. Here description means the saved
  clinic-authored "معلومات Tia" guidance, not a service-table description. Do not add unrelated
  details.

Clinic timezone: {timezone_name}
Clinic local time: {local_now.isoformat()}
"""


def _build_interpreter_messages(
    *,
    history: list[BaseMessage],
    semantic_context: SemanticContext,
    timezone_name: str,
    local_now: datetime,
) -> list[BaseMessage]:
    latest_index = _latest_customer_index(history)
    if latest_index is None:
        raise ValueError("V2 turn interpretation requires a customer message.")

    latest_text = _message_text(history[latest_index])
    system = SystemMessage(
        content=_interpreter_system_prompt(
            timezone_name=timezone_name,
            local_now=local_now,
        )
    )
    context = SystemMessage(
        content=(
            "SEMANTIC_CONTEXT (ephemeral references only; Python resolves them to canonical data):\n"
            + json.dumps(
                semantic_context.model_input,
                ensure_ascii=False,
                default=str,
                separators=(",", ":"),
            )
        )
    )
    recent = _native_context_messages(
        history,
        latest_customer_index=latest_index,
    )
    return [system, context, *recent, HumanMessage(content=latest_text)]


def _reference_from_verified(
    verified: dict[str, object],
    *,
    single_key: str,
    set_key: str | None = None,
) -> EntityReference | None:
    single = verified.get(single_key)
    if isinstance(single, str) and single:
        return EntityReference(text=None, ref=single, candidate_refs=[], candidate_mode="ambiguous")
    if set_key is not None:
        raw = verified.get(set_key)
        if isinstance(raw, list):
            refs = [str(item) for item in raw if isinstance(item, str) and item]
            if refs:
                return EntityReference(text=None, ref=None, candidate_refs=refs, candidate_mode="set")
    return None


def _conditional_fallback_disproved(
    verified: dict[str, object],
    *,
    continuation_condition: str,
) -> bool:
    if continuation_condition != "if_previous_no_availability":
        return False
    found = verified.get("availability_found")
    option_count = verified.get("availability_option_count")
    return found is True or (
        isinstance(option_count, int) and not isinstance(option_count, bool) and option_count > 0
    )


def merge_verified_read_context(
    turn: TiaTurnUnderstanding,
    semantic_context: SemanticContext,
) -> TiaTurnUnderstanding:
    """Merge explicitly-declared continuations with the previous verified read scope."""
    raw = semantic_context.model_input.get("recent_verified_read")
    if not isinstance(raw, dict) or not raw:
        return turn

    previous_date = None
    previous_time = None
    if isinstance(raw.get("date"), dict):
        try:
            previous_date = DateConstraint.model_validate(raw["date"])
        except ValueError:
            previous_date = None
    if isinstance(raw.get("time"), dict):
        try:
            previous_time = TimeConstraint.model_validate(raw["time"])
        except ValueError:
            previous_time = None

    operations = []
    for operation in turn.operations:
        if not operation.continues_previous:
            operations.append(operation)
            continue

        entities = operation.entities
        updates: dict[str, object] = {}
        inherited = (
            ("service", _reference_from_verified(raw, single_key="service_ref")),
            (
                "doctor",
                _reference_from_verified(
                    raw,
                    single_key="doctor_ref",
                    set_key="doctor_refs",
                ),
            ),
            ("device", _reference_from_verified(raw, single_key="device_ref")),
        )
        for field, value in inherited:
            if getattr(entities, field) is None and value is not None:
                updates[field] = value

        fallback_disproved = _conditional_fallback_disproved(
            raw,
            continuation_condition=operation.continuation_condition,
        )
        if fallback_disproved and previous_date is not None:
            updates["date"] = previous_date
        elif entities.date is None and previous_date is not None:
            updates["date"] = previous_date

        if fallback_disproved and previous_time is not None:
            updates["time"] = previous_time
        elif entities.time is None and previous_time is not None:
            updates["time"] = previous_time
        elif (
            entities.time is not None
            and entities.time.mode == "nearest"
            and entities.time.start_time is None
            and previous_time is not None
            and previous_time.mode == "exact"
            and previous_time.start_time is not None
        ):
            updates["time"] = entities.time.model_copy(
                update={
                    "start_time": previous_time.start_time,
                    "start_time_ambiguity": previous_time.start_time_ambiguity,
                }
            )
        if updates:
            entities = entities.model_copy(update=updates)
        operations.append(operation.model_copy(update={"entities": entities}))
    return turn.model_copy(update={"operations": operations})


def interpret_customer_turn_v2(
    *,
    history: list[BaseMessage],
    semantic_context: SemanticContext,
    timezone_name: str,
    local_now: datetime,
) -> TiaTurnUnderstanding:
    """One semantic LLM call; no regex/keyword fallback and no production side effects."""

    messages = _build_interpreter_messages(
        history=history,
        semantic_context=semantic_context,
        timezone_name=timezone_name,
        local_now=local_now,
    )
    primary_name = settings.openai_model
    fallback_name = settings.openai_fallback_model
    primary_model = build_realtime_interpreter_model()

    def invoke_structured(model) -> TiaTurnUnderstanding:
        try:
            return invoke_typed_structured_output(
                model=model,
                schema=TiaTurnUnderstanding,
                messages=messages,
            )
        except StructuredOutputError:
            return invoke_typed_structured_output(
                model=model,
                schema=TiaTurnUnderstanding,
                messages=messages,
            )

    def invoke_primary() -> TiaTurnUnderstanding:
        return invoke_structured(primary_model)

    def invoke_fallback() -> TiaTurnUnderstanding:
        fallback_model = build_realtime_interpreter_fallback_model()
        if fallback_model is None:
            raise RuntimeError("V2 turn interpreter fallback model is not configured.")
        return invoke_structured(fallback_model)

    model_calls = [(primary_name, invoke_primary)]
    if fallback_name and fallback_name != primary_name:
        model_calls.append((fallback_name, invoke_fallback))

    invocation = invoke_with_model_chain(
        model_calls=model_calls,
        operation="v2-turn-interpreter",
        circuit_breaker_cooldown_seconds=settings.llm_realtime_circuit_breaker_cooldown_seconds,
    )
    continued = merge_verified_read_context(invocation.value, semantic_context)
    grounded = ground_turn_references(continued, semantic_context)
    resolved = resolve_turn_times_by_clinic_hours(grounded, semantic_context)
    return dedupe_exact_operations(resolved)