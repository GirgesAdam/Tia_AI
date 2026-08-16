from app.agents.onboarding_planner import _provider_to_domain
from app.schemas.onboarding_provider import (
    OnboardingProviderDecision,
    ProviderBookingSettings,
    ProviderBranch,
    ProviderBranchHour,
    ProviderDoctor,
    ProviderDoctorBranch,
    ProviderDoctorHour,
    ProviderDoctorService,
    ProviderService,
)
from app.services.ai_onboarding import validate_plan


def test_flat_provider_dto_maps_to_executable_domain_plan() -> None:
    decision = OnboardingProviderDecision(
        action="propose",
        capabilities=[
            "branch_configuration",
            "service_configuration",
            "doctor_configuration",
            "schedule_configuration",
            "booking_settings_configuration",
        ],
        branches=[
            ProviderBranch(
                key="nasr-city",
                name="فرع مدينة نصر",
                code="nasr-city",
                city="Cairo",
            )
        ],
        services=[
            ProviderService(
                key="laser",
                name="ليزر إزالة الشعر",
                slug="laser-hair-removal",
                duration_minutes=60,
                price_minor=150000,
            )
        ],
        doctors=[
            ProviderDoctor(
                key="dr-ahmed",
                first_name="أحمد",
                last_name="محمود",
            )
        ],
        branch_hours=[
            ProviderBranchHour(
                branch_key="nasr-city",
                weekdays=[0],
                start_time="10:00:00",
                end_time="22:00:00",
            )
        ],
        doctor_branches=[
            ProviderDoctorBranch(
                doctor_key="dr-ahmed",
                branch_key="nasr-city",
                is_primary=True,
            )
        ],
        doctor_services=[
            ProviderDoctorService(
                doctor_key="dr-ahmed",
                service_key="laser",
            )
        ],
        doctor_hours=[
            ProviderDoctorHour(
                doctor_key="dr-ahmed",
                branch_key="nasr-city",
                weekdays=[0],
                start_time="10:00:00",
                end_time="22:00:00",
            )
        ],
        booking_settings=ProviderBookingSettings(
            apply=True,
            slot_interval_minutes=15,
            allow_same_day_booking=True,
            require_confirmation=True,
        ),
        missing_information=[],
        assistant_message="الخطة جاهزة للمراجعة.",
        confidence=0.98,
    )

    domain = _provider_to_domain(decision)
    assert validate_plan(domain.plan) == []
    assert domain.plan.branches[0].working_hours[0].start_time.hour == 10
    assert domain.plan.services[0].price_minor == 150000
    assert domain.plan.doctors[0].branch_keys == ["nasr-city"]
    assert domain.plan.doctors[0].service_keys == ["laser"]
    assert domain.plan.doctors[0].primary_branch_key == "nasr-city"
    assert domain.plan.booking_settings.slot_interval_minutes == 15



def test_compact_every_day_schedule_expands_to_seven_domain_rows() -> None:
    decision = OnboardingProviderDecision(
        action="propose",
        capabilities=[
            "branch_configuration",
            "service_configuration",
            "doctor_configuration",
            "schedule_configuration",
        ],
        assistant_message="الخطة جاهزة.",
        confidence=0.97,
        missing_information=[],
        booking_settings=ProviderBookingSettings(apply=False),
        branches=[
            ProviderBranch(
                key="nasr-city",
                name="فرع مدينة نصر",
                code="nasr-city",
            )
        ],
        services=[
            ProviderService(
                key="laser",
                name="ليزر إزالة الشعر",
                slug="laser-hair-removal",
                duration_minutes=60,
                price_minor=150000,
            )
        ],
        doctors=[
            ProviderDoctor(
                key="dr-ahmed",
                first_name="أحمد",
                last_name="محمود",
            )
        ],
        doctor_branches=[
            ProviderDoctorBranch(
                doctor_key="dr-ahmed",
                branch_key="nasr-city",
                is_primary=True,
            )
        ],
        doctor_services=[
            ProviderDoctorService(
                doctor_key="dr-ahmed",
                service_key="laser",
            )
        ],
        branch_hours=[
            ProviderBranchHour(
                branch_key="nasr-city",
                weekdays=[0, 1, 2, 3, 4, 5, 6],
                start_time="10:00:00",
                end_time="22:00:00",
            )
        ],
        doctor_hours=[
            ProviderDoctorHour(
                doctor_key="dr-ahmed",
                branch_key="nasr-city",
                weekdays=[0, 1, 2, 3, 4, 5, 6],
                start_time="10:00:00",
                end_time="22:00:00",
            )
        ],
    )

    domain = _provider_to_domain(decision)
    branch_hours = domain.plan.branches[0].working_hours
    doctor_hours = domain.plan.doctors[0].working_hours[0].intervals

    assert [row.weekday for row in branch_hours] == list(range(7))
    assert [row.weekday for row in doctor_hours] == list(range(7))
