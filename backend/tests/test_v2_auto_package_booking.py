from __future__ import annotations

from contextlib import nullcontext
from datetime import UTC, date, datetime
from types import SimpleNamespace
from uuid import uuid4

import pytest

from app.agents.v2.turn_contract import DateConstraint, TurnEntities, TurnOperation
from app.schemas.pulse_billing import PulsePackOfferRead
from app.services.agent_v2.package_booking_policy import (
    BookingPackagePolicyError,
    BookingPackageResolution,
    resolve_booking_package,
)
from app.services.agent_v2.planner import PlanStep, ReadRequest, WriteIntent
from app.services.agent_v2.read_executor import (
    ReadExecutionBundle,
    ReadExecutionContext,
    ReadResult,
    execute_step_reads,
)
from app.services.agent_v2.state_executor import apply_step_state
from app.services.agent_v2.write_executor import execute_write_ready_step


def _workspace():
    return SimpleNamespace(id=uuid4(), timezone="Africa/Cairo")


def _patient():
    return SimpleNamespace(id=uuid4(), status="active")


def _package(*, expires_at: date | None, device_key: str | None = None):
    return SimpleNamespace(
        id=uuid4(),
        name="Test package",
        expires_at=expires_at,
        purchased_at=datetime(2026, 1, 1, tzinfo=UTC),
        laser_device_key=device_key,
    )


def test_unspecified_booking_auto_uses_eligible_package_and_prefers_nearest_expiry(monkeypatch):
    later = _package(expires_at=date(2026, 12, 1))
    sooner = _package(expires_at=date(2026, 10, 1))
    captured = {}

    def fake_list(_db, **kwargs):
        captured.update(kwargs)
        return [later, sooner]

    monkeypatch.setattr(
        "app.services.agent_v2.package_booking_policy.list_patient_packages",
        fake_list,
    )
    workspace = _workspace()
    patient = _patient()
    service_id = uuid4()

    result = resolve_booking_package(
        object(),
        workspace=workspace,
        patient=patient,
        service_id=service_id,
        start_at=datetime(2026, 9, 15, 10, 0, tzinfo=UTC),
        device_key=None,
        package_usage="unspecified",
    )

    assert result.package_id == sooner.id
    assert result.package_used is True
    assert captured["workspace_id"] == workspace.id
    assert captured["patient_id"] == patient.id
    assert captured["service_id"] == service_id
    assert captured["usable_only"] is True
    assert captured["on_date"] == date(2026, 9, 15)


def test_auto_package_ignores_package_for_different_device(monkeypatch):
    wrong_device = _package(expires_at=date(2026, 10, 1), device_key="other_device")
    right_device = _package(expires_at=date(2026, 11, 1), device_key="prime_lase")
    monkeypatch.setattr(
        "app.services.agent_v2.package_booking_policy.list_patient_packages",
        lambda *_args, **_kwargs: [wrong_device, right_device],
    )

    result = resolve_booking_package(
        object(),
        workspace=_workspace(),
        patient=_patient(),
        service_id=uuid4(),
        start_at=datetime(2026, 9, 15, 10, 0, tzinfo=UTC),
        device_key="prime_lase",
        package_usage=None,
    )

    assert result.package_id == right_device.id


def test_auto_package_falls_back_to_standalone_when_no_matching_package(monkeypatch):
    monkeypatch.setattr(
        "app.services.agent_v2.package_booking_policy.list_patient_packages",
        lambda *_args, **_kwargs: [],
    )

    result = resolve_booking_package(
        object(),
        workspace=_workspace(),
        patient=_patient(),
        service_id=uuid4(),
        start_at=datetime(2026, 9, 15, 10, 0, tzinfo=UTC),
        device_key=None,
        package_usage="unspecified",
    )

    assert result.package_id is None
    assert result.package_used is False


