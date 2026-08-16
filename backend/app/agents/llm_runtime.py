from __future__ import annotations

from collections.abc import Callable
from typing import TypeVar

from google.genai import errors
from langchain_google_genai.chat_models import ChatGoogleGenerativeAIError

T = TypeVar("T")


class LLMProviderError(RuntimeError):
    def __init__(
        self,
        message: str,
        *,
        status_code: int | None = None,
        retryable: bool = False,
    ) -> None:
        super().__init__(message)
        self.status_code = status_code
        self.retryable = retryable


def _status_from_exception(exc: BaseException) -> int | None:
    current: BaseException | None = exc
    visited: set[int] = set()

    while current is not None and id(current) not in visited:
        visited.add(id(current))
        if isinstance(current, errors.APIError):
            try:
                return int(current.code) if current.code is not None else None
            except (TypeError, ValueError):
                return None
        current = current.__cause__ or current.__context__

    return None


def _provider_error(exc: BaseException) -> LLMProviderError:
    code = _status_from_exception(exc)
    retryable = code == 429 or (code is not None and code >= 500)
    return LLMProviderError(
        "Gemini API request failed.",
        status_code=code,
        retryable=retryable,
    )


def invoke_model(call: Callable[[], T]) -> T:
    """
    Small provider error boundary.

    Retries belong to the Google/LangChain client configuration. This function
    does not sleep, parse Retry-After headers, or replay a LangGraph run.

    ChatGoogleGenerativeAI wraps google.genai ClientError, so both the original
    SDK error and the LangChain wrapper are normalized here.
    """
    try:
        return call()
    except ChatGoogleGenerativeAIError as exc:
        raise _provider_error(exc) from exc
    except errors.APIError as exc:
        raise _provider_error(exc) from exc
