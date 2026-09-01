from __future__ import annotations

import json
from datetime import datetime
from typing import Literal

from langchain_core.messages import BaseMessage, HumanMessage, SystemMessage
from pydantic import BaseModel, ConfigDict, Field

from app.agents.llm_runtime import invoke_with_fallback
from app.agents.model_provider import (
    build_flow_interpreter_fallback_model,
    build_flow_interpreter_model,
)
from app.agents.semantic_router import (
    HandoffCategory,
    Priority,
    RiskFlag,
    SemanticCapability,
    SemanticEntityHints,
    _require_all_schema_fields,
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

ClearableFlowEntity = Literal[
    "service_query",
    "service_id",
    "service_candidate_ids",
    "branch_query",
    "branch_id",
    "branch_candidate_ids",
    "doctor_query",
    "doctor_id",
    "doctor_candidate_ids",
    "requested_date",
    "requested_start_time",
    "not_before_time",
    "not_after_time",
    "appointment_reference",
]


class FlowTurnDecision(BaseModel):
    model_config = ConfigDict(
        extra="forbid", json_schema_extra=_require_all_schema_fields
    )

    action: FlowTurnAction
    capabilities: list[SemanticCapability]
    risk_flags: list[RiskFlag]
    entity_hints: SemanticEntityHints
    clear_entity_fields: list[ClearableFlowEntity] = Field(default_factory=list)
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
    timezone_name: str,
    local_now: datetime,
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

        choice_specs = (
            ("services", ("service_name", "name")),
            ("branches", ("branch_name", "name")),
            ("doctors", ("doctor_name", "name")),
        )
        for collection_name, name_keys in choice_specs:
            choices = flow.option_snapshot.get(collection_name)
            if not isinstance(choices, list):
                continue
            summarized = []
            for index, choice in enumerate(choices[:8]):
                if not isinstance(choice, dict):
                    continue
                display_name = next(
                    (choice.get(key) for key in name_keys if choice.get(key)),
                    None,
                )
                summarized.append({"index": index + 1, "name": display_name})
            if summarized:
                option_summary[collection_name] = summarized

    system = SystemMessage(
        content=(
            "You interpret the customer's newest turn inside an active Tia clinic "
            "workflow. Return only the structured schema. Never answer the customer "
            "and never return implementation tool names.\n\n"
            "IMPORTANT OUTPUT CONTRACT: every schema field must be present. "
            "Use null for unresolved optional scalar values and [] for empty lists, "
            "including clear_entity_fields when nothing should be cleared.\n\n"
            "Actions:\n"
            "- continue: keep the workflow and answer/collect information without "
            "changing the existing requirements materially.\n"
            "- modify: customer changes date/service/doctor/branch/time requirements.\n"
            "- select_option: customer clearly chooses one of the options already "
            "presented. Populate selection_index or selection_time when resolvable. "
            "This can be a prerequisite choice (service/branch/doctor) or a final slot. "
            "A final slot selection authorizes execution; a prerequisite selection only "
            "updates the workflow requirements and must not execute a booking yet.\n"
            "- cancel_flow: customer wants to stop this workflow without cancelling an "
            "already-existing appointment unless that separate capability is explicit.\n"
            "- interrupt: medical/safety/human-support or a clearly separate task should "
            "take ownership from the current workflow.\n\n"
            "A harmless side question related to the same booking can stay continue "
            "with extra semantic capabilities. A separate request for the clinic to contact "
            "the customer later should include follow_up_request and normally interrupt the "
            "booking flow instead of silently changing booking requirements. Medical risk "
            "always sets risk_flags.\n\n"
            "Requirement relaxation:\n"
            "- clear_entity_fields is the semantic way to remove a requirement that was "
            "stored from an earlier turn. Do not use it merely because the newest message "
            "does not repeat a known requirement.\n"
            "- If the customer broadens availability after an exact time failed (for example "
            "asks to see other times in the same day), keep the existing service/branch/doctor/date "
            "and clear requested_start_time plus any obsolete not_before_time/not_after_time bounds.\n"
            "- If the customer replaces one time constraint with another, populate the new bound "
            "and clear any old incompatible bound.\n"
            "- Never clear a requirement unless the newest turn semantically relaxes, removes, or "
            "replaces it. This decision is semantic, not keyword-based.\n\n"
            f"Clinic timezone: {timezone_name}\n"
            f"Clinic local date/time now: {local_now.isoformat()}\n"
            "Resolve relative date/time language against this clinic-local clock. If a "
            "customer says a clear relative date such as tomorrow/بكرة while modifying "
            "or continuing the flow, put the resolved YYYY-MM-DD in entity_hints.requested_date. "
            "Resolve clear local times to HH:MM. Exact-start semantics are separate from "
            "time windows: 'at 6 PM' / 'الساعة 6' => requested_start_time='18:00'; "
            "'after 6' => not_before_time='18:00'; 'before 8' => not_after_time='20:00'; "
            "'from 6 to 8' => both bounds. Never encode an exact start as equal lower/upper "
            "bounds. Do not infer an ambiguous date."
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

    primary_model = build_flow_interpreter_model()
    fallback_name = settings.gemini_flow_fallback_model

    def invoke_fallback():
        fallback_model = build_flow_interpreter_fallback_model()
        if fallback_model is None:
            raise RuntimeError("Flow interpreter fallback model is not configured.")
        return invoke_typed_structured_output(
            model=fallback_model,
            schema=FlowTurnDecision,
            messages=[system, state],
        )

    has_fallback = bool(fallback_name and fallback_name != settings.gemini_flow_model)
    invocation = invoke_with_fallback(
        primary_call=lambda: invoke_typed_structured_output(
            model=primary_model,
            schema=FlowTurnDecision,
            messages=[system, state],
        ),
        primary_model_name=settings.gemini_flow_model,
        fallback_call=invoke_fallback if has_fallback else None,
        fallback_model_name=fallback_name if has_fallback else None,
        operation="flow-interpreter",
        circuit_breaker_cooldown_seconds=settings.llm_realtime_circuit_breaker_cooldown_seconds,
    )
    return invocation.value
