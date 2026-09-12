from __future__ import annotations

from contextlib import nullcontext
from datetime import UTC, datetime
from types import SimpleNamespace
from uuid import uuid4

from app.services.agent_v2 import write_executor
from app.services.agent_v2.package_booking_policy import (
    BookingPackageResolution,
    resolve_booking_package,
)
from app.services.agent_v2.planner import PlanStep, WriteIntent


def test_explicit_standalone_overrides_negative_package_reference(monkeypatch) -> None:
    def should_not_read(*_args, **_kwargs):
        raise AssertionError("explicit standalone intent must bypass package resolution")

    monkeypatch.setattr(
        "app.services.agent_v2.package_booking_policy.list_patient_packages",
        should_not_read,
    )
    result = resolve_booking_package(
        object(),
        workspace=SimpleNamespace(id=uuid4(), timezone="Africa/Cairo"),
        patient=SimpleNamespace(id=uuid4()),
        service_id=uuid4(),
        start_at=datetime(2026, 9, 15, 10, 0, tzinfo=UTC),
        device_key="candela_gentle",
        package_usage="avoid_existing",
        requested_package_id=uuid4(),
    )

    assert result.package_id is None
    assert result.package_used is False
    assert result.usage_mode == "avoid_existing"


def test_completed_package_booking_exposes_verified_package_use_without_internal_id(monkeypatch) -> None:
    package_id = uuid4()
    appointment = SimpleNamespace(id=uuid4(), status="confirmed")
    workspace = SimpleNamespace(id=uuid4(), timezone="Africa/Cairo")
    patient = SimpleNamespace(id=uuid4(), status="active")
    captured = {}

    monkeypatch.setattr(
        write_executor,
        "require_tia_workspace_domain_write",
        lambda *_args, **_kwargs: None,
    )
    monkeypatch.setattr(
        write_executor,
        "resolve_booking_package",
        lambda *_args, **_kwargs: BookingPackageResolution(
            package_id=package_id,
            package_name="PRP package",
            package_used=True,
            usage_mode="unspecified",
        ),
    )

    def create(_db, **kwargs):
        captured.update(kwargs)
        return appointment

    monkeypatch.setattr(write_executor, "create_appointment_operation", create)
    db = SimpleNamespace(begin_nested=lambda: nullcontext(), commit=lambda: None, rollback=lambda: None)
    step = PlanStep(
        operation_index=0,
        operation_type="book",
        disposition="write_ready",
        write_intent=WriteIntent(
            kind="booking",
            authorized=True,
            parameters={
                "branch_id": str(uuid4()),
                "doctor_id": str(uuid4()),
                "service_id": str(uuid4()),
                "start_at": "2026-09-15T10:00:00+03:00",
                "package_usage": "unspecified",
            },
        ),
        response_goal="booking_completed",
    )

    result = write_executor.execute_write_ready_step(
        db,
        workspace=workspace,
        patient=patient,
        step=step,
        commit=False,
    )

    assert result["ok"] is True
    assert result["package_used"] is True
    assert result["package_name"] == "PRP package"
    assert "patient_package_id" not in result
    assert captured["patient_package_id"] == package_id
