from uuid import uuid4

import pytest
from pydantic import ValidationError

from app.schemas.agent import AgentChatRequest


def test_agent_chat_message_is_trimmed() -> None:
    payload = AgentChatRequest(patient_id=uuid4(), message="  عايز احجز ليزر بكرة  ")
    assert payload.message == "عايز احجز ليزر بكرة"
    assert payload.channel == "web"


def test_agent_chat_rejects_blank_message() -> None:
    with pytest.raises(ValidationError):
        AgentChatRequest(patient_id=uuid4(), message="   ")
