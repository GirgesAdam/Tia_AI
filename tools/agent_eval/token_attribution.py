from __future__ import annotations

import json
from typing import Any

import tiktoken
from app.agents.structured_output import canonicalize_provider_json_schema
from app.agents.v2.responder import ResponderDraft
from app.agents.v2.turn_contract import TiaTurnUnderstanding
from langchain_core.messages import BaseMessage

_ENCODING = tiktoken.get_encoding("o200k_base")
_STATE_KEYS = ("active_task", "pending_choice", "recent_verified_read")


def estimate_text_tokens(value: object) -> int:
    if value in (None, ""):
        return 0
    return len(_ENCODING.encode(str(value)))


def estimate_json_tokens(value: object) -> int:
    return estimate_text_tokens(
        json.dumps(
            value,
            ensure_ascii=False,
            default=str,
            separators=(",", ":"),
            sort_keys=True,
        )
    )


def _message_content_tokens(messages: list[BaseMessage]) -> int:
    return sum(estimate_text_tokens(message.content) for message in messages)


def provider_schema_tokens(schema: type) -> int:
    return estimate_json_tokens(
        canonicalize_provider_json_schema(schema.model_json_schema())
    )


def interpreter_attribution(
    *,
    messages: list[BaseMessage],
    model_input: dict[str, object],
) -> dict[str, Any]:
    if len(messages) < 3:
        raise ValueError("Interpreter attribution requires system, context, and user messages.")

    history_messages = messages[2:-1]
    semantic_context_full = messages[1].content
    catalog_only = {
        key: value
        for key, value in model_input.items()
        if key not in _STATE_KEYS
    }
    schema_tokens = provider_schema_tokens(TiaTurnUnderstanding)
    message_tokens = _message_content_tokens(messages)

    return {
        "operation": "v2-turn-interpreter",
        "system_tokens_estimated": estimate_text_tokens(messages[0].content),
        "semantic_context_tokens_estimated": estimate_text_tokens(semantic_context_full),
        "semantic_catalog_tokens_estimated": estimate_json_tokens(catalog_only),
        "conversation_history_tokens_estimated": _message_content_tokens(history_messages),
        "latest_user_tokens_estimated": estimate_text_tokens(messages[-1].content),
        "active_task_tokens_estimated": estimate_json_tokens(model_input.get("active_task"))
        if model_input.get("active_task") not in (None, {}, [])
        else 0,
        "pending_choice_tokens_estimated": estimate_json_tokens(model_input.get("pending_choice"))
        if model_input.get("pending_choice") not in (None, {}, [])
        else 0,
        "recent_verified_read_tokens_estimated": estimate_json_tokens(
            model_input.get("recent_verified_read")
        )
        if model_input.get("recent_verified_read") not in (None, {}, [])
        else 0,
        "grounded_outcome_tokens_estimated": 0,
        "structured_schema_tokens_estimated": schema_tokens,
        "message_tokens_estimated": message_tokens,
        "message_plus_schema_tokens_estimated": message_tokens + schema_tokens,
    }


def responder_attribution(
    *,
    messages: list[BaseMessage],
) -> dict[str, Any]:
    if len(messages) < 3:
        raise ValueError("Responder attribution requires system, outcome, and user messages.")

    history_messages = messages[1:-2]
    outcome_message = messages[-2]
    schema_tokens = provider_schema_tokens(ResponderDraft)
    message_tokens = _message_content_tokens(messages)

    return {
        "operation": "v2-customer-responder",
        "system_tokens_estimated": estimate_text_tokens(messages[0].content),
        "semantic_context_tokens_estimated": 0,
        "semantic_catalog_tokens_estimated": 0,
        "conversation_history_tokens_estimated": _message_content_tokens(history_messages),
        "latest_user_tokens_estimated": estimate_text_tokens(messages[-1].content),
        "active_task_tokens_estimated": 0,
        "pending_choice_tokens_estimated": 0,
        "recent_verified_read_tokens_estimated": 0,
        "grounded_outcome_tokens_estimated": estimate_text_tokens(outcome_message.content),
        "structured_schema_tokens_estimated": schema_tokens,
        "message_tokens_estimated": message_tokens,
        "message_plus_schema_tokens_estimated": message_tokens + schema_tokens,
    }


def attach_actual_usage(
    attribution: dict[str, Any],
    *,
    input_tokens: int,
    output_tokens: int,
    cached_tokens: int,
    total_tokens: int,
    model: str | None,
    latency_ms: int,
    attempt_index: int,
    fallback_used: bool,
    error: str | None = None,
) -> dict[str, Any]:
    output = dict(attribution)
    estimated = int(output.get("message_plus_schema_tokens_estimated") or 0)
    output.update(
        {
            "model": model,
            "input_tokens_actual": int(input_tokens),
            "output_tokens_actual": int(output_tokens),
            "cached_tokens_actual": int(cached_tokens),
            "total_tokens_actual": int(total_tokens),
            "provider_input_minus_estimate": int(input_tokens) - estimated,
            "latency_ms": int(latency_ms),
            "attempt_index": int(attempt_index),
            "retry_count": max(0, int(attempt_index) - 1),
            "fallback_used": bool(fallback_used),
            "error": error,
        }
    )
    return output
