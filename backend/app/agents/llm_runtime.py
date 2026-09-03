from __future__ import annotations

import logging
import re
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from threading import Lock
from time import monotonic, perf_counter
from typing import TypeVar

import openai

T = TypeVar("T")

logger = logging.getLogger(__name__)


@dataclass
class _CircuitState:
    open_until: float = 0.0
    probe_inflight: bool = False


# Provider health is tracked per model, not per primary->fallback pair.
_circuit_states: dict[str, _CircuitState] = {}
_circuit_lock = Lock()


def _provider_name() -> str:
    return "OpenAI"


def _should_bypass_model(model_name: str, *, cooldown_seconds: int) -> bool:
    if cooldown_seconds <= 0:
        return False
    now = monotonic()
    with _circuit_lock:
        state = _circuit_states.get(model_name)
        if state is None:
            return False
        if state.open_until > now:
            return True
        if state.open_until > 0:
            if state.probe_inflight:
                return True
            state.probe_inflight = True
    return False


def _open_model_circuit(model_name: str, *, cooldown_seconds: int) -> None:
    if cooldown_seconds <= 0:
        return
    with _circuit_lock:
        state = _circuit_states.setdefault(model_name, _CircuitState())
        state.open_until = monotonic() + cooldown_seconds
        state.probe_inflight = False


def _close_model_circuit(model_name: str) -> None:
    with _circuit_lock:
        _circuit_states.pop(model_name, None)


def _release_model_probe(model_name: str) -> None:
    with _circuit_lock:
        state = _circuit_states.get(model_name)
        if state is not None:
            state.probe_inflight = False


def _reset_circuit_breakers_for_tests() -> None:
    with _circuit_lock:
        _circuit_states.clear()


class LLMProviderError(RuntimeError):
    def __init__(
        self,
        message: str,
        *,
        status_code: int | None = None,
        retryable: bool = False,
        provider_detail: str | None = None,
        provider_error_type: str | None = None,
    ) -> None:
        super().__init__(message)
        self.status_code = status_code
        self.retryable = retryable
        # Backend-only diagnostics. API routes must never surface these fields to
        # browser/mobile clients because provider messages are operational details.
        self.provider_detail = provider_detail
        self.provider_error_type = provider_error_type


@dataclass(frozen=True)
class LLMInvocationResult[T]:
    value: T
    model_name: str
    used_fallback: bool


def _status_from_exception(exc: BaseException) -> int | None:
    current: BaseException | None = exc
    visited: set[int] = set()
    while current is not None and id(current) not in visited:
        visited.add(id(current))
        if isinstance(current, openai.APIStatusError):
            try:
                return int(current.status_code)
            except (TypeError, ValueError):
                return None
        if isinstance(current, openai.APIConnectionError):
            # There is no upstream HTTP status for a connection/timeout failure,
            # but operationally this is a temporary provider-unavailable condition.
            return 503
        current = current.__cause__ or current.__context__
    return None


_SENSITIVE_PROVIDER_PATTERNS = (
    re.compile(r"sk-[0-9A-Za-z_-]{20,}"),
    re.compile(r"(?i)(?:api[_-]?key|authorization)\s*[=:]\s*[^\s,;]+"),
)


def _provider_diagnostic_source(exc: BaseException) -> BaseException:
    current: BaseException = exc
    visited: set[int] = set()
    deepest: BaseException = exc
    while id(current) not in visited:
        visited.add(id(current))
        deepest = current
        next_exc = current.__cause__ or current.__context__
        if next_exc is None:
            break
        current = next_exc
    return deepest


def _safe_provider_detail(exc: BaseException) -> tuple[str, str]:
    """Return a short backend-only provider diagnostic without request payloads."""
    source = _provider_diagnostic_source(exc)
    detail = " ".join(str(source).split())
    for pattern in _SENSITIVE_PROVIDER_PATTERNS:
        detail = pattern.sub("[REDACTED]", detail)
    if len(detail) > 1200:
        detail = detail[:1197] + "..."
    return type(source).__name__, detail


def _provider_error(exc: BaseException) -> LLMProviderError:
    code = _status_from_exception(exc)
    retryable = code == 429 or (code is not None and code >= 500)
    error_type, detail = _safe_provider_detail(exc)
    return LLMProviderError(
        "OpenAI API request failed.",
        status_code=code,
        retryable=retryable,
        provider_detail=detail or None,
        provider_error_type=error_type,
    )


def is_cross_model_failover_eligible(exc: LLMProviderError) -> bool:
    """Only provider-side 5xx errors can advance to another configured model."""
    return exc.status_code is not None and 500 <= exc.status_code <= 599


def provider_error_http_status(exc: LLMProviderError) -> int:
    if exc.status_code == 429:
        return 429
    if exc.status_code is not None and 500 <= exc.status_code <= 599:
        return 503
    return 502


