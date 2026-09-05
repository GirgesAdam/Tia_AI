from __future__ import annotations

from datetime import datetime

from langchain_core.messages import BaseMessage

from app.agents.turn_models import (
    FlowSignal,
    HandoffCategory,
    PackageIntent,
    Priority,
    RiskFlag,
    SemanticCapability,
    SemanticCapabilityDecision,
    SemanticDomain,
    SemanticEntityHints,
    _require_all_schema_fields,
    empty_entity_hints,
)

__all__ = [
    "FlowSignal",
    "HandoffCategory",
    "PackageIntent",
    "Priority",
    "RiskFlag",
    "SemanticCapability",
    "SemanticCapabilityDecision",
    "SemanticDomain",
    "SemanticEntityHints",
    "_require_all_schema_fields",
    "empty_entity_hints",
    "route_customer_message",
]


def route_customer_message(
    *,
    history: list[BaseMessage],
    timezone_name: str,
    local_now: datetime,
) -> SemanticCapabilityDecision:
    del history, timezone_name, local_now
    raise RuntimeError(
        "Legacy semantic router removed; use turn_interpreter.interpret_customer_turn."
    )
