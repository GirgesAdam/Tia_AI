from __future__ import annotations

from typing import Literal
from uuid import UUID

from pydantic import BaseModel, Field, field_validator

AgentChannel = Literal[
    "whatsapp",
    "instagram",
    "facebook",
    "web",
    "email",
    "sms",
    "other",
]


class AgentChatRequest(BaseModel):
    patient_id: UUID
    conversation_id: UUID | None = None
    channel: AgentChannel = "web"
    message: str = Field(min_length=1, max_length=10000)

    @field_validator("message")
    @classmethod
    def normalize_message(cls, value: str) -> str:
        value = value.strip()
        if not value:
            raise ValueError("Message cannot be empty.")
        return value


class AgentChatResponse(BaseModel):
    run_id: UUID
    conversation_id: UUID
    inbound_message_id: UUID
    outbound_message_id: UUID | None
    reply: str | None
    handoff_required: bool
    agent_paused: bool = False
    model: str | None
