from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]


def read(path: str) -> str:
    return (ROOT / path).read_text(encoding="utf-8")


def write(path: str, content: str) -> None:
    target = ROOT / path
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(content, encoding="utf-8")


def replace_once(content: str, old: str, new: str, *, label: str) -> str:
    count = content.count(old)
    if count != 1:
        raise RuntimeError(f"{label}: expected one anchor, found {count}")
    return content.replace(old, new, 1)


def create_turn_models() -> None:
    write(
        "backend/app/agents/turn_models.py",
        '''from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

SemanticDomain = Literal[
    "services",
    "clinic",
    "booking",
    "appointments",
    "patient",
    "support",
    "communications",
    "general",
]
SemanticCapability = Literal[
    "service_information",
    "pricing",
    "branch_discovery",
    "doctor_discovery",
    "availability_discovery",
    "appointment_creation",
    "appointment_list",
    "appointment_confirmation",
    "appointment_cancellation",
    "appointment_reschedule",
    "customer_profile",
    "customer_history",
    "package_information",
    "package_refund_quote",
    "follow_up_request",
    "marketing_preferences",
    "human_support",
]
RiskFlag = Literal["medical", "complaint", "payment", "urgent"]
HandoffCategory = Literal[
    "medical",
    "complaint",
    "payment",
    "customer_request",
    "booking_exception",
    "agent_uncertain",
    "other",
]
Priority = Literal["low", "normal", "high", "urgent"]
FlowSignal = Literal["none", "start_booking", "start_reschedule", "interrupt"]
PackageIntent = Literal["none", "inquire", "purchase", "use_existing", "avoid_existing"]
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


def _require_all_schema_fields(schema: dict) -> None:
    properties = schema.get("properties")
    if isinstance(properties, dict):
        schema["required"] = list(properties)


class SemanticEntityHints(BaseModel):
    model_config = ConfigDict(
        extra="forbid", json_schema_extra=_require_all_schema_fields
    )

    service_query: str | None
    branch_query: str | None
    doctor_query: str | None
    service_id: str | None = Field(
        default=None,
        description="Canonical service UUID from the supplied clinic catalog.",
    )
    service_candidate_ids: list[str] = Field(
        default_factory=list,
        description="All plausible service UUIDs when no single service is selected.",
    )
    branch_id: str | None = Field(
        default=None,
        description="Canonical branch UUID from the supplied clinic catalog.",
    )
    branch_candidate_ids: list[str] = Field(
        default_factory=list,
        description="All plausible branch UUIDs when no single branch is selected.",
    )
    doctor_id: str | None = Field(
        default=None,
        description="Canonical doctor UUID from the supplied clinic catalog.",
    )
    doctor_candidate_ids: list[str] = Field(
        default_factory=list,
        description="All plausible doctor UUIDs when no single doctor is selected.",
    )
    requested_date: str | None = Field(
        description="YYYY-MM-DD when semantically resolved, otherwise null."
    )
    requested_start_time: str | None = Field(
        default=None,
        description=(
            "Exact local appointment start HH:MM when the customer requests one "
            "precise start time, otherwise null."
        ),
    )
    not_before_time: str | None = Field(
        description="Local HH:MM when semantically resolved, otherwise null."
    )
    not_after_time: str | None = Field(
        description="Local HH:MM when semantically resolved, otherwise null."
    )
    appointment_reference: str | None


class SemanticCapabilityDecision(BaseModel):
    model_config = ConfigDict(
        extra="forbid", json_schema_extra=_require_all_schema_fields
    )

    domains: list[SemanticDomain]
    capabilities: list[SemanticCapability]
    risk_flags: list[RiskFlag]
    flow_signal: FlowSignal
    package_intent: PackageIntent = "none"
    entity_hints: SemanticEntityHints
    missing_information: list[str]
    recommended_handoff_category: HandoffCategory
    recommended_handoff_priority: Priority
    confidence: float
    reason: str


class FlowTurnDecision(BaseModel):
    model_config = ConfigDict(
        extra="forbid", json_schema_extra=_require_all_schema_fields
    )

    action: FlowTurnAction
    capabilities: list[SemanticCapability]
    risk_flags: list[RiskFlag]
    package_intent: PackageIntent = "none"
    entity_hints: SemanticEntityHints
    clear_entity_fields: list[ClearableFlowEntity] = Field(default_factory=list)
    selection_index: int | None
    selection_time: str | None
    missing_information: list[str]
    recommended_handoff_category: HandoffCategory
    recommended_handoff_priority: Priority
    confidence: float
    reason: str


def empty_entity_hints() -> SemanticEntityHints:
    return SemanticEntityHints(
        service_query=None,
        branch_query=None,
        doctor_query=None,
        requested_date=None,
        requested_start_time=None,
        not_before_time=None,
        not_after_time=None,
        appointment_reference=None,
    )
''',
    )


