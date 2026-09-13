from __future__ import annotations

from datetime import UTC, datetime, timedelta
from types import SimpleNamespace
from uuid import uuid4

from app.integrations.clinic.base import (
    AppointmentReadResult,
    AppointmentRecord,
    AvailabilityResult,
    AvailabilitySlot,
)
from app.services.agent_v2.planner import ReadRequest
from app.services.agent_v2.read_executor import (
    ReadExecutionContext,
    _read_appointments,
    _read_group_reschedule_availability,
)

PATIENT_ID = uuid4()
BRANCH_ID = uuid4()
DOCTOR_ID = uuid4()
SERVICE_A = uuid4()
SERVICE_B = uuid4()
GROUP_ID = uuid4()
APPT_A = uuid4()
APPT_B = uuid4()
OLD_A = datetime(2026, 9, 15, 7, 0, tzinfo=UTC)
OLD_B = datetime(2026, 9, 15, 7, 30, tzinfo=UTC)


def _appointment(*, appointment_id, group_id, service_id, start_at):
    return AppointmentRecord(
        appointment_id=str(appointment_id),
        patient_id=str(PATIENT_ID),
        status="confirmed",
        service_id=str(service_id),
        service_name=f"Service {service_id}",
        branch_id=str(BRANCH_ID),
        branch_name="Main",
        doctor_id=str(DOCTOR_ID),
        doctor_name="Doctor",
        start_at=start_at,
        end_at=start_at + timedelta(minutes=30),
        timezone="Africa/Cairo",
        price_minor=10_000,
        currency="EGP",
        visit_group_id=str(group_id),
    )


ROWS = (
    _appointment(
        appointment_id=APPT_A,
        group_id=GROUP_ID,
        service_id=SERVICE_A,
        start_at=OLD_A,
    ),
    _appointment(
        appointment_id=APPT_B,
        group_id=GROUP_ID,
        service_id=SERVICE_B,
        start_at=OLD_B,
    ),
)


class AppointmentAdapter:
    def require_capability(self, _capability):
        return None

    def get_patient_appointments(self, _request):
        return AppointmentReadResult(appointments=ROWS)


def _context(adapter):
    return ReadExecutionContext(
        db=SimpleNamespace(),
        workspace=SimpleNamespace(
            timezone="Africa/Cairo",
            primary_branch_id=BRANCH_ID,
            name="Clinic",
        ),
        patient=SimpleNamespace(id=PATIENT_ID),
        now=datetime(2026, 9, 13, 8, 0, tzinfo=UTC),
        adapter=adapter,
    )


def test_general_cancel_treats_group_as_one_logical_visit():
    result, verification, selected = _read_appointments(
        ReadRequest(kind="appointments"),
        _context(AppointmentAdapter()),
        operation_type="cancel_appointment",
    )
    assert verification.appointment_match_count == 1
    assert verification.verified_parameters["visit_group_id"] == str(GROUP_ID)
    assert verification.verified_parameters["appointment_ids"] == [
        str(APPT_A),
        str(APPT_B),
    ]
    assert selected is not None and len(selected) == 2
    assert result.payload["visit_count"] == 1
    assert len(result.payload["visits"]) == 1


def test_explicit_service_scope_keeps_one_component():
    _result, verification, selected = _read_appointments(
        ReadRequest(
            kind="appointments",
            parameters={"service_id": str(SERVICE_B)},
        ),
        _context(AppointmentAdapter()),
        operation_type="cancel_appointment",
    )
    assert verification.appointment_match_count == 1
    assert verification.verified_parameters["appointment_id"] == str(APPT_B)
    assert "appointment_ids" not in verification.verified_parameters
    assert selected is not None and len(selected) == 1


