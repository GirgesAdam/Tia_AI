from pathlib import Path

from app.schemas.onboarding_ai import (
    OnboardingBranchPlan,
    OnboardingDoctorPlan,
    OnboardingPlan,
    OnboardingServicePlan,
    OnboardingWorkingHour,
)
from app.services.ai_onboarding import validate_plan


def test_plan_accepts_realistic_clinic_configuration() -> None:
    plan = OnboardingPlan(
        branches=[
            OnboardingBranchPlan(
                key="nasr-city",
                name="فرع مدينة نصر",
                code="nasr-city",
                city="Cairo",
                apply_working_hours=True,
                working_hours=[
                    OnboardingWorkingHour(
                        weekday=0,
                        start_time="10:00",
                        end_time="22:00",
                    )
                ],
            )
        ],
        services=[
            OnboardingServicePlan(
                key="laser",
                name="ليزر إزالة الشعر",
                slug="laser-hair-removal",
                duration_minutes=60,
                price_minor=150000,
            )
        ],
        doctors=[
            OnboardingDoctorPlan(
                key="dr-ahmed",
                first_name="أحمد",
                last_name="محمود",
                branch_keys=["nasr-city"],
                primary_branch_key="nasr-city",
                service_keys=["laser"],
            )
        ],
    )
    assert validate_plan(plan) == []


def test_plan_rejects_cross_reference_to_missing_branch() -> None:
    plan = OnboardingPlan(
        services=[
            OnboardingServicePlan(
                key="laser",
                name="ليزر",
                slug="laser",
                duration_minutes=30,
            )
        ],
        doctors=[
            OnboardingDoctorPlan(
                key="doctor",
                first_name="سارة",
                last_name="علي",
                branch_keys=["missing"],
                service_keys=["laser"],
            )
        ],
    )
    errors = validate_plan(plan)
    assert any("unknown branch key" in item for item in errors)


def test_onboarding_has_no_keyword_confirmation_shortcut() -> None:
    backend = Path(__file__).resolve().parent.parent
    source = "\n".join(
        (backend / relative).read_text(encoding="utf-8")
        for relative in (
            "app/agents/onboarding_planner.py",
            "app/services/ai_onboarding.py",
        )
    )
    assert 'if "ايوة" in' not in source
    assert 'if "confirm" in message' not in source
    assert 'decision.action == "confirm"' in source


def test_write_requires_awaiting_confirmation_state() -> None:
    backend = Path(__file__).resolve().parent.parent
    source = (backend / "app/services/ai_onboarding.py").read_text(encoding="utf-8")
    assert 'session.status != "awaiting_confirmation"' in source
    assert 'session.status = "executing"' in source
    assert 'session.status = "completed"' in source


def test_overlapping_branch_hours_are_rejected_by_schema() -> None:
    import pytest
    from pydantic import ValidationError

    with pytest.raises(ValidationError):
        OnboardingBranchPlan(
            key="branch",
            name="فرع",
            code="branch",
            apply_working_hours=True,
            working_hours=[
                OnboardingWorkingHour(weekday=0, start_time="10:00", end_time="15:00"),
                OnboardingWorkingHour(weekday=0, start_time="14:00", end_time="18:00"),
            ],
        )


def test_onboarding_api_surfaces_provider_errors_without_generic_500() -> None:
    backend = Path(__file__).resolve().parent.parent
    source = (backend / "app/api/routes/onboarding.py").read_text(encoding="utf-8")
    assert "except StructuredOutputError" in source
    assert "except LLMProviderError" in source
