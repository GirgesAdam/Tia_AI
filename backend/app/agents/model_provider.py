from __future__ import annotations

from langchain_core.language_models.chat_models import BaseChatModel
from langchain_google_genai import ChatGoogleGenerativeAI

from app.core.config import settings


class LLMConfigurationError(RuntimeError):
    pass


def _require_gemini_key() -> str:
    if not settings.gemini_api_key:
        raise LLMConfigurationError(
            "GEMINI_API_KEY is not configured. Add it to backend/.env."
        )
    return settings.gemini_api_key


def _build_gemini_model(
    *,
    model: str,
    thinking_level: str,
    max_tokens: int,
) -> BaseChatModel:
    """
    Build a Gemini Developer API model through LangChain's current Google GenAI
    integration.

    Gemini 3.7 uses thinking_level rather than Groq/OpenAI-style reasoning
    workarounds. We deliberately do not set temperature/top_p/top_k.
    """
    return ChatGoogleGenerativeAI(
        model=model,
        api_key=_require_gemini_key(),
        vertexai=False,
        thinking_level=thinking_level,
        max_tokens=max_tokens,
        timeout=settings.llm_timeout_seconds,
        max_retries=settings.llm_max_retries,
    )


def build_chat_model() -> BaseChatModel:
    return _build_gemini_model(
        model=settings.gemini_agent_model,
        thinking_level=settings.gemini_agent_thinking_level,
        max_tokens=settings.llm_max_output_tokens,
    )


def build_semantic_router_model() -> BaseChatModel:
    return _build_gemini_model(
        model=settings.gemini_router_model,
        thinking_level=settings.gemini_router_thinking_level,
        max_tokens=settings.agent_router_max_output_tokens,
    )


def build_flow_interpreter_model() -> BaseChatModel:
    return _build_gemini_model(
        model=settings.gemini_flow_model,
        thinking_level=settings.gemini_flow_thinking_level,
        max_tokens=settings.agent_flow_interpreter_max_output_tokens,
    )


def build_onboarding_model() -> BaseChatModel:
    return _build_gemini_model(
        model=settings.gemini_onboarding_model,
        thinking_level=settings.gemini_onboarding_thinking_level,
        max_tokens=settings.gemini_onboarding_max_output_tokens,
    )


def build_onboarding_fallback_model() -> BaseChatModel | None:
    model = settings.gemini_onboarding_fallback_model
    if not model or model == settings.gemini_onboarding_model:
        return None
    return _build_gemini_model(
        model=model,
        thinking_level=settings.gemini_onboarding_thinking_level,
        max_tokens=settings.gemini_onboarding_max_output_tokens,
    )


def build_utility_model() -> BaseChatModel:
    return _build_gemini_model(
        model=settings.gemini_utility_model,
        thinking_level=settings.gemini_utility_thinking_level,
        max_tokens=1024,
    )


def active_model_name() -> str:
    return settings.gemini_agent_model


def active_model_label() -> str:
    return f"gemini:{active_model_name()}"
