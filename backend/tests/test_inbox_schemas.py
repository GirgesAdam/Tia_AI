from uuid import uuid4

import pytest
from pydantic import ValidationError

from app.schemas.agent import AgentChatResponse
from app.schemas.inbox import ResolveHandoffRequest, StaffReplyRequest


def test_staff_reply_strips_content() -> None:
    payload = StaffReplyRequest(content="  تمام، هراجعلك الموضوع.  ")
    assert payload.content == "تمام، هراجعلك الموضوع."


def test_staff_reply_rejects_blank_content() -> None:
    with pytest.raises(ValidationError):
        StaffReplyRequest(content="   ")


def test_resolve_defaults_to_reopen_ai_conversation() -> None:
    payload = ResolveHandoffRequest()
    assert payload.conversation_status_after == "open"


def test_paused_agent_response_has_no_fake_outbound_message() -> None:
    response = AgentChatResponse(
        run_id=uuid4(),
        conversation_id=uuid4(),
        inbound_message_id=uuid4(),
        outbound_message_id=None,
        reply=None,
        handoff_required=True,
        agent_paused=True,
        model=None,
    )
    assert response.agent_paused is True
    assert response.outbound_message_id is None
    assert response.reply is None
