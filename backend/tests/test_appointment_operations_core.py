from datetime import UTC, datetime, timedelta
from pathlib import Path

from app.integrations.clinic.base import CancelAppointmentRequest, ClinicActionRequiresHuman
from app.integrations.clinic.tia_database import TiaDatabaseClinicAdapter
from app.services.appointment_operations import (
    AppointmentCancellationOverrideRequired,
    appointment_allowed_actions,
    cancellation_override_required,
)


def test_allowed_actions_follow_simplified_operational_state_machine() -> None:
    start = datetime(2026, 8, 25, 18, 0, tzinfo=UTC)
    before = start - timedelta(hours=1)
    after = start + timedelta(minutes=1)

    assert appointment_allowed_actions(appointment_status="pending", start_at=start, now=before) == (
        "confirm",
        "reschedule",
        "cancel",
    )
    assert appointment_allowed_actions(appointment_status="confirmed", start_at=start, now=before) == (
        "reschedule",
        "cancel",
    )
    assert appointment_allowed_actions(appointment_status="pending", start_at=start, now=after) == (
        "complete",
        "no_show",
    )
    assert appointment_allowed_actions(appointment_status="confirmed", start_at=start, now=after) == (
        "complete",
        "no_show",
    )
    # Legacy rows stay closable without reintroducing check-in/in-progress steps.
    assert appointment_allowed_actions(appointment_status="checked_in", start_at=start, now=after) == (
        "complete",
        "no_show",
    )
    assert appointment_allowed_actions(appointment_status="in_progress", start_at=start, now=after) == (
        "complete",
        "no_show",
    )
    assert appointment_allowed_actions(appointment_status="completed", start_at=start, now=after) == ()


def test_cancellation_override_is_only_for_future_pending_or_confirmed_inside_notice() -> None:
    start = datetime(2026, 8, 25, 18, 0, tzinfo=UTC)
    assert cancellation_override_required(
        appointment_status="confirmed",
        start_at=start,
        cancellation_notice_minutes=120,
        now=start - timedelta(minutes=90),
    ) is True
    assert cancellation_override_required(
        appointment_status="confirmed",
        start_at=start,
        cancellation_notice_minutes=120,
        now=start - timedelta(hours=3),
    ) is False
    assert cancellation_override_required(
        appointment_status="checked_in",
        start_at=start,
        cancellation_notice_minutes=120,
        now=start - timedelta(minutes=30),
    ) is False
    assert cancellation_override_required(
        appointment_status="confirmed",
        start_at=start,
        cancellation_notice_minutes=120,
        now=start + timedelta(minutes=1),
    ) is False


def test_dashboard_and_native_ai_adapter_share_one_operation_service() -> None:
    backend = Path(__file__).resolve().parent.parent
    route = (backend / "app/api/routes/booking.py").read_text(encoding="utf-8")
    adapter = (backend / "app/integrations/clinic/tia_database.py").read_text(encoding="utf-8")

    for name in (
        "confirm_appointment_operation",
        "cancel_appointment_operation",
        "reschedule_appointment_operation",
    ):
        assert name in route
        assert name in adapter

    assert "update_operational_status_operation" in route


def test_operation_service_serializes_writes_and_cancels_stale_appointment_jobs() -> None:
    backend = Path(__file__).resolve().parent.parent
    source = (backend / "app/services/appointment_operations.py").read_text(encoding="utf-8")

    assert ".with_for_update()" in source
    assert "AutomationJob.status.in_((\"queued\", \"failed\"))" in source
    assert 'job.status = "cancelled"' in source
    assert 'reason="appointment_rescheduled"' in source
    assert 'reason=f"appointment_{target_status}"' in source


def test_reschedule_preserves_existing_payment_state() -> None:
    backend = Path(__file__).resolve().parent.parent
    source = (backend / "app/services/appointment_operations.py").read_text(encoding="utf-8")

    assert "payment_status=current.payment_status" in source
    assert "amount_paid_minor=current.amount_paid_minor" in source
    assert "payment_method=current.payment_method" in source


def test_appointment_operations_ui_uses_verified_slots_and_backend_actions() -> None:
    root = Path(__file__).resolve().parents[2]
    detail = (root / "frontend/src/app/(dashboard)/appointments/[appointmentId]/page.tsx").read_text(encoding="utf-8")
    reschedule = (root / "frontend/src/app/(dashboard)/appointments/[appointmentId]/reschedule/page.tsx").read_text(encoding="utf-8")
    actions = (root / "frontend/src/app/(dashboard)/appointments/[appointmentId]/actions.ts").read_text(encoding="utf-8")
    listing = (root / "frontend/src/app/(dashboard)/appointments/page.tsx").read_text(encoding="utf-8")

    assert "/operations`" in detail
    assert "allowed_actions" in detail
    assert "/booking/availability?" in reschedule
    assert 'name="start_at" value={slot.start_at}' in reschedule
    assert "/confirm`" in actions
    assert "/cancel`" in actions
    assert "/reschedule`" in actions
    assert "/status`" in actions
    assert 'scope: "today"' not in listing
    assert 'date: selectedDate' in listing
    assert 'branch_id' in listing
    assert 'working_hours' in listing


