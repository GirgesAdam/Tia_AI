from datetime import UTC, datetime, timedelta
from pathlib import Path

from app.services.appointment_operations import (
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
    assert 'scope: "today"' not in listing  # default is derived, not hard-coded into API behavior
    assert 'const defaultScope = patientId ? "all" : "today"' in listing


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