class AvailabilityAdapter(AppointmentAdapter):
    def __init__(self):
        self.exclusion_sets = []

    def get_availability(self, request):
        self.exclusion_sets.append(set(request.exclude_appointment_ids))
        assert set(request.exclude_appointment_ids) == {
            str(APPT_A),
            str(APPT_B),
        }
        start = (
            datetime(2026, 9, 15, 8, 0, tzinfo=UTC)
            if request.service_id == str(SERVICE_A)
            else datetime(2026, 9, 15, 8, 30, tzinfo=UTC)
        )
        slot = AvailabilitySlot(
            branch_id=str(BRANCH_ID),
            branch_name="Main",
            doctor_id=str(DOCTOR_ID),
            doctor_name="Doctor",
            service_id=request.service_id,
            service_name="Service",
            start_at=start,
            end_at=start + timedelta(minutes=30),
            duration_minutes=30,
            price_minor=10_000,
            currency="EGP",
        )
        return AvailabilityResult(
            timezone="Africa/Cairo",
            branch_id=str(BRANCH_ID),
            branch_name="Main",
            service_id=request.service_id,
            service_name="Service",
            service_duration_minutes=30,
            service_price_minor=10_000,
            service_currency="EGP",
            slots=(slot,),
        )


def test_group_reschedule_verifies_every_component_excluding_whole_old_group():
    adapter = AvailabilityAdapter()
    result, verification = _read_group_reschedule_availability(
        ReadRequest(
            kind="availability",
            parameters={
                "date": {"mode": "exact", "start_date": "2026-09-15"},
                "time": {"mode": "exact", "start_time": "11:00"},
                "reschedule": True,
            },
        ),
        _context(adapter),
        appointments=list(ROWS),
    )
    assert result.ok is True
    assert verification.exact_slot_match_count == 1
    components = verification.verified_parameters["reschedule_components"]
    assert [item["appointment_id"] for item in components] == [
        str(APPT_A),
        str(APPT_B),
    ]
    assert [item["start_at"] for item in components] == [
        "2026-09-15T08:00:00+00:00",
        "2026-09-15T08:30:00+00:00",
    ]
    assert len(adapter.exclusion_sets) >= 2



def test_group_reschedule_excludes_prior_replacements(monkeypatch):
    from app.services.agent_v2 import grouped_visit_operations as grouped_ops

    replacement_a = SimpleNamespace(id=uuid4())
    replacement_b = SimpleNamespace(id=uuid4())
    members = [SimpleNamespace(id=APPT_A), SimpleNamespace(id=APPT_B)]
    exclusion_calls = []

    monkeypatch.setattr(
        grouped_ops,
        "_visit_members",
        lambda *_args, **_kwargs: members,
    )

    def fake_reschedule(*_args, appointment_id, exclude_appointment_ids, **_kwargs):
        exclusion_calls.append(set(exclude_appointment_ids))
        replacement = replacement_a if appointment_id == APPT_A else replacement_b
        return replacement, SimpleNamespace(id=appointment_id)

    monkeypatch.setattr(grouped_ops, "reschedule_appointment_operation", fake_reschedule)

    class NestedScope:
        def __enter__(self):
            return self

        def __exit__(self, _exc_type, _exc, _tb):
            return False

    components = [
        {
            "appointment_id": str(APPT_A),
            "branch_id": str(BRANCH_ID),
            "doctor_id": str(DOCTOR_ID),
            "service_id": str(SERVICE_A),
            "start_at": datetime(2026, 9, 15, 8, 0, tzinfo=UTC).isoformat(),
        },
        {
            "appointment_id": str(APPT_B),
            "branch_id": str(BRANCH_ID),
            "doctor_id": str(DOCTOR_ID),
            "service_id": str(SERVICE_B),
            "start_at": datetime(2026, 9, 15, 8, 30, tzinfo=UTC).isoformat(),
        },
    ]
    moved = grouped_ops.reschedule_visit_group_operation(
        SimpleNamespace(begin_nested=lambda: NestedScope()),
        workspace=SimpleNamespace(id=uuid4()),
        patient_id=PATIENT_ID,
        visit_group_id=GROUP_ID,
        appointment_ids=(APPT_A, APPT_B),
        components=components,
    )

    assert len(moved) == 2
    assert exclusion_calls[0] == {APPT_A, APPT_B}
    assert exclusion_calls[1] == {APPT_A, APPT_B, replacement_a.id}
