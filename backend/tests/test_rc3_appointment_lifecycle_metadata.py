from __future__ import annotations

from datetime import UTC, datetime, timedelta
from types import SimpleNamespace
from uuid import uuid4

from app.agents.v2.turn_contract import DateConstraint, TurnEntities, TurnOperation
from app.integrations.clinic.base import AppointmentReadRequest, AppointmentRecord
from app.integrations.clinic.tia_database import TiaDatabaseClinicAdapter
from app.services.agent_v2.planner import PlanStep, ReadRequest
from app.services.agent_v2.read_executor import (
    ReadExecutionBundle,
    ReadExecutionContext,
    ReadResult,
    _appointment_payload,
    _read_appointments,
)
from app.services.agent_v2.state_executor import _new_reschedule_state

NOW = datetime(2026, 9, 24, 12, 0, tzinfo=UTC)


class _Rows:
    def __init__(self, values):
        self._values = list(values)

    def all(self):
        return list(self._values)


class _ReadDb:
    def __init__(self, rows):
        self.rows = rows

    def execute(self, _statement):
        return _Rows(self.rows)


class _AppointmentAdapter:
    def __init__(self, appointments):
        self.appointments = tuple(appointments)

    @property
    def capabilities(self):
        from app.integrations.clinic.base import ClinicCapabilities, ClinicCapability

        return ClinicCapabilities(frozenset({ClinicCapability.APPOINTMENTS_READ}))

    def require_capability(self, capability):
        self.capabilities.require(capability)

    def get_patient_appointments(self, _request):
        return SimpleNamespace(appointments=self.appointments)


def _record(
    *,
    billing_context: str = "standard",
    patient_package_id: str | None = None,
    package_external_id: str | None = None,
    device_key: str | None = "candela_gentle",
    visit_group_id: str | None = None,
    appointment_id: str | None = None,
) -> AppointmentRecord:
    return AppointmentRecord(
        appointment_id=appointment_id or str(uuid4()),
        patient_id=str(uuid4()),
        status="confirmed",
        service_id=str(uuid4()),
        service_name="Underarm Laser",
        branch_id=str(uuid4()),
        branch_name="Main",
        doctor_id=str(uuid4()),
        doctor_name="Dr Test",
        start_at=NOW + timedelta(days=1),
        end_at=NOW + timedelta(days=1, minutes=30),
        timezone="Africa/Cairo",
        price_minor=50_000,
        currency="EGP",
        payment_status="paid" if billing_context != "standard" else "unpaid",
        amount_paid_minor=0 if billing_context == "pulse_prepaid" else None,
        payment_method="unknown",
        billing_context=billing_context,
        package_external_id=package_external_id,
        patient_package_id=patient_package_id,
        laser_device_key=device_key,
        laser_device_name="Candela Gentle" if device_key else None,
        visit_group_id=visit_group_id,
    )


def _reschedule_state(record: AppointmentRecord):
    payload = _appointment_payload(record)
    reads = ReadExecutionBundle(
        results=[ReadResult(kind="appointments", ok=True, payload={"appointments": [payload]})]
    )
    operation = TurnOperation(
        type="reschedule",
        entities=TurnEntities(date=DateConstraint(mode="exact", start_date="2026-09-26")),
        execution_intent="execute",
    )
    step = PlanStep(
        operation_index=0,
        operation_type="reschedule",
        disposition="read",
        state_action="start_reschedule",
        response_goal="clarification",
        facts={"date": {"mode": "exact", "start_date": "2026-09-26"}},
    )
    return _new_reschedule_state(
        step=step,
        operation=operation,
        reads=reads,
        turn_id="rc3-test",
        now=NOW,
    )


