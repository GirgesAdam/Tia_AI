from __future__ import annotations

import json
from datetime import datetime

from langchain_core.messages import AIMessage, BaseMessage, HumanMessage, SystemMessage

from app.agents.llm_runtime import LLMProviderError, invoke_model, invoke_with_model_chain
from app.agents.model_provider import (
    build_realtime_composer_fallback_model,
    build_realtime_composer_model,
    model_label,
)
from app.core.config import settings
from app.services.agent_v2.outcome import TurnOutcome
from app.services.agent_v2.outcome_builder import customer_visible_outcome


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


def _native_recent_messages(
    history: list[BaseMessage],
    *,
    latest_customer_index: int,
    limit: int = 8,
) -> list[BaseMessage]:
    selected: list[BaseMessage] = []
    for message in history[:latest_customer_index]:
        if not isinstance(message, (HumanMessage, AIMessage)):
            continue
        text = _message_text(message, limit=900)
        if not text:
            continue
        selected.append(
            HumanMessage(content=text) if isinstance(message, HumanMessage) else AIMessage(content=text)
        )
    return selected[-limit:]


def _system_prompt(*, clinic_name: str, timezone_name: str, local_now: datetime) -> str:
    return f"""You are Tia, the customer-facing assistant for an aesthetic clinic.
Write one natural, concise reply that continues the actual conversation. If the latest customer
message is Arabic, use natural Egyptian Arabic. If it is English, reply in natural English.

You are a language layer only. You do not choose tools, route requests, authorize actions, mutate
state, calculate business facts, or decide whether an action happened. TURN_OUTCOMES are the source
of truth for this reply.

RULES
- Never invent or infer clinic facts, prices, durations, doctors, availability, appointment state,
  package balances, payment facts, or action results beyond TURN_OUTCOMES.
- Never claim a booking, reschedule, cancellation, confirmation, package purchase, follow-up, or
  marketing change succeeded unless the corresponding outcome says status=completed and its
  action_result confirms success.
- If an outcome says needs_input, ask only the focused missing detail. If verified choices are
  supplied, present those choices naturally without exposing refs or internal metadata.
- If an outcome is blocked, say what is known and what the customer can do next without pretending
  the requested action succeeded.
- If handoff is required, communicate that clearly and briefly. For urgent medical situations, do
  not diagnose; advise urgent emergency help when the supplied outcome indicates urgent medical
  escalation.
- Never expose UUIDs, database IDs, reference tokens, internal fields, implementation details, or
  branch/storage metadata. The customer experience is single-location; do not ask about branches.
- Use recent dialogue for continuity. Do not restart the conversation, repeat a greeting, or use a
  stock opener/closer on every turn. Answer the customer's direct question before optional detail.
- Combine multiple TURN_OUTCOMES into one coherent reply in customer-request order. Do not send one
  mini-reply per operation.
- If the structured facts are insufficient, say so or ask the one required clarification instead of
  guessing.

Clinic: {clinic_name}
Clinic timezone: {timezone_name}
Clinic local time: {local_now.isoformat()}
"""


def _build_responder_messages(
    *,
    clinic_name: str,
    timezone_name: str,
    local_now: datetime,
    history: list[BaseMessage],
    outcomes: list[TurnOutcome],
) -> list[BaseMessage]:
    latest_index = _latest_customer_index(history)
    if latest_index is None:
        raise ValueError("V2 responder requires a customer message.")
    if not outcomes:
        raise ValueError("V2 responder requires at least one structured outcome.")

    latest_text = _message_text(history[latest_index])
    visible_outcomes = [customer_visible_outcome(outcome) for outcome in outcomes]
    outcome_message = SystemMessage(
        content=(
            "TURN_OUTCOMES (authoritative customer-visible business result):\n"
            + json.dumps(
                visible_outcomes,
                ensure_ascii=False,
                default=str,
                separators=(",", ":"),
            )
        )
    )
    return [
        SystemMessage(
            content=_system_prompt(
                clinic_name=clinic_name,
                timezone_name=timezone_name,
                local_now=local_now,
            )
        ),
        *_native_recent_messages(history, latest_customer_index=latest_index),
        outcome_message,
        HumanMessage(content=latest_text),
    ]


def _extract_text(message: AIMessage) -> str:
    if isinstance(message.content, str):
        return message.content.strip()
    parts: list[str] = []
    if isinstance(message.content, list):
        for block in message.content:
            if isinstance(block, str):
                parts.append(block)
                continue
            if isinstance(block, dict):
                text = block.get("text") or block.get("content")
                if isinstance(text, str):
                    parts.append(text)
    return "\n".join(part.strip() for part in parts if part.strip()).strip()


def compose_v2_customer_reply(
    *,
    clinic_name: str,
    timezone_name: str,
    local_now: datetime,
    history: list[BaseMessage],
    outcomes: list[TurnOutcome],
) -> tuple[str, str]:
    """Render one customer reply from verified V2 outcomes; never execute actions or tools."""
    messages = _build_responder_messages(
        clinic_name=clinic_name,
        timezone_name=timezone_name,
        local_now=local_now,
        history=history,
        outcomes=outcomes,
    )

    primary_name = settings.openai_model
    fallback_name = settings.openai_fallback_model
    primary = build_realtime_composer_model()
    fallback_model = None

    def primary_call() -> AIMessage:
        return invoke_model(lambda: primary.invoke(messages))

    def fallback_call() -> AIMessage:
        nonlocal fallback_model
        if fallback_model is None:
            fallback_model = build_realtime_composer_fallback_model()
        if fallback_model is None:
            raise RuntimeError("V2 responder fallback model is not configured.")
        return invoke_model(lambda: fallback_model.invoke(messages))

    model_calls = [(primary_name, primary_call)]
    if fallback_name and fallback_name != primary_name:
        model_calls.append((fallback_name, fallback_call))

    invocation = invoke_with_model_chain(
        model_calls=model_calls,
        operation="v2-customer-responder",
        circuit_breaker_cooldown_seconds=settings.llm_realtime_circuit_breaker_cooldown_seconds,
    )
    text = _extract_text(invocation.value)
    if not text:
        raise LLMProviderError(
            "V2 responder returned no customer-visible text.",
            retryable=False,
        )
    return text, model_label(invocation.model_name)
