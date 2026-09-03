from __future__ import annotations

from functools import lru_cache

from langchain_core.language_models.chat_models import BaseChatModel
from langchain_google_genai import ChatGoogleGenerativeAI
from langchain_openai import ChatOpenAI

from app.core.config import settings


class LLMConfigurationError(RuntimeError):
    pass


def _require_gemini_key() -> str:
    if not settings.gemini_api_key:
        raise LLMConfigurationError("GEMINI_API_KEY is not configured. Add it to backend/.env.")
    return settings.gemini_api_key


def _require_openai_key() -> str:
    if not settings.openai_api_key:
        raise LLMConfigurationError("OPENAI_API_KEY is not configured. Add it to the backend environment.")
    return settings.openai_api_key


@lru_cache(maxsize=32)
def _cached_gemini_model(
    *,
    api_key: str,
    model: str,
    thinking_level: str,
    max_tokens: int,
    timeout_seconds: int,
    max_retries: int,
) -> BaseChatModel:
    return ChatGoogleGenerativeAI(
        model=model,
        api_key=api_key,
        vertexai=False,
        thinking_level=thinking_level,
        max_tokens=max_tokens,
        timeout=timeout_seconds,
        max_retries=max_retries,
    )


@lru_cache(maxsize=32)
def _cached_openai_model(
    *,
    api_key: str,
    model: str,
    reasoning_effort: str,
    max_tokens: int,
    timeout_seconds: int,
    max_retries: int,
) -> BaseChatModel:
    """Reuse stateless OpenAI Responses API clients across customer turns.

    Tia keeps conversation/workflow state in its own database and messages, so the
    provider response is not stored server-side by OpenAI. The v0 LangChain output
    shape keeps the existing LangGraph/tool-message contract stable while the
    transport uses the Responses API.
    """
    return ChatOpenAI(
        model=model,
        api_key=api_key,
        use_responses_api=True,
        output_version="v0",
        reasoning={"effort": reasoning_effort},
        max_tokens=max_tokens,
        timeout=timeout_seconds,
        max_retries=max_retries,
        streaming=False,
        store=False,
    )


def _build_provider_model(
    *,
    model: str,
    thinking_level: str,
    max_tokens: int,
    max_retries: int | None = None,
) -> BaseChatModel:
    retries = settings.llm_max_retries if max_retries is None else max_retries
    if settings.llm_provider == "openai":
        return _cached_openai_model(
            api_key=_require_openai_key(),
            model=model,
            reasoning_effort=settings.openai_reasoning_effort,
            max_tokens=max_tokens,
            timeout_seconds=settings.llm_timeout_seconds,
            max_retries=retries,
        )
    return _cached_gemini_model(
        api_key=_require_gemini_key(),
        model=model,
        thinking_level=thinking_level,
        max_tokens=max_tokens,
        timeout_seconds=settings.llm_timeout_seconds,
        max_retries=retries,
    )


def _build_optional_fallback_model(
    *,
    primary_model: str,
    fallback_model: str | None,
    thinking_level: str,
    max_tokens: int,
    max_retries: int | None = None,
) -> BaseChatModel | None:
    if not fallback_model or fallback_model == primary_model:
        return None
    return _build_provider_model(
        model=fallback_model,
        thinking_level=thinking_level,
        max_tokens=max_tokens,
        max_retries=max_retries,
    )


def build_realtime_interpreter_model() -> BaseChatModel:
    return _build_provider_model(
        model=settings.gemini_realtime_interpreter_model,
        thinking_level=settings.gemini_realtime_interpreter_thinking_level,
        max_tokens=settings.agent_router_max_output_tokens,
        max_retries=settings.llm_realtime_max_retries,
    )


def build_realtime_interpreter_fallback_model() -> BaseChatModel | None:
    return _build_optional_fallback_model(
        primary_model=settings.gemini_realtime_interpreter_model,
        fallback_model=settings.gemini_realtime_interpreter_fallback_model,
        thinking_level=settings.gemini_realtime_interpreter_thinking_level,
        max_tokens=settings.agent_router_max_output_tokens,
        max_retries=settings.llm_realtime_max_retries,
    )