def test_native_adapter_maps_verified_lifecycle_metadata() -> None:
    workspace_id = uuid4()
    patient_id = uuid4()
    package_id = uuid4()
    visit_group_id = uuid4()
    appointment = SimpleNamespace(
        id=uuid4(),
        patient_id=patient_id,
        status="confirmed",
        service_id=uuid4(),
        branch_id=uuid4(),
        doctor_id=uuid4(),
        start_at=NOW + timedelta(days=1),
        end_at=NOW + timedelta(days=1, minutes=30),
        price_minor=50_000,
        currency="EGP",
        payment_status="paid",
        amount_paid_minor=0,
        payment_method="unknown",
        billing_context="pulse_prepaid",
        package_external_id="PKG-EXT-1",
        patient_package_id=package_id,
        laser_device_key="candela_gentle",
        laser_device_name="Candela Gentle",
        visit_group_id=visit_group_id,
    )
    db = _ReadDb(
        [
            (
                appointment,
                "Underarm Laser",
                "Main",
                "Africa/Cairo",
                "Mariam",
                "Test",
            )
        ]
    )
    adapter = TiaDatabaseClinicAdapter(
        db=db,
        workspace=SimpleNamespace(id=workspace_id, timezone="Africa/Cairo"),
    )

    result = adapter.get_patient_appointments(
        AppointmentReadRequest(
            patient_id=str(patient_id),
            include_past=False,
            now=NOW,
        )
    )

    assert len(result.appointments) == 1
    row = result.appointments[0]
    assert row.billing_context == "pulse_prepaid"
    assert row.patient_package_id == str(package_id)
    assert row.package_external_id == "PKG-EXT-1"
    assert row.laser_device_key == "candela_gentle"
    assert row.laser_device_name == "Candela Gentle"
    assert row.visit_group_id == str(visit_group_id)


def test_standard_reschedule_state_preserves_verified_service_doctor_and_device() -> None:
    record = _record(billing_context="standard")
    state = _reschedule_state(record)

    assert state is not None
    assert state.target.appointment_id == record.appointment_id
    assert state.target.service_id == record.service_id
    assert state.target.doctor_id == record.doctor_id
    assert state.target.device_key == "candela_gentle"
    assert state.target.payment_context["billing_context"] == "standard"
    assert state.replacement.service_id == record.service_id
    assert state.replacement.doctor_id == record.doctor_id
    assert state.replacement.device_key == "candela_gentle"


def test_package_backed_reschedule_state_preserves_package_identity() -> None:
    package_id = str(uuid4())
    record = _record(
        billing_context="package_prepaid",
        patient_package_id=package_id,
        package_external_id="PKG-EXT-2",
    )
    state = _reschedule_state(record)

    assert state is not None
    assert state.target.payment_context["billing_context"] == "package_prepaid"
    assert state.target.payment_context["patient_package_id"] == package_id
    assert state.target.payment_context["package_external_id"] == "PKG-EXT-2"
    assert state.replacement.device_key == "candela_gentle"


def test_pulse_prepaid_reschedule_state_preserves_device_and_billing_context() -> None:
    record = _record(billing_context="pulse_prepaid")
    state = _reschedule_state(record)

    assert state is not None
    assert state.target.device_key == "candela_gentle"
    assert state.target.payment_context["billing_context"] == "pulse_prepaid"
    assert state.replacement.device_key == "candela_gentle"
    assert state.replacement.pulse_usage == "unspecified"


def test_real_appointment_ambiguity_remains_unresolved() -> None:
    patient_id = uuid4()
    rows = [
        _record(appointment_id=str(uuid4())),
        _record(appointment_id=str(uuid4())),
    ]
    adapter = _AppointmentAdapter(rows)
    context = ReadExecutionContext(
        db=SimpleNamespace(),
        workspace=SimpleNamespace(id=uuid4()),
        patient=SimpleNamespace(id=patient_id),
        now=NOW,
        adapter=adapter,
    )

    _result, verification, selected = _read_appointments(
        ReadRequest(kind="appointments", parameters={}),
        context,
        operation_type="reschedule",
    )

    assert verification.appointment_match_count == 2
    assert selected is None
    assert verification.verified_parameters == {}