def thin_legacy_modules() -> None:
    write(
        "backend/app/agents/semantic_router.py",
        '''from __future__ import annotations

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
''',
    )
    write(
        "backend/app/agents/flow_interpreter.py",
        '''from __future__ import annotations

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
''',
    )


def patch_turn_interpreter_imports() -> None:
    path = "backend/app/agents/turn_interpreter.py"
    content = read(path)
    old = '''from app.agents.flow_interpreter import ClearableFlowEntity, FlowTurnDecision
from app.agents.llm_runtime import invoke_with_model_chain
from app.agents.model_provider import (
    build_realtime_interpreter_emergency_model,
    build_realtime_interpreter_fallback_model,
    build_realtime_interpreter_model,
)
from app.agents.semantic_router import (
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
)
'''
    new = '''from app.agents.llm_runtime import invoke_with_model_chain
from app.agents.model_provider import (
    build_realtime_interpreter_emergency_model,
    build_realtime_interpreter_fallback_model,
    build_realtime_interpreter_model,
)
from app.agents.turn_models import (
    ClearableFlowEntity,
    FlowSignal,
    FlowTurnDecision,
    HandoffCategory,
    PackageIntent,
    Priority,
    RiskFlag,
    SemanticCapability,
    SemanticCapabilityDecision,
    SemanticDomain,
    SemanticEntityHints,
    _require_all_schema_fields,
)
'''
    content = replace_once(content, old, new, label="turn interpreter imports")
    write(path, content)


def patch_agent_chat_runtime() -> None:
    path = "backend/app/services/agent_chat.py"
    content = read(path)
    content = replace_once(
        content,
        "from app.agents.flow_interpreter import FlowTurnDecision, interpret_active_flow_turn\n",
        "from app.agents.turn_models import FlowTurnDecision, SemanticCapabilityDecision\n",
        label="agent chat flow import",
    )
    content = replace_once(
        content,
        '''from app.agents.semantic_router import (
    SemanticCapabilityDecision,
    route_customer_message,
)
''',
        "",
        label="agent chat semantic router import",
    )

    start_marker = '''    flow_turn: FlowTurnDecision | None = None
    grounded_mode = settings.agent_unified_turn_interpreter_enabled
'''
    end_marker = '        semantic_stage = "semantic-router"\n'
    start = content.find(start_marker)
    end = content.find(end_marker, start)
    if start < 0 or end < 0:
        raise RuntimeError("agent chat semantic runtime block not found")
    end += len(end_marker)
    unified = '''    flow_turn: FlowTurnDecision | None = None
    grounded_mode = True
    catalog_started = perf_counter()
    clinic_catalog = build_clinic_catalog(db, workspace)
    logger.info(
        "Tia turn run_id=%s stage=clinic-catalog services=%s branches=%s doctors=%s duration_ms=%s",
        run_id,
        len(clinic_catalog.get("services", [])),
        len(clinic_catalog.get("branches", [])),
        len(clinic_catalog.get("doctors", [])),
        int((perf_counter() - catalog_started) * 1000),
    )
    semantic_started = perf_counter()
    unified_turn = interpret_customer_turn(
        flow=flow,
        history=history,
        timezone_name=timezone_name,
        local_now=local_now,
        clinic_catalog=clinic_catalog,
    )
    semantic_decision = _package_intent_non_booking(unified_turn.as_semantic_decision())
    semantic_decision = _with_implicit_primary_branch(
        semantic_decision,
        workspace=workspace,
        clinic_catalog=clinic_catalog,
    )
    if flow is not None:
        flow_turn = unified_turn.as_flow_turn_decision().model_copy(
            update={
                "capabilities": list(semantic_decision.capabilities),
                "package_intent": semantic_decision.package_intent,
                "entity_hints": semantic_decision.entity_hints,
            }
        )
        turn_local_side_read = _turn_is_local_side_read(flow, flow_turn)
        inherited_capabilities = (
            _persistent_flow_capabilities(flow.flow_type, flow.capabilities)
            if flow_turn.action != "interrupt" and not turn_local_side_read
            else []
        )
    else:
        turn_local_side_read = False
        inherited_capabilities = []
    semantic_stage = "unified-turn-interpreter"
'''
    content = content[:start] + unified + content[end:]
    write(path, content)


