import pytest

from app.agents.llm_runtime import (
    LLMProviderError,
    _reset_circuit_breakers_for_tests,
    invoke_with_fallback,
    is_cross_model_failover_eligible,
    provider_error_http_status,
)


def _error(status_code: int | None) -> LLMProviderError:
    return LLMProviderError(
        "provider",
        status_code=status_code,
        retryable=status_code == 429 or (status_code is not None and status_code >= 500),
    )


def test_503_uses_one_cross_model_fallback() -> None:
    calls: list[str] = []

    def primary() -> str:
        calls.append("primary")
        raise _error(503)

    def fallback() -> str:
        calls.append("fallback")
        return "ok"

    result = invoke_with_fallback(
        primary_call=primary,
        primary_model_name="gemini-3.7-flash",
        fallback_call=fallback,
        fallback_model_name="gemini-3.6-flash",
        operation="test",
    )

    assert result.value == "ok"
    assert result.model_name == "gemini-3.6-flash"
    assert result.used_fallback is True
    assert calls == ["primary", "fallback"]


@pytest.mark.parametrize("status_code", [400, 401, 403, 404, 429, None])
def test_non_5xx_errors_never_switch_models(status_code: int | None) -> None:
    calls: list[str] = []

    def primary() -> str:
        calls.append("primary")
        raise _error(status_code)

    def fallback() -> str:
        calls.append("fallback")
        return "unexpected"

    with pytest.raises(LLMProviderError) as exc_info:
        invoke_with_fallback(
            primary_call=primary,
            primary_model_name="gemini-3.7-flash",
            fallback_call=fallback,
            fallback_model_name="gemini-3.6-flash",
            operation="test",
        )

    assert exc_info.value.status_code == status_code
    assert calls == ["primary"]


def test_fallback_failure_is_not_replayed_again() -> None:
    calls: list[str] = []

    def primary() -> str:
        calls.append("primary")
        raise _error(503)

    def fallback() -> str:
        calls.append("fallback")
        raise _error(503)

    with pytest.raises(LLMProviderError):
        invoke_with_fallback(
            primary_call=primary,
            primary_model_name="gemini-3.7-flash",
            fallback_call=fallback,
            fallback_model_name="gemini-3.6-flash",
            operation="test",
        )

    assert calls == ["primary", "fallback"]


def test_failover_eligibility_is_5xx_only() -> None:
    assert is_cross_model_failover_eligible(_error(500)) is True
    assert is_cross_model_failover_eligible(_error(503)) is True
    assert is_cross_model_failover_eligible(_error(429)) is False
    assert is_cross_model_failover_eligible(_error(400)) is False


def test_provider_http_status_preserves_rate_limit_semantics() -> None:
    assert provider_error_http_status(_error(429)) == 429
    assert provider_error_http_status(_error(503)) == 503
    assert provider_error_http_status(_error(400)) == 502


def test_circuit_breaker_bypasses_repeated_unhealthy_primary() -> None:
    _reset_circuit_breakers_for_tests()
    calls: list[str] = []

    def primary() -> str:
        calls.append("primary")
        raise _error(503)

    def fallback() -> str:
        calls.append("fallback")
        return "ok"

    first = invoke_with_fallback(
        primary_call=primary,
        primary_model_name="gemini-3.7-flash-circuit-test",
        fallback_call=fallback,
        fallback_model_name="gemini-3.6-flash-circuit-test",
        operation="test",
        circuit_breaker_cooldown_seconds=120,
    )
    second = invoke_with_fallback(
        primary_call=primary,
        primary_model_name="gemini-3.7-flash-circuit-test",
        fallback_call=fallback,
        fallback_model_name="gemini-3.6-flash-circuit-test",
        operation="test",
        circuit_breaker_cooldown_seconds=120,
    )

    assert first.used_fallback is True
    assert second.used_fallback is True
    assert calls == ["primary", "fallback", "fallback"]
    _reset_circuit_breakers_for_tests()


def test_non_5xx_does_not_open_circuit() -> None:
    _reset_circuit_breakers_for_tests()
    calls: list[str] = []

    def primary() -> str:
        calls.append("primary")
        if len(calls) == 1:
            raise _error(400)
        return "primary-ok"

    def fallback() -> str:
        calls.append("fallback")
        return "fallback-ok"

    with pytest.raises(LLMProviderError):
        invoke_with_fallback(
            primary_call=primary,
            primary_model_name="gemini-3.7-flash-4xx-test",
            fallback_call=fallback,
            fallback_model_name="gemini-3.6-flash-4xx-test",
            operation="test",
            circuit_breaker_cooldown_seconds=120,
        )

    result = invoke_with_fallback(
        primary_call=primary,
        primary_model_name="gemini-3.7-flash-4xx-test",
        fallback_call=fallback,
        fallback_model_name="gemini-3.6-flash-4xx-test",
        operation="test",
        circuit_breaker_cooldown_seconds=120,
    )
    assert result.value == "primary-ok"
    assert calls == ["primary", "primary"]
    _reset_circuit_breakers_for_tests()



def test_three_model_chain_reaches_emergency_after_two_503s() -> None:
    from app.agents.llm_runtime import invoke_with_model_chain

    _reset_circuit_breakers_for_tests()
    calls: list[str] = []

    def lite() -> str:
        calls.append("lite")
        raise _error(503)

    def flash36() -> str:
        calls.append("3.6")
        raise _error(503)

    def flash35() -> str:
        calls.append("3.5")
        return "ok"

    result = invoke_with_model_chain(
        model_calls=[
            ("gemini-3.5-flash-lite-chain-test", lite),
            ("gemini-3.6-flash-chain-test", flash36),
            ("gemini-3.5-flash-chain-test", flash35),
        ],
        operation="test-chain",
        circuit_breaker_cooldown_seconds=120,
    )

    assert result.value == "ok"
    assert result.model_name == "gemini-3.5-flash-chain-test"
    assert result.used_fallback is True
    assert calls == ["lite", "3.6", "3.5"]
    _reset_circuit_breakers_for_tests()


def test_per_model_circuits_bypass_failed_models_on_next_turn() -> None:
    from app.agents.llm_runtime import invoke_with_model_chain

    _reset_circuit_breakers_for_tests()
    calls: list[str] = []

    def lite() -> str:
        calls.append("lite")
        raise _error(503)

    def flash36() -> str:
        calls.append("3.6")
        raise _error(503)

    def flash35() -> str:
        calls.append("3.5")
        return "ok"

    kwargs = {
        "model_calls": [
            ("gemini-3.5-flash-lite-circuit-chain", lite),
            ("gemini-3.6-flash-circuit-chain", flash36),
            ("gemini-3.5-flash-circuit-chain", flash35),
        ],
        "operation": "test-chain-circuit",
        "circuit_breaker_cooldown_seconds": 120,
    }

    first = invoke_with_model_chain(**kwargs)
    second = invoke_with_model_chain(**kwargs)

    assert first.model_name == "gemini-3.5-flash-circuit-chain"
    assert second.model_name == "gemini-3.5-flash-circuit-chain"
    assert calls == ["lite", "3.6", "3.5", "3.5"]
    _reset_circuit_breakers_for_tests()
