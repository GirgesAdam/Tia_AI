from __future__ import annotations

from datetime import datetime

from langchain_core.messages import BaseMessage

from app.agents.turn_models import (
    ClearableFlowEntity,
    FlowTurnAction,
    FlowTurnDecision,
)
from app.models.conversation_flow_state import ConversationFlowState

__all__ = [
    "ClearableFlowEntity",
    "FlowTurnAction",
    "FlowTurnDecision",
    "interpret_active_flow_turn",
]


def interpret_active_flow_turn(
    *,
    flow: ConversationFlowState,
    history: list[BaseMessage],
    timezone_name: str,
    local_now: datetime,
) -> FlowTurnDecision:
    del flow, history, timezone_name, local_now
    raise RuntimeError(
        "Legacy flow interpreter removed; use turn_interpreter.interpret_customer_turn."
    )