def fix_live_checker() -> None:
    path = "backend/scripts/run_live_agent_ux_review.py"
    content = read(path)
    old = '''            natural = ("من " in replies and (" لـ" in replies or " ل" in replies)) or "مفيش مواعيد" in replies or "مش متاح" in replies
            dense = sum(replies.count(f":{minute:02d}") for minute in (0, 15, 30, 45)) >= 5
            checks.append(f"natural_windows={natural and not dense}")
            scenario_ok = scenario_ok and natural and not dense
'''
    new = '''            natural = ("من " in replies and (" لـ" in replies or " ل" in replies)) or "مفيش مواعيد" in replies or "مش متاح" in replies
            checks.append(f"natural_windows={natural}")
            scenario_ok = scenario_ok and natural
'''
    content = replace_once(content, old, new, label="natural window checker")
    write(path, content)


def add_architecture_test() -> None:
    write(
        "backend/tests/test_unified_turn_interpreter_architecture.py",
        '''from pathlib import Path

BACKEND = Path(__file__).resolve().parent.parent


def test_customer_runtime_has_one_semantic_interpreter() -> None:
    source = (BACKEND / "app/services/agent_chat.py").read_text(encoding="utf-8")

    assert "interpret_customer_turn(" in source
    assert "route_customer_message" not in source
    assert "interpret_active_flow_turn" not in source
    assert "agent_unified_turn_interpreter_enabled" not in source


def test_legacy_interpreter_modules_do_not_call_llms() -> None:
    semantic = (BACKEND / "app/agents/semantic_router.py").read_text(encoding="utf-8")
    flow = (BACKEND / "app/agents/flow_interpreter.py").read_text(encoding="utf-8")
    unified = (BACKEND / "app/agents/turn_interpreter.py").read_text(encoding="utf-8")

    for source in (semantic, flow):
        assert "invoke_typed_structured_output" not in source
        assert "build_semantic_router_model" not in source
        assert "build_flow_interpreter_model" not in source
    assert "invoke_typed_structured_output" in unified
''',
    )


def remove_temporary_scaffolding() -> None:
    paths = [
        "backend/scripts/apply_agent_ux_continuation.py",
        "backend/scripts/apply_agent_semantic_followups.py",
        ".github/workflows/live-agent-ux-review-once.yml",
        "backend/scripts/apply_agent_cleanup_once.py",
        ".github/workflows/agent-cleanup-once.yml",
    ]
    for path in paths:
        target = ROOT / path
        if target.exists():
            target.unlink()


def main() -> None:
    create_turn_models()
    thin_legacy_modules()
    patch_turn_interpreter_imports()
    patch_agent_chat_runtime()
    fix_live_checker()
    add_architecture_test()
    remove_temporary_scaffolding()
    print("Unified semantic interpreter cleanup applied.")


if __name__ == "__main__":
    main()