def test_explicit_use_existing_never_silently_falls_back(monkeypatch):
    monkeypatch.setattr(
        "app.services.agent_v2.package_booking_policy.list_patient_packages",
        lambda *_args, **_kwargs: [],
    )

    with pytest.raises(BookingPackagePolicyError):
        resolve_booking_package(
            object(),
            workspace=_workspace(),
            patient=_patient(),
            service_id=uuid4(),
            start_at=datetime(2026, 9, 15, 10, 0, tzinfo=UTC),
            device_key=None,
            package_usage="use_existing",
        )


def test_explicit_standalone_opt_out_skips_existing_packages(monkeypatch):
    def should_not_read(*_args, **_kwargs):
        raise AssertionError("opt-out must not inspect or consume a package")

    monkeypatch.setattr(
        "app.services.agent_v2.package_booking_policy.list_patient_packages",
        should_not_read,
    )

    result = resolve_booking_package(
        object(),
        workspace=_workspace(),
        patient=_patient(),
        service_id=uuid4(),
        start_at=datetime(2026, 9, 15, 10, 0, tzinfo=UTC),
        device_key=None,
        package_usage="avoid_existing",
    )

    assert result.package_id is None
    assert result.package_used is False


def test_booking_slot_snapshot_preserves_package_policy_and_explicit_package():
    service_id = str(uuid4())
    doctor_id = str(uuid4())
    branch_id = str(uuid4())
    package_id = str(uuid4())
    operation = TurnOperation(
        type="book",
        entities=TurnEntities(
            date=DateConstraint(mode="exact", start_date="2026-09-15"),
        ),
        package_usage="avoid_existing",
        execution_intent="execute",
    )
    step = PlanStep(
        operation_index=0,
        operation_type="book",
        disposition="read",
        reads=[ReadRequest(kind="availability")],
        write_intent=WriteIntent(
            kind="booking",
            authorized=True,
            parameters={"service_id": service_id},
        ),
        state_action="start_booking",
        response_goal="present_availability",
        facts={
            "service_id": service_id,
            "package_id": package_id,
            "date": {"mode": "exact", "start_date": "2026-09-15", "end_date": None},
        },
    )
    reads = ReadExecutionBundle(
        results=[
            ReadResult(
                kind="availability",
                ok=True,
                payload={
                    "slots": [
                        {
                            "branch_id": branch_id,
                            "service_id": service_id,
                            "doctor_id": doctor_id,
                            "start_at": "2026-09-15T08:00:00+00:00",
                            "start_local": "2026-09-15T11:00:00+03:00",
                            "start_time_24h": "11:00",
                        }
                    ]
                },
            )
        ]
    )

    transition = apply_step_state(
        None,
        step=step,
        operation=operation,
        reads=reads,
        now=datetime(2026, 9, 12, tzinfo=UTC),
        turn_id="turn-1",
    )

    assert transition.active_task is not None
    snapshot = transition.active_task.option_snapshot
    assert snapshot is not None
    payload = snapshot.options[0].payload
    assert payload["package_usage"] == "avoid_existing"
    assert payload["package_id"] == package_id


def test_write_executor_passes_auto_resolved_package_to_canonical_booking(monkeypatch):
    package_id = uuid4()
    service_id = uuid4()
    branch_id = uuid4()
    doctor_id = uuid4()
    workspace = _workspace()
    patient = _patient()
    captured = {}

    monkeypatch.setattr(
        "app.services.agent_v2.write_executor.require_tia_workspace_domain_write",
        lambda *_args, **_kwargs: None,
    )
    monkeypatch.setattr(
        "app.services.agent_v2.write_executor.resolve_booking_package",
        lambda *_args, **_kwargs: BookingPackageResolution(
            package_id=package_id,
            package_name="PRP package",
            package_used=True,
            usage_mode="unspecified",
        ),
    )

    def fake_create(_db, **kwargs):
        captured.update(kwargs)
        return SimpleNamespace(id=uuid4(), status="confirmed")

    monkeypatch.setattr(
        "app.services.agent_v2.write_executor.create_appointment_operation",
        fake_create,
    )
    db = SimpleNamespace(begin_nested=lambda: nullcontext(), commit=lambda: None, rollback=lambda: None)
    step = PlanStep(
        operation_index=0,
        operation_type="book",
        disposition="write_ready",
        write_intent=WriteIntent(
            kind="booking",
            authorized=True,
            parameters={
                "branch_id": str(branch_id),
                "doctor_id": str(doctor_id),
                "service_id": str(service_id),
                "start_at": "2026-09-15T10:00:00+03:00",
                "package_usage": "unspecified",
            },
        ),
        response_goal="booking_completed",
    )

    result = execute_write_ready_step(
        db,
        workspace=workspace,
        patient=patient,
        step=step,
        commit=False,
    )

    assert result["ok"] is True
    assert captured["patient_package_id"] == package_id


