from __future__ import annotations

import json
from datetime import datetime
from typing import Any

from langchain_core.messages import AIMessage, BaseMessage, HumanMessage, SystemMessage

from app.agents.availability_presentation import customer_visible_verified_data
from app.agents.llm_runtime import LLMProviderError, invoke_model, invoke_with_model_chain
from app.agents.model_provider import (
    build_realtime_composer_fallback_model,
    build_realtime_composer_model,
    model_label,
)
from app.core.config import settings


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


def _recent_history(history: list[BaseMessage], *, limit: int = 6) -> str:
    lines: list[str] = []
    for message in history[-limit:]:
        if not isinstance(message.content, str) or not message.content.strip():
            continue
        role = "customer" if isinstance(message, HumanMessage) else "assistant"
        text = " ".join(message.content.strip().split())
        lines.append(f"{role}: {text[:900]}")
    return "\n".join(lines)


def compose_grounded_customer_reply(
    *,
    clinic_name: str,
    timezone_name: str,
    local_now: datetime,
    history: list[BaseMessage],
    semantic_decision: Any,
    verified_data: dict[str, Any],
) -> tuple[str, str]:
    """Generate customer-facing language from verified structured facts only.

    The model is not allowed to choose tools, mutate state, or invent clinic facts.
    Python/PostgreSQL have already selected/validated the data and execution result.
    """
    system = SystemMessage(
        content=(
            "You are Tia's customer-facing response composer for an aesthetic clinic. "
            "Write one concise, natural reply to the customer. If the customer writes Arabic, "
            "reply in natural Egyptian Arabic. You are a language layer only: do not route, "
            "do not call tools, do not authorize actions, and do not infer clinic facts outside "
            "VERIFIED_DATA.\n\n"
            "GROUNDING RULES:\n"
            "- Every factual claim about services, prices, durations, doctors, branches, dates, "
            "times, availability, appointment status, or completed actions MUST come from VERIFIED_DATA.\n"
            "- Never print internal UUIDs or implementation metadata.\n"
            "- The customer experience is single-location. Never mention or ask about branches; "
            "storage-level branch data is internal only.\n"
            "- When availability_windows are provided, summarize those natural continuous windows "
            "per doctor instead of listing dense quarter-hour slot starts.\n"
            "- If VERIFIED_DATA contains multiple candidate services/doctors/branches, present all "
            "provided relevant options clearly and ask the customer to choose. Do not silently pick one.\n"
            "- If an exact requested time is unavailable and alternatives are provided, say it is "
            "unavailable and list only the supplied alternatives.\n"
            "- If an action result says a booking is pending confirmation, do not claim it is confirmed.\n"
            "- If the verified facts are insufficient, ask one focused clarification question instead "
            "of guessing.\n"
            "- Medical safety/handoff decisions supplied by the orchestrator take priority.\n\n"
            f"Clinic: {clinic_name}\n"
            f"Clinic timezone: {timezone_name}\n"
            f"Clinic local time: {local_now.isoformat()}"
        )
    )
    payload = {
        "semantic": {
            "capabilities": list(getattr(semantic_decision, "capabilities", []) or []),
            "risk_flags": list(getattr(semantic_decision, "risk_flags", []) or []),
            "missing_information": list(
                getattr(semantic_decision, "missing_information", []) or []
            ),
        },
        "verified_data": customer_visible_verified_data(verified_data),
    }
    user = HumanMessage(
        content=(
            "Recent conversation:\n"
            f"{_recent_history(history)}\n\n"
            "VERIFIED_DATA (source of truth; internal IDs must not be shown):\n"
            f"{json.dumps(payload, ensure_ascii=False, default=str, separators=(',', ':'))}"
        )
    )
    messages = [system, user]

    primary_name = settings.gemini_realtime_composer_model
    fallback_name = settings.gemini_realtime_composer_fallback_model
    primary = build_realtime_composer_model()
    fallback_model = None

    def primary_call() -> AIMessage:
        return invoke_model(lambda: primary.invoke(messages))

    def fallback_call() -> AIMessage:
        nonlocal fallback_model
        if fallback_model is None:
            fallback_model = build_realtime_composer_fallback_model()
        if fallback_model is None:
            raise RuntimeError("Grounded response fallback model is not configured.")
        return invoke_model(lambda: fallback_model.invoke(messages))

    model_calls = [(primary_name, primary_call)]
    if fallback_name and fallback_name != primary_name:
        model_calls.append((fallback_name, fallback_call))

    invocation = invoke_with_model_chain(
        model_calls=model_calls,
        operation="grounded-response-composer",
        circuit_breaker_cooldown_seconds=settings.llm_realtime_circuit_breaker_cooldown_seconds,
    )
    text = _extract_text(invocation.value)
    if not text:
        raise LLMProviderError(
            "Grounded response composer returned no customer-visible text.",
            retryable=False,
        )
    return text, model_label(invocation.model_name)