def test_check_in_and_in_progress_are_not_exposed_as_new_operations() -> None:
    root = Path(__file__).resolve().parents[2]
    service = (root / "backend/app/services/appointment_operations.py").read_text(encoding="utf-8")
    schema = (root / "backend/app/schemas/booking.py").read_text(encoding="utf-8")
    detail = (root / "frontend/src/app/(dashboard)/appointments/[appointmentId]/page.tsx").read_text(encoding="utf-8")
    listing = (root / "frontend/src/app/(dashboard)/appointments/page.tsx").read_text(encoding="utf-8")
    types = (root / "frontend/src/lib/types.ts").read_text(encoding="utf-8")

    assert '"check_in"' not in service.split("AppointmentOperationAction =", 1)[1].split("]", 1)[0]
    assert '"start_session"' not in service.split("AppointmentOperationAction =", 1)[1].split("]", 1)[0]
    assert 'OperationalAppointmentStatus = Literal["completed", "no_show"]' in schema
    assert 'allowed.has("check_in")' not in detail
    assert 'allowed.has("start_session")' not in detail
    assert '["checked_in", "وصل"]' not in listing
    assert '["in_progress", "داخل الجلسة"]' not in listing
    assert '"check_in" | "start_session"' not in types


def test_completion_and_no_show_require_appointment_start_time() -> None:
    backend = Path(__file__).resolve().parent.parent
    source = (backend / "app/services/appointment_operations.py").read_text(encoding="utf-8")

    assert 'target_status in {"completed", "no_show"} and now < appointment.start_at' in source
    assert '"confirmed": {"completed", "no_show"}' in source
    assert '"pending": {"completed", "no_show"}' in source


def test_reschedule_canonical_contract_preserves_lineage_and_relationship_transfers() -> None:
    backend = Path(__file__).resolve().parent.parent
    source = (backend / "app/services/appointment_operations.py").read_text(encoding="utf-8")

    assert "rescheduled_from_appointment_id=current.id" in source
    assert 'current.status = "rescheduled"' in source
    assert "from_appointment_id=current.id" in source
    assert "to_appointment_id=replacement.id" in source
    assert "transfer_package_usage(" in source
    assert "from_appointment=current" in source
    assert "to_appointment=replacement" in source


def test_ai_cancellation_inside_notice_maps_to_human_handoff_contract() -> None:
    backend = Path(__file__).resolve().parent.parent
    source = (backend / "app/integrations/clinic/tia_database.py").read_text(encoding="utf-8")

    cancel_block = source.split("def cancel_appointment(", 1)[1].split("def reschedule_appointment(", 1)[0]
    assert "override_policy=False" in cancel_block
    assert "actor_is_admin=False" in cancel_block
    assert "except AppointmentCancellationOverrideRequired" in cancel_block
    assert "raise ClinicActionRequiresHuman(" in cancel_block



def test_ai_cancellation_outside_notice_calls_customer_path_without_override(monkeypatch) -> None:
    from types import SimpleNamespace
    from uuid import UUID

    workspace_id = UUID("11111111-1111-1111-1111-111111111111")
    patient_id = UUID("22222222-2222-2222-2222-222222222222")
    appointment_id = UUID("33333333-3333-3333-3333-333333333333")
    now = datetime(2026, 9, 21, 18, 0, tzinfo=UTC)
    captured = {}

    def fake_cancel(db, **kwargs):
        captured.update(kwargs)
        return SimpleNamespace(id=appointment_id)

    adapter = TiaDatabaseClinicAdapter(
        db=SimpleNamespace(),
        workspace=SimpleNamespace(id=workspace_id),
    )
    monkeypatch.setattr(adapter, "_require_local_appointment_write", lambda: None)
    monkeypatch.setattr(
        adapter,
        "_appointment_record",
        lambda *, appointment_id: SimpleNamespace(id=str(appointment_id)),
    )
    monkeypatch.setattr(
        "app.integrations.clinic.tia_database.cancel_appointment_operation",
        fake_cancel,
    )

    result = adapter.cancel_appointment(
        CancelAppointmentRequest(
            patient_id=str(patient_id),
            appointment_id=str(appointment_id),
            operation_id="cancel-outside-window",
            reason="customer requested",
            now=now,
        )
    )

    assert result.appointment.id == str(appointment_id)
    assert captured["override_policy"] is False
    assert captured["actor_is_admin"] is False
    assert captured["actor_type"] == "ai"
    assert captured["now"] == now


def test_ai_cancellation_inside_notice_maps_to_human_handoff(monkeypatch) -> None:
    from types import SimpleNamespace
    from uuid import UUID

    workspace_id = UUID("44444444-4444-4444-4444-444444444444")
    patient_id = UUID("55555555-5555-5555-5555-555555555555")
    appointment_id = UUID("66666666-6666-6666-6666-666666666666")

    def requires_override(db, **kwargs):
        raise AppointmentCancellationOverrideRequired("inside notice window")

    adapter = TiaDatabaseClinicAdapter(
        db=SimpleNamespace(),
        workspace=SimpleNamespace(id=workspace_id),
    )
    monkeypatch.setattr(adapter, "_require_local_appointment_write", lambda: None)
    monkeypatch.setattr(
        "app.integrations.clinic.tia_database.cancel_appointment_operation",
        requires_override,
    )

    try:
        adapter.cancel_appointment(
            CancelAppointmentRequest(
                patient_id=str(patient_id),
                appointment_id=str(appointment_id),
                operation_id="cancel-inside-window",
                reason="customer requested",
            )
        )
    except ClinicActionRequiresHuman as exc:
        assert exc.appointment_id == str(appointment_id)
    else:
        raise AssertionError("Expected customer cancellation inside notice window to require human handoff")


def test_eval_preflight_is_read_only() -> None:
    root = Path(__file__).resolve().parents[2]
    source = (root / "tools/agent_eval/clean_preflight.py").read_text(encoding="utf-8")
    assert "reset_demo_workspace(" not in source
    assert "services_expected_from_seed" in source
    assert "canonical_reset\": \"NOT_NEEDED" in source
