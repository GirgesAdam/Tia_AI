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
    "clinic_information",
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
    "appointment_id",
]


def _require_all_schema_fields(schema: dict) -> None:
    properties = schema.get("properties")
    if isinstance(properties, dict):
        schema["required"] = list(properties)


class SemanticEntityHints(BaseModel):
    model_config = ConfigDict(
        extra="forbid", json_schema_extra=_require_all_schema_fields
    )

    service_query: str | None = Field(
        default=None,
        description=(
            "Service wording intended by the latest customer turn. If the latest turn replaces "
            "a service from persisted workflow state, reflect the new service wording here and "
            "never copy the old service wording merely because it is stored in the flow."
        ),
    )
    branch_query: str | None
    doctor_query: str | None
    service_id: str | None = Field(
        default=None,
        description=(
            "Canonical service UUID from the supplied clinic catalog for the service intended by "
            "the latest customer turn. If the latest wording plausibly matches multiple service "
            "variants, leave this null and return those UUIDs in service_candidate_ids instead of "
            "reusing a persisted older service UUID."
        ),
    )
    service_candidate_ids: list[str] = Field(
        default_factory=list,
        description=(
            "All plausible service UUIDs for the latest customer turn when no single service is "
            "selected; use this for ambiguous service variants rather than keeping an older service."
        ),
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
    appointment_id: str | None = Field(
        default=None,
        description=(
            "Canonical ID of the EXISTING appointment being acted on, selected only from the "
            "supplied current-patient appointment catalog. In a reschedule flow this identifies "
            "the old appointment; replacement date/time/service belong in the other fields."
        ),
    )
    requested_date: str | None = Field(
        default=None,
        description=(
            "Desired appointment date YYYY-MM-DD from the latest customer turn. In a reschedule "
            "flow this is always the NEW target date, never the date of the existing appointment "
            "being changed. Use appointment_reference for the existing appointment."
        ),
    )
    requested_start_time: str | None = Field(
        default=None,
        description=(
            "Exact local appointment start HH:MM intended by the latest customer turn. In a "
            "reschedule flow this is the NEW target start time. Preserve an explicit exact clock "
            "time from the latest turn even when older exact/before/after constraints exist in "
            "workflow state; otherwise null."
        ),
    )
    not_before_time: str | None = Field(
        description="Local HH:MM when semantically resolved, otherwise null."
    )
    not_after_time: str | None = Field(
        description="Local HH:MM when semantically resolved, otherwise null."
    )
    appointment_reference: str | None = Field(
        default=None,
        description=(
            "Reference that identifies the EXISTING appointment being acted on, such as its "
            "current date/time or other customer-facing description. Never put the replacement "
            "reschedule target here; replacement date/time belong in requested_date and "
            "requested_start_time."
        ),
    )


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