def invoke_model(call: Callable[[], T]) -> T:
    """Provider error boundary; no graph/workflow replay happens here."""
    try:
        return call()
    except openai.APIError as exc:
        raise _provider_error(exc) from exc


def _unique_model_calls(
    model_calls: Sequence[tuple[str, Callable[[], T]]],
) -> list[tuple[str, Callable[[], T]]]:
    result: list[tuple[str, Callable[[], T]]] = []
    seen: set[str] = set()
    for model_name, call in model_calls:
        normalized = str(model_name).strip()
        if not normalized or normalized in seen:
            continue
        seen.add(normalized)
        result.append((normalized, call))
    return result


def invoke_with_model_chain(
    *,
    model_calls: Sequence[tuple[str, Callable[[], T]]],
    operation: str,
    circuit_breaker_cooldown_seconds: int = 0,
) -> LLMInvocationResult[T]:
    """Bounded ordered OpenAI model failover with a circuit breaker per model.

    5xx advances to the next configured model. 4xx/429/schema/application errors
    fail immediately so switching models cannot conceal a broken request.
    """
    candidates = _unique_model_calls(model_calls)
    provider = _provider_name()
    if not candidates:
        raise RuntimeError("No OpenAI model is configured for this operation.")

    chain_started = perf_counter()
    last_provider_error: LLMProviderError | None = None
    attempted_any = False

    for index, (model_name, call) in enumerate(candidates):
        if _should_bypass_model(
            model_name,
            cooldown_seconds=circuit_breaker_cooldown_seconds,
        ):
            next_model = candidates[index + 1][0] if index + 1 < len(candidates) else None
            logger.warning(
                "%s runtime operation=%s model=%s circuit=open bypass_model=true next_model=%s",
                provider,
                operation,
                model_name,
                next_model,
            )
            continue

        attempted_any = True
        started = perf_counter()
        try:
            value = call()
        except LLMProviderError as exc:
            elapsed_ms = int((perf_counter() - started) * 1000)
            if not is_cross_model_failover_eligible(exc):
                _release_model_probe(model_name)
                logger.warning(
                    "%s runtime operation=%s model=%s failed status=%s retryable=%s "
                    "duration_ms=%s failover=false",
                    provider,
                    operation,
                    model_name,
                    exc.status_code,
                    exc.retryable,
                    elapsed_ms,
                )
                raise
            _open_model_circuit(
                model_name,
                cooldown_seconds=circuit_breaker_cooldown_seconds,
            )
            last_provider_error = exc
            next_model = candidates[index + 1][0] if index + 1 < len(candidates) else None
            logger.warning(
                "%s runtime operation=%s model=%s failed status=%s duration_ms=%s; "
                "open_circuit_seconds=%s next_model=%s",
                provider,
                operation,
                model_name,
                exc.status_code,
                elapsed_ms,
                circuit_breaker_cooldown_seconds,
                next_model,
            )
            continue
        except BaseException:
            _release_model_probe(model_name)
            raise

        _close_model_circuit(model_name)
        elapsed_ms = int((perf_counter() - started) * 1000)
        total_ms = int((perf_counter() - chain_started) * 1000)
        logger.info(
            "%s runtime operation=%s model=%s candidate_index=%s fallback=%s "
            "duration_ms=%s total_duration_ms=%s",
            provider,
            operation,
            model_name,
            index,
            index > 0,
            elapsed_ms,
            total_ms,
        )
        return LLMInvocationResult(
            value=value,
            model_name=model_name,
            used_fallback=index > 0,
        )

    if last_provider_error is not None:
        logger.error(
            "%s runtime operation=%s model_chain_exhausted=true models=%s total_duration_ms=%s",
            provider,
            operation,
            [name for name, _ in candidates],
            int((perf_counter() - chain_started) * 1000),
        )
        raise last_provider_error

    if not attempted_any:
        logger.error(
            "%s runtime operation=%s model_chain_unavailable=true all_circuits_open=true models=%s",
            provider,
            operation,
            [name for name, _ in candidates],
        )
        raise LLMProviderError(
            "All configured OpenAI realtime models are temporarily unavailable.",
            status_code=503,
            retryable=True,
        )

    raise RuntimeError("OpenAI model chain ended without a result.")


def invoke_with_fallback(
    *,
    primary_call: Callable[[], T],
    primary_model_name: str,
    fallback_call: Callable[[], T] | None,
    fallback_model_name: str | None,
    operation: str,
    circuit_breaker_cooldown_seconds: int = 0,
) -> LLMInvocationResult[T]:
    """Two-model wrapper used by the realtime orchestration modules."""
    model_calls: list[tuple[str, Callable[[], T]]] = [
        (primary_model_name, primary_call)
    ]
    if fallback_call is not None and fallback_model_name:
        model_calls.append((fallback_model_name, fallback_call))
    return invoke_with_model_chain(
        model_calls=model_calls,
        operation=operation,
        circuit_breaker_cooldown_seconds=circuit_breaker_cooldown_seconds,
    )
