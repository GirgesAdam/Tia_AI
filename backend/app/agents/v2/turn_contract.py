from __future__ import annotations

from datetime import date, datetime, time
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

OperationType = Literal[
    "service_info",
    "pricing",
    "doctor_info",
    "clinic_info",
    "availability",
    "book",
    "appointment_list",
    "confirm_appointment",
    "cancel_appointment",
    "reschedule",
    "customer_profile",
    "customer_history",
    "package_info",
    "buy_package",
    "refund_quote",
    "follow_up",
    "marketing_update",
    "human_support",
    "continue_active",
    "select_active",
    "cancel_active",
    "social",
    "unclear",
]
SafetySignal = Literal[
    "medical",
    "urgent_medical",
    "complaint",
    "payment_dispute",
    "privacy_issue",
]
PackageUsage = Literal["unspecified", "use_existing", "avoid_existing"]
ServiceDetail = Literal["price", "duration", "description", "devices"]
DateMode = Literal["exact", "range", "from_date", "next_available"]
TimeMode = Literal["exact", "after", "before", "range"]
TimeAmbiguity = Literal["none", "twelve_hour"]
SelectionKind = Literal["index", "time", "ref"]


def _require_all_schema_fields(schema: dict) -> None:
    properties = schema.get("properties")
    if isinstance(properties, dict):
        schema["required"] = list(properties)


class StrictContractModel(BaseModel):
    model_config = ConfigDict(
        extra="forbid",
        json_schema_extra=_require_all_schema_fields,
    )


class EntityReference(StrictContractModel):
    """Semantic catalog reference selected by the model, never a database identifier."""

    text: str | None = None
    ref: str | None = None
    candidate_refs: list[str] = Field(default_factory=list)


class DateConstraint(StrictContractModel):
    mode: DateMode
    start_date: str | None = None
    end_date: str | None = None

    @model_validator(mode="after")
    def validate_dates(self) -> DateConstraint:
        if self.start_date is not None:
            date.fromisoformat(self.start_date)
        if self.end_date is not None:
            date.fromisoformat(self.end_date)

        if self.mode in {"exact", "from_date"} and self.start_date is None:
            raise ValueError(f"{self.mode} date constraint requires start_date.")
        if self.mode == "range":
            if self.start_date is None or self.end_date is None:
                raise ValueError("range date constraint requires start_date and end_date.")
            if date.fromisoformat(self.end_date) < date.fromisoformat(self.start_date):
                raise ValueError("date range end_date cannot be before start_date.")
        if self.mode == "next_available" and (
            self.start_date is not None or self.end_date is not None
        ):
            raise ValueError("next_available date constraint must not invent a date.")
        return self


class TimeConstraint(StrictContractModel):
    mode: TimeMode
    start_time: str | None = None
    end_time: str | None = None
    start_time_ambiguity: TimeAmbiguity = "none"
    end_time_ambiguity: TimeAmbiguity = "none"

    @model_validator(mode="after")
    def validate_times(self) -> TimeConstraint:
        parsed_start = time.fromisoformat(self.start_time) if self.start_time else None
        parsed_end = time.fromisoformat(self.end_time) if self.end_time else None

        if self.mode in {"exact", "after", "before"} and parsed_start is None:
            raise ValueError(f"{self.mode} time constraint requires start_time.")
        if self.mode == "range":
            if parsed_start is None or parsed_end is None:
                raise ValueError("range time constraint requires start_time and end_time.")
            if parsed_end < parsed_start:
                raise ValueError("time range end_time cannot be before start_time.")
        if parsed_start is None and self.start_time_ambiguity != "none":
            raise ValueError("start_time_ambiguity requires start_time.")
        if parsed_end is None and self.end_time_ambiguity != "none":
            raise ValueError("end_time_ambiguity requires end_time.")
        return self


class Selection(StrictContractModel):
    kind: SelectionKind
    index: int | None = None
    time: str | None = None
    ref: str | None = None
    time_ambiguity: TimeAmbiguity = "none"

    @model_validator(mode="after")
    def validate_selection(self) -> Selection:
        if self.kind == "index":
            if self.index is None or self.index < 1:
                raise ValueError("index selection requires a positive index.")
            if self.time is not None or self.ref is not None:
                raise ValueError("index selection cannot also contain time/ref.")
            if self.time_ambiguity != "none":
                raise ValueError("index selection cannot contain time ambiguity.")
        elif self.kind == "time":
            if self.time is None:
                raise ValueError("time selection requires time.")
            time.fromisoformat(self.time)
            if self.index is not None or self.ref is not None:
                raise ValueError("time selection cannot also contain index/ref.")
        elif self.kind == "ref":
            if not self.ref:
                raise ValueError("ref selection requires ref.")
            if self.index is not None or self.time is not None:
                raise ValueError("ref selection cannot also contain index/time.")
            if self.time_ambiguity != "none":
                raise ValueError("ref selection cannot contain time ambiguity.")
        return self


class TurnEntities(StrictContractModel):
    service: EntityReference | None = None
    doctor: EntityReference | None = None
    device: EntityReference | None = None
    appointment: EntityReference | None = None
    package: EntityReference | None = None
    date: DateConstraint | None = None
    time: TimeConstraint | None = None
    package_sessions: int | None = None
    marketing_consent: bool | None = None
    follow_up_at_local: str | None = None

    @model_validator(mode="after")
    def validate_follow_up_datetime(self) -> TurnEntities:
        if self.package_sessions is not None and self.package_sessions < 1:
            raise ValueError("package_sessions must be positive.")
        if self.follow_up_at_local is not None:
            datetime.fromisoformat(self.follow_up_at_local)
        return self


class TurnOperation(StrictContractModel):
    type: OperationType = Field(
        description=(
            "Choose the customer's semantic action. Use book whenever the customer is asking Tia "
            "to create/reserve a new appointment now, even when required booking details are still "
            "missing and Python will need to clarify them. Do not downgrade an incomplete booking "
            "request to availability. Use availability only when the customer is asking to inspect "
            "possible appointment options without requesting creation of a new appointment."
        )
    )
    entities: TurnEntities
    selection: Selection | None = None
    package_usage: PackageUsage = "unspecified"
    requested_service_details: list[ServiceDetail] = Field(default_factory=list)


class TiaTurnUnderstanding(StrictContractModel):
    """The only semantic result required from the V2 language-understanding model."""

    operations: list[TurnOperation] = Field(default_factory=list)
    safety_signals: list[SafetySignal] = Field(default_factory=list)

    @model_validator(mode="after")
    def validate_non_empty_turn(self) -> TiaTurnUnderstanding:
        if not self.operations and not self.safety_signals:
            raise ValueError("A turn must contain at least one operation or safety signal.")
        if len(self.operations) > 6:
            raise ValueError("A customer turn cannot produce more than six operations.")
        return self
