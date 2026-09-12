from app.agents.availability_presentation import availability_windows_from_slots
from app.services.agent_v2.planner import PlanStep, ReadRequest, VerificationFacts, WriteIntent
from app.services.agent_v2.read_executor import ReadExecutionBundle, ReadResult
from app.services.agent_v2.write_policy import advance_step_with_write_policies


def _slot(start: str, end: str) -> dict[str, object]:
    return {
        "doctor_id": "d1",
        "doctor_name": "د. مريم",
        "laser_device_key": "candela",
        "laser_device_name": "Candela Gentle",
        "start_local": f"2026-09-12T{start}:00+03:00",
        "end_local": f"2026-09-12T{end}:00+03:00",
    }


def _cancel_step() -> PlanStep:
    return PlanStep(
        operation_index=0,
        operation_type="cancel_appointment",
        disposition="read",
        reads=[ReadRequest(kind="appointments")],
        write_intent=WriteIntent(
            kind="cancel_appointment",
            authorized=True,
            parameters={},
        ),
        response_goal="cancellation_completed",
    )


def _appointment_bundle(**overrides: object) -> ReadExecutionBundle:
    appointment = {
        "appointment_id": "apt-1",
        "service_name": "هيدرافيشل",
        "doctor_name": "د. سارة",
        "start_local": "2026-09-17T18:00:00+03:00",
        "payment_status": "unpaid",
        "amount_paid_minor": 0,
        "billing_context": "standard",
        "patient_package_id": None,
        "package_external_id": None,
        **overrides,
    }
    return ReadExecutionBundle(
        results=[ReadResult(kind="appointments", ok=True, payload={"appointments": [appointment]})],
        verification=VerificationFacts(
            appointment_match_count=1,
            verified_parameters={"appointment_id": "apt-1"},
        ),
    )


def test_regular_discrete_start_times_are_presented_as_one_range() -> None:
    windows = availability_windows_from_slots(
        [
            _slot("18:00", "18:30"),
            _slot("19:00", "19:30"),
            _slot("20:00", "20:30"),
        ]
    )

    assert len(windows) == 1
    assert windows[0]["start_time_24h"] == "18:00"
    assert windows[0]["end_time_24h"] == "20:00"


def test_irregular_start_times_do_not_hide_a_real_gap() -> None:
    windows = availability_windows_from_slots(
        [
            _slot("18:00", "18:30"),
            _slot("19:00", "19:30"),
            _slot("21:00", "21:30"),
        ]
    )

    assert len(windows) == 3


def test_unpaid_appointment_can_reach_cancel_write_ready() -> None:
    advanced = advance_step_with_write_policies(_cancel_step(), _appointment_bundle())

    assert advanced.disposition == "write_ready"


def test_paid_appointment_cancellation_hands_off_before_write() -> None:
    advanced = advance_step_with_write_policies(
        _cancel_step(),
        _appointment_bundle(payment_status="paid", amount_paid_minor=120_000),
    )

    assert advanced.disposition == "handoff"
    assert advanced.response_goal == "handoff"
    assert advanced.facts["reason"] == "financial_cancellation_requires_staff"


def test_package_backed_appointment_cancellation_hands_off_before_write() -> None:
    advanced = advance_step_with_write_policies(
        _cancel_step(),
        _appointment_bundle(
            payment_status="paid",
            billing_context="package_prepaid",
            patient_package_id="pkg-1",
        ),
    )

    assert advanced.disposition == "handoff"