def build_realtime_interpreter_emergency_model() -> BaseChatModel | None:
    emergency = settings.gemini_realtime_interpreter_emergency_model
    if not emergency or emergency in {
        settings.gemini_realtime_interpreter_model,
        settings.gemini_realtime_interpreter_fallback_model,
    }:
        return None
    return _build_provider_model(
        model=emergency,
        thinking_level=settings.gemini_realtime_interpreter_thinking_level,
        max_tokens=settings.agent_router_max_output_tokens,
        max_retries=settings.llm_realtime_max_retries,
    )


def build_realtime_composer_model() -> BaseChatModel:
    return _build_provider_model(
        model=settings.gemini_realtime_composer_model,
        thinking_level=settings.gemini_realtime_composer_thinking_level,
        max_tokens=settings.llm_max_output_tokens,
        max_retries=settings.llm_realtime_max_retries,
    )


def build_realtime_composer_fallback_model() -> BaseChatModel | None:
    return _build_optional_fallback_model(
        primary_model=settings.gemini_realtime_composer_model,
        fallback_model=settings.gemini_realtime_composer_fallback_model,
        thinking_level=settings.gemini_realtime_composer_thinking_level,
        max_tokens=settings.llm_max_output_tokens,
        max_retries=settings.llm_realtime_max_retries,
    )


def build_chat_model() -> BaseChatModel:
    return _build_provider_model(
        model=settings.gemini_agent_model,
        thinking_level=settings.gemini_agent_thinking_level,
        max_tokens=settings.llm_max_output_tokens,
        max_retries=settings.llm_realtime_max_retries,
    )


def build_chat_fallback_model() -> BaseChatModel | None:
    return _build_optional_fallback_model(
        primary_model=settings.gemini_agent_model,
        fallback_model=settings.gemini_agent_fallback_model,
        thinking_level=settings.gemini_agent_thinking_level,
        max_tokens=settings.llm_max_output_tokens,
        max_retries=settings.llm_realtime_max_retries,
    )


def build_semantic_router_model() -> BaseChatModel:
    return _build_provider_model(
        model=settings.gemini_router_model,
        thinking_level=settings.gemini_router_thinking_level,
        max_tokens=settings.agent_router_max_output_tokens,
        max_retries=settings.llm_realtime_max_retries,
    )


def build_semantic_router_fallback_model() -> BaseChatModel | None:
    return _build_optional_fallback_model(
        primary_model=settings.gemini_router_model,
        fallback_model=settings.gemini_router_fallback_model,
        thinking_level=settings.gemini_router_thinking_level,
        max_tokens=settings.agent_router_max_output_tokens,
        max_retries=settings.llm_realtime_max_retries,
    )


def build_flow_interpreter_model() -> BaseChatModel:
    return _build_provider_model(
        model=settings.gemini_flow_model,
        thinking_level=settings.gemini_flow_thinking_level,
        max_tokens=settings.agent_flow_interpreter_max_output_tokens,
        max_retries=settings.llm_realtime_max_retries,
    )


def build_flow_interpreter_fallback_model() -> BaseChatModel | None:
    return _build_optional_fallback_model(
        primary_model=settings.gemini_flow_model,
        fallback_model=settings.gemini_flow_fallback_model,
        thinking_level=settings.gemini_flow_thinking_level,
        max_tokens=settings.agent_flow_interpreter_max_output_tokens,
        max_retries=settings.llm_realtime_max_retries,
    )


def build_onboarding_model(*, max_retries: int | None = None) -> BaseChatModel:
    return _build_provider_model(
        model=settings.gemini_onboarding_model,
        thinking_level=settings.gemini_onboarding_thinking_level,
        max_tokens=settings.gemini_onboarding_max_output_tokens,
        max_retries=max_retries,
    )


def build_onboarding_fallback_model(*, max_retries: int | None = None) -> BaseChatModel | None:
    return _build_optional_fallback_model(
        primary_model=settings.gemini_onboarding_model,
        fallback_model=settings.gemini_onboarding_fallback_model,
        thinking_level=settings.gemini_onboarding_thinking_level,
        max_tokens=settings.gemini_onboarding_max_output_tokens,
        max_retries=max_retries,
    )


def build_utility_model() -> BaseChatModel:
    return _build_provider_model(
        model=settings.gemini_utility_model,
        thinking_level=settings.gemini_utility_thinking_level,
        max_tokens=1024,
    )


def model_label(model_name: str) -> str:
    return f"{settings.llm_provider}:{model_name}"


def active_model_name() -> str:
    return settings.gemini_agent_model


def active_model_label() -> str:
    return model_label(active_model_name())
