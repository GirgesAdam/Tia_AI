from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace
from uuid import uuid4

from app.agents import clinic_grounding
from app.integrations.clinic.base import (
    AppointmentReadRequest,
    AppointmentReadResult,
    AvailabilityRequest,
    AvailabilityResult,
    ClinicAdapter,
    ClinicCapabilities,
    ClinicCapability,
)
from app.integrations.clinic.registry import get_clinic_adapter
from app.integrations.clinic.tia_database import TiaDatabaseClinicAdapter


class _FakeAdapter(ClinicAdapter):
    def __init__(self) -> None:
        self.build_calls = 0

    @property
    def capabilities(self) -> ClinicCapabilities:
        return ClinicCapabilities(frozenset({ClinicCapability.CATALOG_READ}))

    def catalog_revision(self):
        return ("fake", 1)

    def get_availability(self, request: AvailabilityRequest) -> AvailabilityResult:
        raise NotImplementedError

    def get_patient_appointments(
        self, request: AppointmentReadRequest
    ) -> AppointmentReadResult:
        raise NotImplementedError

    def build_catalog(self):
        self.build_calls += 1
        return {
            "services": [{"id": "service-1", "name": "Laser"}],
            "branches": [],
            "doctors": [],
        }


def test_clinic_grounding_reads_catalog_through_adapter(monkeypatch) -> None:
    workspace = SimpleNamespace(id=uuid4())
    adapter = _FakeAdapter()

    with clinic_grounding._catalog_cache_lock:
        clinic_grounding._catalog_cache.clear()

    monkeypatch.setattr(
        clinic_grounding,
        "get_clinic_adapter",
        lambda **_: adapter,
    )

    first = clinic_grounding.build_clinic_catalog(object(), workspace)
    second = clinic_grounding.build_clinic_catalog(object(), workspace)

    assert first == second
    assert adapter.build_calls == 1
    first["services"][0]["name"] = "mutated"
    assert second["services"][0]["name"] == "Laser"


def test_default_workspace_adapter_is_tia_database_adapter() -> None:
    workspace = SimpleNamespace(id=uuid4())
    adapter = get_clinic_adapter(db=object(), workspace=workspace)
    assert isinstance(adapter, TiaDatabaseClinicAdapter)


def test_semantic_grounding_no_longer_imports_concrete_clinic_models() -> None:
    backend = Path(__file__).resolve().parent.parent
    source = (backend / "app/agents/clinic_grounding.py").read_text(encoding="utf-8")

    forbidden = (
        "from app.models.branch import Branch",
        "from app.models.doctor import Doctor",
        "from app.models.doctor_branch import DoctorBranch",
        "from app.models.doctor_service import DoctorService",
        "from app.models.service import Service",
        "from app.models.staff import Staff",
        "from app.models.working_hours import",
        "select(Service)",
        "select(Branch)",
        "select(Doctor",
    )
    for token in forbidden:
        assert token not in source


def test_tia_database_adapter_owns_native_catalog_mapping() -> None:
    backend = Path(__file__).resolve().parent.parent
    source = (backend / "app/integrations/clinic/tia_database.py").read_text(encoding="utf-8")

    assert "class TiaDatabaseClinicAdapter" in source
    assert "select(Service)" in source
    assert "select(Branch)" in source
    assert "select(Doctor, Staff)" in source
    assert '"services"' in source
    assert '"branches"' in source
    assert '"doctors"' in source


class _CatalogRevisionResult:
    def __init__(self, row):
        self._row = row

    def one(self):
        return self._row


class _CatalogRevisionDb:
    def __init__(self, row):
        self._row = row

    def execute(self, _statement):
        return _CatalogRevisionResult(self._row)


def test_tia_database_catalog_revision_uses_adapter_workspace_primary_branch() -> None:
    primary_branch_id = uuid4()
    workspace = SimpleNamespace(id=uuid4(), primary_branch_id=primary_branch_id)
    row = tuple(value for index in range(8) for value in (index + 1, None))
    adapter = TiaDatabaseClinicAdapter(
        db=_CatalogRevisionDb(row),
        workspace=workspace,
    )

    revision = adapter.catalog_revision()

    assert revision == (primary_branch_id, *row)