def test_write_executor_uses_pulse_balance_without_auto_consuming_session_package(monkeypatch):
    service_id, branch_id, doctor_id = uuid4(), uuid4(), uuid4()
    workspace, patient = _workspace(), _patient()
    captured_resolver = {}
    captured_create = {}

    monkeypatch.setattr(
        "app.services.agent_v2.write_executor.require_tia_workspace_domain_write",
        lambda *_args, **_kwargs: None,
    )

    def fake_resolve(_db, **kwargs):
        captured_resolver.update(kwargs)
        return BookingPackageResolution(
            package_id=None,
            package_name=None,
            package_used=False,
            usage_mode=str(kwargs["package_usage"]),
        )

    monkeypatch.setattr(
        "app.services.agent_v2.write_executor.resolve_booking_package",
        fake_resolve,
    )

    def fake_create(_db, **kwargs):
        captured_create.update(kwargs)
        return SimpleNamespace(id=uuid4(), status="confirmed")

    monkeypatch.setattr(
        "app.services.agent_v2.write_executor.create_appointment_operation",
        fake_create,
    )
    db = SimpleNamespace(begin_nested=lambda: nullcontext(), commit=lambda: None, rollback=lambda: None)
    step = PlanStep(
        operation_index=0,
        operation_type="book",
        disposition="write_ready",
        write_intent=WriteIntent(
            kind="booking",
            authorized=True,
            parameters={
                "branch_id": str(branch_id),
                "doctor_id": str(doctor_id),
                "service_id": str(service_id),
                "device_key": "candela_gentle",
                "start_at": "2026-09-15T10:00:00+03:00",
                "package_usage": "unspecified",
                "pulse_usage": "use_existing",
            },
        ),
        response_goal="booking_completed",
    )

    result = execute_write_ready_step(
        db,
        workspace=workspace,
        patient=patient,
        step=step,
        commit=False,
    )

    assert result["ok"] is True
    assert result["pulse_balance_used"] is True
    assert result["billing_context"] == "pulse_prepaid"
    assert captured_resolver["package_usage"] == "avoid_existing"
    assert captured_create["patient_package_id"] is None
    assert captured_create["use_pulse_balance"] is True


def test_write_executor_fails_closed_on_package_and_pulse_double_entitlement(monkeypatch):
    service_id, branch_id, doctor_id = uuid4(), uuid4(), uuid4()
    workspace, patient = _workspace(), _patient()
    monkeypatch.setattr(
        "app.services.agent_v2.write_executor.require_tia_workspace_domain_write",
        lambda *_args, **_kwargs: None,
    )
    db = SimpleNamespace(begin_nested=lambda: nullcontext(), commit=lambda: None, rollback=lambda: None)
    step = PlanStep(
        operation_index=0,
        operation_type="book",
        disposition="write_ready",
        write_intent=WriteIntent(
            kind="booking",
            authorized=True,
            parameters={
                "branch_id": str(branch_id),
                "doctor_id": str(doctor_id),
                "service_id": str(service_id),
                "device_key": "candela_gentle",
                "start_at": "2026-09-15T10:00:00+03:00",
                "package_usage": "use_existing",
                "pulse_usage": "use_existing",
            },
        ),
        response_goal="booking_completed",
    )

    result = execute_write_ready_step(
        db,
        workspace=workspace,
        patient=patient,
        step=step,
        commit=False,
    )

    assert result["ok"] is False
    assert result["error_code"] == "write_failed"
    assert "cannot use a session package and pulse balance" in str(result["detail"])


