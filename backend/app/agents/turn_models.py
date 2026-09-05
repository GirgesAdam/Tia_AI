from __future__ import annotations

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
