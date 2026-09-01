from __future__ import annotations

from datetime import UTC, datetime, timedelta
from pathlib import Path
from types import SimpleNamespace
from uuid import uuid4

import pytest

from app.integrations.clinic.base import (
    AppointmentReadRequest,
    AppointmentReadResult,
    AppointmentRecord,
    AvailabilityRequest,
    AvailabilityResult,
    ClinicAdapter,
    ClinicCapabilities,
    ClinicCapability,
    ClinicCapabilityNotSupported,
)
from app.integrations.clinic.tia_database import TiaDatabaseClinicAdapter


class _CatalogAndAvailabilityAdapter(ClinicAdapter):
    @property
    def capabilities(self) -> ClinicCapabilities:
        return ClinicCapabilities(
            frozenset(
                {
                    ClinicCapability.CATALOG_READ,
                    ClinicCapability.AVAILABILITY_READ,
                }
            )
        )

    def build_catalog(self):
        return {"services": [], "branches": [], "doctors": []}

    def get_availability(self, request: AvailabilityRequest) -> AvailabilityResult:
        raise NotImplementedError

    def get_patient_appointments(
        self, request: AppointmentReadRequest
    ) -> AppointmentReadResult:
        self.require_capability(ClinicCapability.APPOINTMENTS_READ)
        raise AssertionError("unreachable")


def test_capabilities_block_unsupported_appointment_reads() -> None:
    adapter = _CatalogAndAvailabilityAdapter()

    with pytest.raises(ClinicCapabilityNotSupported):
        adapter.get_patient_appointments(
            AppointmentReadRequest(patient_id="sheet-patient-42")
        )


def test_appointment_read_request_ids_are_source_agnostic_strings() -> None:
    request = AppointmentReadRequest(
        patient_id="PATIENT-EXCEL-42",
        include_past=True,
        limit=15,
    )

    assert request.patient_id == "PATIENT-EXCEL-42"
    assert request.include_past is True
    assert request.limit == 15


def test_tia_database_adapter_maps_native_appointment_to_canonical_record() -> None:
    workspace_id = uuid4()
    patient_id = uuid4()
    appointment_id = uuid4()
    service_id = uuid4()
    branch_id = uuid4()
    doctor_id = uuid4()
    start = datetime(2026, 8, 25, 16, 0, tzinfo=UTC)

    appointment = SimpleNamespace(
        id=appointment_id,
        patient_id=patient_id,
        service_id=service_id,
        branch_id=branch_id,
        doctor_id=doctor_id,
        status="confirmed",
        start_at=start,
        end_at=start + timedelta(minutes=45),
        price_minor=140000,
        currency="EGP",
    )

    class _ExecuteResult:
        @staticmethod
        def all():
            return [
                (
                    appointment,
                    "Full Face Laser",
                    "New Cairo",
                    "Africa/Cairo",
                    "Sara",
                    "Ali",
                )
            ]

    class _Db:
        def execute(self, _stmt):
            return _ExecuteResult()

    adapter = TiaDatabaseClinicAdapter(
        db=_Db(),
        workspace=SimpleNamespace(id=workspace_id, timezone="Africa/Cairo"),
    )

    result = adapter.get_patient_appointments(
        AppointmentReadRequest(
            patient_id=str(patient_id),
            include_past=False,
            now=datetime(2026, 8, 22, tzinfo=UTC),
        )
    )

    assert isinstance(result, AppointmentReadResult)
    assert len(result.appointments) == 1
    record = result.appointments[0]
    assert isinstance(record, AppointmentRecord)
    assert record.appointment_id == str(appointment_id)
    assert record.patient_id == str(patient_id)
    assert record.status == "confirmed"
    assert record.service_id == str(service_id)
    assert record.service_name == "Full Face Laser"
    assert record.branch_id == str(branch_id)
    assert record.branch_name == "New Cairo"
    assert record.doctor_id == str(doctor_id)
    assert record.doctor_name == "Sara Ali"
    assert record.timezone == "Africa/Cairo"
    assert record.price_minor == 140000
    assert record.currency == "EGP"


def test_invalid_native_patient_id_is_rejected_at_adapter_boundary() -> None:
    adapter = TiaDatabaseClinicAdapter(
        db=object(),
        workspace=SimpleNamespace(id=uuid4(), timezone="Africa/Cairo"),
    )

    with pytest.raises(ValueError):
        adapter.get_patient_appointments(
            AppointmentReadRequest(patient_id="PATIENT-EXCEL-42")
        )


def test_customer_appointment_tool_reads_through_adapter_not_native_table() -> None:
    backend = Path(__file__).resolve().parent.parent
    source = (backend / "app/agents/tools/clinic_tools.py").read_text(encoding="utf-8")

    start = source.index("    def get_customer_appointments(")
    end = source.index("\n    @tool\n    def book_appointment(", start)
    function_source = source[start:end]

    assert "_adapter_patient_appointments(" in function_source
    assert "_canonical_appointment_summary(" in function_source
    assert "select(Appointment)" not in function_source
    assert "ctx.db.scalars" not in function_source


def test_native_adapter_owns_appointment_read_query() -> None:
    backend = Path(__file__).resolve().parent.parent
    source = (
        backend / "app/integrations/clinic/tia_database.py"
    ).read_text(encoding="utf-8")

    assert "def get_patient_appointments(" in source
    assert "select(" in source
    assert "Appointment.patient_id == patient_id" in source
    assert "Appointment.status.in_(ACTIVE_APPOINTMENT_STATUSES)" in source
