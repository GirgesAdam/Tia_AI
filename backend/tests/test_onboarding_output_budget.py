import pytest
from pydantic import ValidationError

from app.agents.structured_output import canonicalize_gemini_json_schema
from app.core.config import settings
from app.schemas.onboarding_provider import OnboardingProviderDecision


def test_onboarding_has_its_own_larger_output_budget() -> None:
    assert settings.gemini_onboarding_max_output_tokens == 8192
    assert settings.gemini_onboarding_max_output_tokens > settings.llm_max_output_tokens


def test_all_provider_top_level_fields_remain_required() -> None:
    schema = canonicalize_gemini_json_schema(OnboardingProviderDecision.model_json_schema())

    properties = set(schema["properties"])
    required = set(schema["required"])

    assert required == properties
    assert {
        "doctor_branches",
        "doctor_services",
        "doctor_hours",
        "booking_settings",
        "missing_information",
        "assistant_message",
        "confidence",
    }.issubset(required)


def test_partial_payload_like_observed_truncation_fails_closed() -> None:
    partial = {
        "action": "propose",
        "capabilities": [
            "branch_configuration",
            "service_configuration",
            "doctor_configuration",
            "schedule_configuration",
        ],
        "branches": [],
        "services": [],
        "doctors": [],
        "branch_hours": [],
    }

    with pytest.raises(ValidationError):
        OnboardingProviderDecision.model_validate(partial)


def test_every_day_schedule_is_compact_in_provider_schema() -> None:
    payload = OnboardingProviderDecision.model_validate(
        {
            "action": "propose",
            "capabilities": ["schedule_configuration"],
            "assistant_message": "الخطة جاهزة.",
            "confidence": 0.9,
            "missing_information": [],
            "booking_settings": {
                "apply": False,
                "slot_interval_minutes": 15,
                "minimum_notice_minutes": 60,
                "booking_horizon_days": 90,
                "cancellation_notice_minutes": 720,
                "allow_same_day_booking": True,
                "require_confirmation": True,
                "default_currency": "EGP",
            },
            "branches": [],
            "services": [],
            "doctors": [],
            "doctor_branches": [],
            "doctor_services": [],
            "branch_hours": [
                {
                    "branch_key": "nasr-city",
                    "weekdays": [0, 1, 2, 3, 4, 5, 6],
                    "start_time": "10:00:00",
                    "end_time": "22:00:00",
                }
            ],
            "doctor_hours": [],
        }
    )

    assert len(payload.branch_hours) == 1
    assert payload.branch_hours[0].weekdays == list(range(7))
