from app.agents.structured_output import canonicalize_gemini_json_schema
from app.schemas.onboarding_provider import OnboardingProviderDecision


def _all_keys(value):
    if isinstance(value, dict):
        for key, item in value.items():
            yield key
            yield from _all_keys(item)
    elif isinstance(value, list):
        for item in value:
            yield from _all_keys(item)


def test_provider_schema_contains_pydantic_refs_and_nullable_anyof_before_conversion() -> None:
    raw = OnboardingProviderDecision.model_json_schema()
    keys = set(_all_keys(raw))
    assert "$defs" in keys
    assert "$ref" in keys
    assert "anyOf" in keys


def test_canonical_schema_has_no_defs_refs_or_anyof() -> None:
    schema = canonicalize_gemini_json_schema(OnboardingProviderDecision.model_json_schema())
    keys = set(_all_keys(schema))

    assert "$defs" not in keys
    assert "$ref" not in keys
    assert "anyOf" not in keys


def test_nullable_provider_fields_use_type_array() -> None:
    schema = canonicalize_gemini_json_schema(OnboardingProviderDecision.model_json_schema())
    branch = schema["properties"]["branches"]["items"]
    city_type = branch["properties"]["city"]["type"]

    assert city_type == ["string", "null"]


def test_supported_schema_constraints_are_preserved() -> None:
    schema = canonicalize_gemini_json_schema(OnboardingProviderDecision.model_json_schema())
    doctor_hours = schema["properties"]["doctor_hours"]["items"]
    weekdays = doctor_hours["properties"]["weekdays"]
    weekday = weekdays["items"]

    assert weekdays["type"] == "array"
    assert weekdays["minItems"] == 1
    assert weekdays["maxItems"] == 7
    assert weekday["type"] == "integer"
    assert weekday["minimum"] == 0
    assert weekday["maximum"] == 6
    assert doctor_hours["additionalProperties"] is False