def test_pulse_offer_read_filters_device_and_count(monkeypatch):
    workspace_id, patient_id = uuid4(), uuid4()
    rows = [
        PulsePackOfferRead(
            id=uuid4(),
            workspace_id=workspace_id,
            device_key="candela_gentle",
            device_name="Candela Gentle",
            pulses_count=2000,
            price_minor=400_000,
            currency="EGP",
            is_active=True,
            created_at=datetime(2026, 9, 1, tzinfo=UTC),
            updated_at=datetime(2026, 9, 1, tzinfo=UTC),
        ),
        PulsePackOfferRead(
            id=uuid4(),
            workspace_id=workspace_id,
            device_key="prime_lase",
            device_name="Prime Lase",
            pulses_count=2000,
            price_minor=350_000,
            currency="EGP",
            is_active=True,
            created_at=datetime(2026, 9, 1, tzinfo=UTC),
            updated_at=datetime(2026, 9, 1, tzinfo=UTC),
        ),
    ]
    monkeypatch.setattr(
        "app.services.agent_v2.read_executor.list_pulse_pack_offers",
        lambda *_args, **_kwargs: rows,
    )
    step = PlanStep(
        operation_index=0,
        operation_type="buy_pulse_pack",
        disposition="read",
        reads=[
            ReadRequest(
                kind="pulse_pack_offers",
                parameters={"device_key": "candela_gentle", "pulse_count": 2000},
            )
        ],
        write_intent=WriteIntent(
            kind="buy_pulse_pack",
            authorized=True,
            parameters={"device_key": "candela_gentle", "pulse_count": 2000},
        ),
        response_goal="pulse_pack_purchased",
    )
    context = ReadExecutionContext(
        db=object(),
        workspace=SimpleNamespace(id=workspace_id),
        patient=SimpleNamespace(id=patient_id),
        now=datetime(2026, 9, 23, tzinfo=UTC),
    )

    bundle = execute_step_reads(step, context)

    assert bundle.verification.pulse_offer_match_count == 1
    assert bundle.verification.verified_parameters["device_key"] == "candela_gentle"
    assert bundle.verification.verified_parameters["pulse_count"] == 2000
    assert bundle.verification.verified_parameters["price_minor"] == 400_000


def test_write_executor_buys_verified_pulse_pack_without_assumed_payment(monkeypatch):
    workspace = _workspace()
    patient = _patient()
    offer_id = uuid4()
    captured = {}

    monkeypatch.setattr(
        "app.services.agent_v2.write_executor.purchase_pulse_pack_offer",
        lambda _db, **kwargs: (
            captured.update(kwargs)
            or SimpleNamespace(
                id=uuid4(),
                status="active",
                sale_price_minor=400_000,
                currency="EGP",
            )
        ),
    )
    db = SimpleNamespace(
        begin_nested=lambda: nullcontext(),
        commit=lambda: None,
        rollback=lambda: None,
    )
    step = PlanStep(
        operation_index=0,
        operation_type="buy_pulse_pack",
        disposition="write_ready",
        write_intent=WriteIntent(
            kind="buy_pulse_pack",
            authorized=True,
            parameters={
                "pulse_pack_offer_id": str(offer_id),
                "device_key": "candela_gentle",
                "pulse_count": 2000,
                "price_minor": 400_000,
                "currency": "EGP",
            },
        ),
        response_goal="pulse_pack_purchased",
    )

    result = execute_write_ready_step(
        db,
        workspace=workspace,
        patient=patient,
        step=step,
        idempotency_key="pulse-v2-test",
        commit=False,
    )

    assert result["ok"] is True
    assert result["amount_paid_minor"] == 0
    assert captured["offer_id"] == offer_id
    assert captured["amount_paid_minor"] == 0
    assert captured["payment_method"] == "unknown"
    assert captured["actor_type"] == "ai"
