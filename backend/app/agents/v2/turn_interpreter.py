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
from app.agents.v2.turn_contract import TiaTurnUnderstanding
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
  pending choice, and supplied semantic catalog references. Do not route by lexical triggers,
  memorized keywords, or phrase matching.
- Select only supplied entity references. If one entity is clearly intended, set ref. If multiple
  supplied entities remain genuinely possible, leave ref null and use candidate_refs. Never invent
  a reference.
- Preserve multi-part requests as multiple operations in customer order when they are independently
  meaningful. Alternatives are not multiple operations.
- A read request never becomes a write request merely because the requested action could be
  executed.
- A harmless informational/social side turn must not be interpreted as cancelling an active task.
- When a customer corrects or changes a requirement in an active task, represent the new semantic
  value only. Python owns dependency invalidation and persisted-state changes.
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
    grounded = ground_turn_references(invocation.value, semantic_context)
    return resolve_turn_times_by_clinic_hours(grounded, semantic_context)
