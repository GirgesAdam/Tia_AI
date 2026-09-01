from __future__ import annotations

from datetime import UTC, date, datetime, timedelta
from types import SimpleNamespace
from uuid import uuid4

import pytest

from app.integrations.clinic.base import (
    AppointmentReadRequest,
    AppointmentReadResult,
    AvailabilityRequest,
    AvailabilityResult,
    AvailabilitySlot,
    ClinicAdapter,
    ClinicCapabilities,
    ClinicCapability,
    ClinicCapabilityNotSupported,
)
from app.integrations.clinic.tia_database import TiaDatabaseClinicAdapter


class _CatalogOnlyAdapter(ClinicAdapter):
    @property
    def capabilities(self) -> ClinicCapabilities:
        return ClinicCapabilities(frozenset({ClinicCapability.CATALOG_READ}))

    def build_catalog(self):
        return {"services": [], "branches": [], "doctors": []}

    def get_availability(self, request: AvailabilityRequest) -> AvailabilityResult:
        self.require_capability(ClinicCapability.AVAILABILITY_READ)
        raise AssertionError("unreachable")

    def get_patient_appointments(
        self, request: AppointmentReadRequest
    ) -> AppointmentReadResult:
        self.require_capability(ClinicCapability.APPOINTMENTS_READ)
        raise AssertionError("unreachable")


def test_capabilities_block_unsupported_availability() -> None:
    adapter = _CatalogOnlyAdapter()

    assert adapter.capabilities.supports(ClinicCapability.CATALOG_READ)
    assert not adapter.capabilities.supports(ClinicCapability.AVAILABILITY_READ)

    with pytest.raises(ClinicCapabilityNotSupported):
        adapter.get_availability(
            AvailabilityRequest(
                branch_id="sheet-branch-a",
                service_id="sheet-service-1",
                booking_date=date(2026, 8, 25),
            )
        )


def test_availability_request_ids_are_source_agnostic_strings() -> None:
    request = AvailabilityRequest(
        branch_id="BRANCH-TAGAMO3",
        service_id="LASER-FULL-FACE",
        doctor_id="DR-SARA",
        booking_date=date(2026, 8, 25),
    )

    assert request.branch_id == "BRANCH-TAGAMO3"
    assert request.service_id == "LASER-FULL-FACE"
    assert request.doctor_id == "DR-SARA"


def test_tia_database_adapter_wraps_existing_availability_engine(monkeypatch) -> None:
    from app.integrations.clinic import tia_database

    workspace_id = uuid4()
    branch_id = uuid4()
    service_id = uuid4()
    doctor_id = uuid4()

    branch = SimpleNamespace(
        id=branch_id,
        workspace_id=workspace_id,
        is_active=True,
        name="New Cairo",
    )
    service = SimpleNamespace(
        id=service_id,
        workspace_id=workspace_id,
        is_active=True,
        name="Full Face Laser",
        duration_minutes=45,
        price_minor=140000,
        currency="EGP",
    )
    start = datetime(2026, 8, 25, 16, 0, tzinfo=UTC)
    native_slot = SimpleNamespace(
        branch_id=branch_id,
        doctor_id=doctor_id,
        service_id=service_id,
        start_at=start,
        end_at=start + timedelta(minutes=45),
        duration_minutes=45,
        price_minor=140000,
        currency="EGP",
    )

    captured: dict[str, object] = {}

    def fake_calculate_availability(**kwargs):
        captured.update(kwargs)
        return "Africa/Cairo", [native_slot]

    monkeypatch.setattr(tia_database, "calculate_availability", fake_calculate_availability)

    class _ExecuteResult:
        @staticmethod
        def all():
            return [(doctor_id, "Sara", "Ali")]

    class _Db:
        def get(self, model, identity):
            if model is tia_database.Branch and identity == branch_id:
                return branch
            if model is tia_database.Service and identity == service_id:
                return service
            raise AssertionError("unexpected identity lookup")

        def execute(self, _stmt):
            return _ExecuteResult()

    db = _Db()
    workspace = SimpleNamespace(id=workspace_id)
    adapter = TiaDatabaseClinicAdapter(db=db, workspace=workspace)

    result = adapter.get_availability(
        AvailabilityRequest(
            branch_id=str(branch_id),
            service_id=str(service_id),
            doctor_id=str(doctor_id),
            booking_date=date(2026, 8, 25),
        )
    )

    assert captured["preloaded_branch"] is branch
    assert captured["preloaded_service"] is service
    assert captured["branch_id"] == branch_id
    assert captured["service_id"] == service_id
    assert captured["doctor_id"] == doctor_id

    assert result.timezone == "Africa/Cairo"
    assert result.branch_id == str(branch_id)
    assert result.branch_name == "New Cairo"
    assert result.service_id == str(service_id)
    assert result.service_name == "Full Face Laser"
    assert result.service_duration_minutes == 45
    assert result.service_price_minor == 140000
    assert len(result.slots) == 1

    slot = result.slots[0]
    assert isinstance(slot, AvailabilitySlot)
    assert slot.doctor_id == str(doctor_id)
    assert slot.doctor_name == "Sara Ali"
    assert slot.duration_minutes == 45
    assert slot.price_minor == 140000


def test_tia_database_adapter_declares_booking_capabilities() -> None:
    adapter = TiaDatabaseClinicAdapter(
        db=object(),
        workspace=SimpleNamespace(id=uuid4()),
    )

    expected = {
        ClinicCapability.CATALOG_READ,
        ClinicCapability.AVAILABILITY_READ,
        ClinicCapability.APPOINTMENTS_READ,
        ClinicCapability.APPOINTMENTS_CREATE,
        ClinicCapability.APPOINTMENTS_CONFIRM,
        ClinicCapability.APPOINTMENTS_CANCEL,
        ClinicCapability.APPOINTMENTS_RESCHEDULE,
        ClinicCapability.PATIENTS_READ,
        ClinicCapability.PAYMENTS_READ,
    }
    assert adapter.capabilities.supported == frozenset(expected)


def test_agent_tools_no_longer_call_native_availability_engine_directly() -> None:
    from pathlib import Path

    backend = Path(__file__).resolve().parent.parent
    tool_source = (backend / "app/agents/tools/clinic_tools.py").read_text(encoding="utf-8")
    adapter_source = (
        backend / "app/integrations/clinic/tia_database.py"
    ).read_text(encoding="utf-8")

    assert "calculate_availability(" not in tool_source
    assert "_adapter_availability(" in tool_source
    assert "calculate_availability(" in adapter_source
