from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

from app.services.laser_booking_context import set_laser_device_key

SemanticDomain = Literal[
    "services", "clinic", "booking", "appointments", "patient", "support", "communications", "general"
]
SemanticCapability = Literal[
    "service_information", "clinic_information", "pricing", "branch_discovery", "doctor_discovery",
    "availability_discovery", "appointment_creation", "appointment_list", "appointment_confirmation",
    "appointment_cancellation", "appointment_reschedule", "customer_profile", "customer_history",
    "package_information", "package_refund_quote", "follow_up_request", "marketing_preferences", "human_support",
]
RiskFlag = Literal["medical", "complaint", "payment", "urgent"]
HandoffCategory = Literal["medical", "complaint", "payment", "customer_request", "booking_exception", "agent_uncertain", "other"]
Priority = Literal["low", "normal", "high", "urgent"]
FlowSignal = Literal["none", "start_booking", "start_reschedule", "interrupt"]
PackageIntent = Literal["none", "inquire", "purchase", "use_existing", "avoid_existing"]
FlowTurnAction = Literal["continue", "modify", "select_option", "cancel_flow", "interrupt"]
LaserDeviceKey = Literal["prime_lase", "candela_gentle"]
ClearableFlowEntity = Literal[
    "service_query", "service_id", "service_candidate_ids", "branch_query", "branch_id",
    "branch_candidate_ids", "doctor_query", "doctor_id", "doctor_candidate_ids", "laser_device_key",
    "requested_date", "requested_start_time", "not_before_time", "not_after_time",
    "appointment_reference", "appointment_id",
]


def _require_all_schema_fields(schema: dict) -> None:
    properties = schema.get("properties")
    if isinstance(properties, dict):
        schema["required"] = list(properties)


class SemanticEntityHints(BaseModel):
    model_config = ConfigDict(extra="forbid", json_schema_extra=_require_all_schema_fields)

    service_query: str | None = Field(default=None, description="Service wording intended by the latest customer turn.")
    branch_query: str | None
    doctor_query: str | None
    service_id: str | None = Field(default=None, description="Canonical service UUID from the supplied clinic catalog.")
    service_candidate_ids: list[str] = Field(default_factory=list)
    branch_id: str | None = Field(default=None, description="Canonical branch UUID from the supplied clinic catalog.")
    branch_candidate_ids: list[str] = Field(default_factory=list)
    doctor_id: str | None = Field(default=None, description="Canonical doctor UUID from the supplied clinic catalog.")
    doctor_candidate_ids: list[str] = Field(default_factory=list)
    laser_device_key: LaserDeviceKey | None = Field(
        default=None,
        description=(
            "For a service whose catalog row requires a laser device, select only one of the supplied "
            "configured device keys when the customer clearly chose it. Never guess a device."
        ),
    )
    appointment_id: str | None = Field(
        default=None,
        description="Canonical ID of the EXISTING appointment being acted on, selected only from current-patient appointments.",
    )
    requested_date: str | None = Field(default=None, description="Desired appointment date YYYY-MM-DD from the latest customer turn.")
    requested_start_time: str | None = Field(
        default=None,
        description=(
            "Exact local appointment start HH:MM that the customer intends as the appointment itself. "
            "Do not use this for the beginning of an availability search or for a reply to a question "
            "asking when the search window should start."
        ),
    )
    not_before_time: str | None = Field(
        description=(
            "Lower bound HH:MM for availability discovery. Use this when the customer wants options at or "
            "after a time, including when answering the assistant's question about when the availability "
            "search should begin. This is not an exact appointment selection."
        )
    )
    not_after_time: str | None = Field(
        description=(
            "Upper bound HH:MM for availability discovery. Use this when the customer wants options at or "
            "before a time or answers when the availability search should end. This is not an exact "
            "appointment selection."
        )
    )
    appointment_reference: str | None = Field(default=None, description="Customer-facing reference identifying an existing appointment.")

    @model_validator(mode="after")
    def bind_selected_laser_device(self) -> SemanticEntityHints:
        # ContextVar is request/task-local. This gives the deterministic clinic
        # adapter access to the structured semantic choice without parsing text
        # and without adding keyword routing to the booking orchestrator.
        if self.laser_device_key is not None:
            set_laser_device_key(self.laser_device_key)
        return self


class SemanticCapabilityDecision(BaseModel):
    model_config = ConfigDict(extra="forbid", json_schema_extra=_require_all_schema_fields)
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
    model_config = ConfigDict(extra="forbid", json_schema_extra=_require_all_schema_fields)
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
        laser_device_key=None,
        requested_date=None,
        requested_start_time=None,
        not_before_time=None,
        not_after_time=None,
        appointment_reference=None,
    )
