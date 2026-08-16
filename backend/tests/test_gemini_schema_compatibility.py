from pathlib import Path

from app.agents.structured_output import sanitize_gemini_json_schema
from app.schemas.onboarding_ai import OnboardingTurnDecision


LOCAL_ONLY = {
    "default",
    "examples",
    "pattern",
    "minLength",
    "maxLength",
    "exclusiveMinimum",
    "exclusiveMaximum",
    "multipleOf",
    "const",
}


def _keys(value):
    if isinstance(value, dict):
        for key, item in value.items():
            yield key
            yield from _keys(item)
    elif isinstance(value, list):
        for item in value:
            yield from _keys(item)


def test_onboarding_schema_contains_rich_local_pydantic_keywords() -> None:
    raw = OnboardingTurnDecision.model_json_schema()
    keys = set(_keys(raw))

    assert "default" in keys
    assert "pattern" in keys
    assert "minLength" in keys
    assert "exclusiveMinimum" in keys
    assert "$defs" in keys
    assert "$ref" in keys
    assert "anyOf" in keys


def test_provider_schema_removes_local_only_keywords_recursively() -> None:
    clean = sanitize_gemini_json_schema(
        OnboardingTurnDecision.model_json_schema()
    )
    clean_keys = set(_keys(clean))

    assert not (LOCAL_ONLY & clean_keys)


def test_provider_schema_uses_canonical_gemini_subset() -> None:
    clean = sanitize_gemini_json_schema(
        OnboardingTurnDecision.model_json_schema()
    )
    keys = set(_keys(clean))

    assert "properties" in keys
    assert "required" in keys
    assert "additionalProperties" in keys
    assert "items" in keys
    assert "minimum" in keys
    assert "maximum" in keys
    assert "format" in keys

    assert "$defs" not in keys
    assert "$ref" not in keys
    assert "anyOf" not in keys


def test_nullable_fields_are_type_arrays_after_canonicalization() -> None:
    clean = sanitize_gemini_json_schema(
        OnboardingTurnDecision.model_json_schema()
    )
    plan = clean["properties"]["plan"]
    branch = plan["properties"]["branches"]["items"]

    assert branch["properties"]["city"]["type"] == ["string", "null"]


def test_local_pydantic_validation_stays_strict_after_provider_sanitization() -> None:
    from pydantic import ValidationError
    from app.schemas.onboarding_ai import OnboardingServicePlan

    try:
        OnboardingServicePlan(
            key="laser",
            name="Laser",
            slug="INVALID SLUG",
            duration_minutes=30,
        )
    except ValidationError:
        pass
    else:
        raise AssertionError("Local regex validation must remain active.")


def test_runtime_catches_langchain_google_wrapper() -> None:
    backend = Path(__file__).resolve().parent.parent
    source = (
        backend / "app/agents/llm_runtime.py"
    ).read_text(encoding="utf-8")

    assert "ChatGoogleGenerativeAIError" in source
    assert "_status_from_exception" in source
    assert "except ChatGoogleGenerativeAIError as exc" in source
