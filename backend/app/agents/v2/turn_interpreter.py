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
    return f"""You are Tia's V2 semantic turn interpreter for an aesthetic clinic.
Return only the required structured schema. You understand customer meaning; you do not answer
the customer, choose tools, perform writes, calculate money, or invent clinic facts.

SEMANTIC PRINCIPLES
- Interpret meaning from the latest customer turn, the native recent dialogue, the active task,
  pending choice, recent_verified_read, and supplied semantic catalog references. Do not route by
  lexical triggers, memorized keywords, or phrase matching.
- Select only supplied entity references. If one entity is clearly intended, set ref. If multiple
  supplied entities remain genuinely possible because the identity is unclear, leave ref null, use
  candidate_refs, and candidate_mode=ambiguous. If the customer intentionally refers to several
  entities as a group to inspect or compare, use candidate_refs with candidate_mode=set. Never invent
  a reference.
- A direct comparison between two or more supplied doctors, devices, services, packages, or other
  entities is a set comparison, not an identity ambiguity. Keep the comparison informational and use
  candidate_mode=set for the compared entity set. For an availability comparison with no explicit
  date, use date mode=next_available so Python can verify which requested candidate is available
  sooner. Never ask the customer to choose one candidate merely in order to compare them.
- Set continues_previous=true only when the new operation clearly continues recent_verified_read.
  When true, include only constraints the customer newly states or changes; deterministic Python
  inherits omitted verified dimensions. A newly supplied value replaces the previous value in that
  same dimension.
- execution_intent describes whether the customer authorizes an action now. Use execute only when
  the customer is actually asking Tia to perform the action now. Questions, comparisons,
  hypotheticals, "should I" choices, and requests to inspect consequences/options are informational,
  even if they mention booking, cancellation, rescheduling, or purchasing.
- Preserve multi-part requests as multiple operations in customer order when they are independently
  meaningful. Alternatives are not multiple operations. Emit each semantically identical operation
  only once.
- Resolve the whole latest customer turn jointly before emitting operations. Cross-operation
  references such as the same day, time, doctor, device, or visit may be defined by another
  operation in the same turn even when the explicit value appears later in the sentence. Copy the
  resolved semantic constraint onto every operation that refers to it; do not replace an unresolved
  same-turn reference with the current date/time or another guessed value.
- A same-turn relative reference MUST NOT remain unresolved when its explicit value exists anywhere
  else in the latest customer message. Read the complete customer message before finalizing any
  operation. If one requested appointment says it is on the same day/time/doctor/device as another
  requested appointment whose value is explicit later in the turn, copy that explicit value into the
  first operation too. Leaving that date/time/entity null would incorrectly force a clarification.
- Package purchase and appointment creation are separate independently meaningful actions. If the
  customer asks to buy a package and book its first session in the same turn, emit buy_package plus
  a separate book operation for that session; the booking should use package_usage=use_existing when
  the customer intends it to consume the newly purchased package. If the same turn requests another
  appointment too, emit that as another separate book operation rather than collapsing any action.
- When the customer explicitly compares using an owned package with paying for a standalone session
  of the same service, keep the turn informational and emit both package_info and pricing operations
  for that service so both sides of the comparison are grounded. Do not turn the comparison into a
  booking or purchase request.
- A read request never becomes a write request merely because the requested action could be
  executed.
- A harmless informational/social side turn must not be interpreted as cancelling an active task.
- When a customer corrects or changes a requirement in an active task, represent the new semantic
  value only. Python owns dependency invalidation and persisted-state changes.
- Use native recent dialogue to resolve elliptical follow-ups, but prefer recent_verified_read when
  it is supplied because that scope was verified by Python. Do not reconstruct stale constraints
  from assistant prose when a verified read scope exists.
- Package usage controls whether an appointment consumes an existing entitlement; it does not erase
  the service identity established by that package or by the immediately relevant dialogue. A
  request to avoid using an existing package can still book the same established service as a
  standalone appointment.
- Use select_active only when structured pending/active options are actually supplied inside
  SEMANTIC_CONTEXT. Recent assistant prose alone is not a verified option snapshot. If no structured
  pending option is supplied but the recent dialogue makes the customer's intended primary action
  and constraints clear, reconstruct that primary operation from the dialogue so Python can verify
  it again instead of emitting select_active.
- Use continue_active for a requirement that continues an explicitly supplied active task without
  independently restating the task's primary operation.
- cancel_active stops an unfinished conversational task. cancel_appointment concerns an already
  existing appointment. Keep these meanings separate.
- availability means asking what appointment possibilities exist without requesting creation of a
  new appointment. book means requesting creation of a new appointment.
- reschedule means changing an existing appointment. confirm_appointment confirms an existing
  appointment.
- For appointment_list, broad category wording such as asking for "my next laser appointment" must
  not force a service choice from the catalog. Unless one specific service is clearly named, leave
  the service entity null so Python can read the customer's actual appointments first.
- package_info and refund_quote are reads. buy_package is a purchase request. package_usage describes
  whether an appointment should consume an existing package, avoid an existing package, or leaves
  that question unspecified.
- Distinguish a hypothetical financial question from an instruction to reverse a purchased package.
  If the customer is only asking what the refund amount or financial consequence would be if the
  package were cancelled, without authorizing cancellation now, interpret it as refund_quote. If the
  customer is actually asking Tia to carry out cancellation/refund/termination now, interpret it as
  human_support because the agent must not execute purchased-package cancellation.
- clinic_info covers clinic-wide informational/explanatory questions, including policies, general
  service guidance, and comparisons between clinic devices when the question is not about one
  specific service. service_info is for information about one specific service.
- customer_history covers the customer's own prior visits/services/payment facts. A discrepancy or
  contested payment is additionally payment_dispute.
- Medical suitability/symptom questions are medical safety signals; acute/emergency-seeming medical
  situations use urgent_medical. Explicit requests for a person use human_support.
- Resolve clear relative dates against the clinic-local clock. If a date remains semantically
  underspecified, leave it null rather than guessing.
- For clock times, separate semantic meaning from AM/PM resolution. If the customer's wording itself
  fixes the period (for example an explicit morning/evening meaning or an unambiguous 24-hour clock),
  use time_ambiguity=none. If a clock value from 1 through 12 could still semantically mean either
  AM or PM, use time_ambiguity=twelve_hour. Do not use clinic opening hours to hide that ambiguity;
  deterministic Python resolves the two clock candidates against clinic_operating_hours after this
  call. For an ambiguous clock, encode one 12-hour-form candidate such as 08:00 plus
  time_ambiguity=twelve_hour rather than guessing 20:00.
- Apply the same rule independently to start_time_ambiguity/end_time_ambiguity and to a time
  selection's time_ambiguity. Fields unrelated to a time value use none.
- follow_up_at_local is an ISO local datetime only when the customer supplied enough meaning to
  resolve a specific future follow-up time. Otherwise leave it null.
- requested_service_details describes only service facts the customer explicitly asked for in that
  operation: price, duration, description, and/or devices. Here description means clinic-authored
  explanatory guidance from the saved "معلومات Tia" field, not a service-table description. Do not
  add extra details merely because they are available. A pricing operation semantically requests
  price. A generic service-information question requests description unless the customer asks for
  a narrower detail. A request to explain or compare devices for a specific service requests both
  devices and description. Leave requested_service_details empty on unrelated operations.

DATE/TIME REPRESENTATION
- exact date: mode=exact with start_date.
- date range: mode=range with start_date/end_date.
- starting from a date: mode=from_date with start_date.
- nearest available date: mode=next_available with no invented date.
- exact time: mode=exact with start_time.
- after/before constraints: mode=after or mode=before with start_time. After/from a time includes the
  boundary itself; Python treats this lower bound as inclusive.
- time range: mode=range with start_time/end_time.
- nearest time: mode=nearest. Supply start_time only when the customer gives an anchor in this turn;
  on a continuation Python may inherit the previous verified exact-time anchor.

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


def merge_verified_read_context(
    turn: TiaTurnUnderstanding,
    semantic_context: SemanticContext,
) -> TiaTurnUnderstanding:
    """Merge only explicitly-declared continuations with the previous verified read scope."""
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
        if entities.date is None and previous_date is not None:
            updates["date"] = previous_date
        if entities.time is None and previous_time is not None:
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
