from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

OutcomeStatus = Literal[
    "answered",
    "needs_input",
    "completed",
    "blocked",
    "handoff",
    "partial_success",
]
ResponseGoal = Literal[
    "answer_service",
    "answer_price",
    "answer_doctor",
    "answer_clinic_info",
    "answer_customer_profile",
    "answer_customer_history",
    "present_availability",
    "requested_time_unavailable",
    "no_availability",
    "ask_service_choice",
    "ask_doctor_choice",
    "ask_device_choice",
    "ask_time_choice",
    "ask_appointment_choice",
    "ask_package_choice",
    "clarification",
    "booking_completed",
    "reschedule_completed",
    "cancellation_completed",
    "appointment_confirmed",
    "package_information",
    "package_purchased",
    "package_refund_quote",
    "follow_up_created",
    "marketing_updated",
    "handoff",
    "social_ack",
]


class StrictOutcomeModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


class OutcomeChoice(StrictOutcomeModel):
    ref: str
    label: str
    facts: dict[str, object] = Field(default_factory=dict)


class TurnOutcome(StrictOutcomeModel):
    """Structured business result consumed by the customer-facing V2 responder."""

    status: OutcomeStatus
    response_goal: ResponseGoal
    facts: dict[str, object] = Field(default_factory=dict)
    choices: list[OutcomeChoice] = Field(default_factory=list)
    action_result: dict[str, object] = Field(default_factory=dict)
    active_task_summary: dict[str, object] = Field(default_factory=dict)

    @model_validator(mode="after")
    def validate_shape(self) -> TurnOutcome:
        choice_goals = {
            "ask_service_choice",
            "ask_doctor_choice",
            "ask_device_choice",
            "ask_time_choice",
            "ask_appointment_choice",
            "ask_package_choice",
        }
        if self.response_goal in choice_goals and not self.choices:
            raise ValueError("choice response goals require verified choices.")
        if self.status == "handoff" and self.response_goal != "handoff":
            raise ValueError("handoff status requires handoff response goal.")
        return self
