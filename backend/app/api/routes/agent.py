from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.agents.llm_runtime import LLMProviderError
from app.agents.model_provider import LLMConfigurationError
from app.agents.structured_output import StructuredOutputError
from app.api.dependencies.security import WorkspaceAccess, get_workspace_reader
from app.database.session import get_db
from app.schemas.agent import AgentChatRequest, AgentChatResponse
from app.services.agent_chat import AgentChatError, run_agent_chat
from app.services.conversation_flows import FlowStateConflictError

router = APIRouter()


@router.post("/chat", response_model=AgentChatResponse)
def chat_with_tia_agent(
    payload: AgentChatRequest,
    access: Annotated[WorkspaceAccess, Depends(get_workspace_reader)],
    db: Annotated[Session, Depends(get_db)],
) -> AgentChatResponse:
    try:
        return run_agent_chat(
            db=db,
            workspace=access.workspace,
            payload=payload,
        )
    except LLMConfigurationError as exc:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=str(exc),
        ) from exc
    except LLMProviderError as exc:
        http_status = (
            status.HTTP_503_SERVICE_UNAVAILABLE
            if exc.retryable
            else status.HTTP_502_BAD_GATEWAY
        )
        raise HTTPException(
            status_code=http_status,
            detail="Gemini provider request failed.",
        ) from exc
    except FlowStateConflictError as exc:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Conversation state changed concurrently. Retry this turn.",
        ) from exc
    except StructuredOutputError as exc:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail="AI semantic routing returned an invalid structured result.",
        ) from exc
    except AgentChatError as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=str(exc),
        ) from exc
    except RuntimeError as exc:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail="AI agent execution failed.",
        ) from exc
