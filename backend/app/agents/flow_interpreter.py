from __future__ import annotations

import json
from typing import Literal

from langchain_core.messages import BaseMessage, HumanMessage, SystemMessage
from pydantic import BaseModel, ConfigDict

from app.agents.model_provider import build_flow_interpreter_model
from app.agents.semantic_router import (
    HandoffCategory,
    Priority,
    RiskFlag,
    SemanticCapability,
    SemanticEntityHints,
)
from app.agents.structured_output import invoke_typed_structured_output
from app.core.config import settings
from app.models.conversation_flow_state import ConversationFlowState


FlowTurnAction = Literal[
    "continue",
    "modify",
    "select_option",
    "cancel_flow",
    "interrupt",
]


class FlowTurnDecision(BaseModel):
    model_config = ConfigDict(extra="forbid")

    action: FlowTurnAction
    capabilities: list[SemanticCapability]
    risk_flags: list[RiskFlag]
    entity_hints: SemanticEntityHints
    selection_index: int | None
    selection_time: str | None
    missing_information: list[str]
    recommended_handoff_category: HandoffCategory
    recommended_handoff_priority: Priority
    confidence: float
    reason: str


def _history_excerpt(history: list[BaseMessage]) -> str:
    selected = history[-settings.agent_flow_interpreter_history_messages :]
    lines: list[str] = []
    for message in selected:
        if not isinstance(message.content, str) or not message.content.strip():
            continue
        text = " ".join(message.content.strip().split())
        lines.append(text[:700] + ("…" if len(text) > 700 else ""))
    return "\n".join(lines)


def interpret_active_flow_turn(
    *,
    flow: ConversationFlowState,
    history: list[BaseMessage],
) -> FlowTurnDecision:
    """
    Interpret a turn inside an existing workflow semantically.

    No lexical shortcut determines whether the customer selected a slot,
    changed requirements, cancelled the flow, or interrupted for safety.
    """
    option_summary = {}
    if isinstance(flow.option_snapshot, dict):
        slots = flow.option_snapshot.get("slots")
        if isinstance(slots, list):
            option_summary["slots"] = [
                {
                    "index": index + 1,
                    "start_time_24h": slot.get("start_time_24h"),
                    "end_time_24h": slot.get("end_time_24h"),
                    "doctor_name": slot.get("doctor_name"),
                    "branch_name": slot.get("branch_name"),
                }
                for index, slot in enumerate(slots[:8])
                if isinstance(slot, dict)
            ]

    system = SystemMessage(
        content=(
            "You interpret the customer's newest turn inside an active Tia clinic "
            "workflow. Return only the structured schema. Never answer the customer "
            "and never return implementation tool names.\n\n"
            "IMPORTANT OUTPUT CONTRACT: every schema field must be present. "
            "Use null for unresolved optional scalar values and [] for empty lists.\n\n"
            "Actions:\n"
            "- continue: keep the workflow and answer/collect information without "
            "changing the existing requirements materially.\n"
            "- modify: customer changes date/service/doctor/branch/time requirements.\n"
            "- select_option: customer clearly chooses one of the options already "
            "presented. Populate selection_index or selection_time when resolvable. "
            "A clear selection authorizes execution; do not invent another confirmation.\n"
            "- cancel_flow: customer wants to stop this workflow without cancelling an "
            "already-existing appointment unless that separate capability is explicit.\n"
            "- interrupt: medical/safety/human-support or a clearly separate task should "
            "take ownership from the current workflow.\n\n"
            "A harmless side question related to the same booking can stay continue "
            "with extra semantic capabilities. Medical risk always sets risk_flags."
        )
    )

    state = HumanMessage(
        content=(
            f"flow_type={flow.flow_type}\n"
            f"flow_status={flow.status}\n"
            f"flow_capabilities={json.dumps(flow.capabilities, ensure_ascii=False)}\n"
            f"entity_state={json.dumps(flow.entity_state, ensure_ascii=False)}\n"
            f"missing_information={json.dumps(flow.missing_information, ensure_ascii=False)}\n"
            f"options={json.dumps(option_summary, ensure_ascii=False)}\n\n"
            "Recent conversation:\n"
            f"{_history_excerpt(history)}"
        )
    )

    return invoke_typed_structured_output(
        model=build_flow_interpreter_model(),
        schema=FlowTurnDecision,
        messages=[system, state],
    )
