from datetime import UTC, datetime, timedelta
from pathlib import Path
from types import SimpleNamespace

from app.agents.availability_presentation import availability_windows_from_slots
from app.services.booking import _overlaps_existing


def test_active_booking_is_excluded_before_customer_windows_are_built() -> None:
    """Customer-facing ranges must be built only from bookable starts.

    A one-hour booking from 18:00 to 19:00 for the requested doctor should split
    an otherwise continuous 15:00-22:00 day into 15:00-18:00 and 19:00-22:00.
    The occupied hour and every service start that would overlap it are removed
    before the presentation layer receives the slots.
    """
    doctor_id = "doctor-mariam"
    busy_start = datetime(2026, 9, 10, 18, 0, tzinfo=UTC)
    busy_end = datetime(2026, 9, 10, 19, 0, tzinfo=UTC)
    existing = [
        SimpleNamespace(
            busy_start_at=busy_start,
            busy_end_at=busy_end,
        )
    ]

    service_duration = timedelta(hours=1)
    day_end = datetime(2026, 9, 10, 22, 0, tzinfo=UTC)
    candidate = datetime(2026, 9, 10, 15, 0, tzinfo=UTC)
    verified_slots: list[dict[str, str]] = []

    while candidate + service_duration <= day_end:
        service_end = candidate + service_duration
        if not _overlaps_existing(candidate, service_end, existing):
            verified_slots.append(
                {
                    "doctor_id": doctor_id,
                    "doctor_name": "مريم",
                    "start_local": candidate.isoformat(),
                    "end_local": service_end.isoformat(),
                }
            )
        candidate += timedelta(minutes=15)

    assert all(
        not (
            datetime.fromisoformat(slot["start_local"]) < busy_end
            and datetime.fromisoformat(slot["end_local"]) > busy_start
        )
        for slot in verified_slots
    )

    windows = availability_windows_from_slots(verified_slots)
    assert [
        (window["start_time_24h"], window["end_time_24h"])
        for window in windows
    ] == [("15:00", "18:00"), ("19:00", "22:00")]


def test_booking_engine_filters_active_appointments_before_appending_slots() -> None:
    """Lock the production ordering that makes the presentation invariant true."""
    source = (
        Path(__file__).resolve().parents[1] / "app" / "services" / "booking.py"
    ).read_text(encoding="utf-8")

    active_query = source.index("Appointment.status.in_(ACTIVE_APPOINTMENT_STATUSES)")
    overlap_filter = source.index("not _overlaps_existing(", active_query)
    slot_append = source.index("slots.append(", overlap_filter)

    assert active_query < overlap_filter < slot_append


def test_manual_live_review_is_transcript_first_and_never_runs_all_cases_by_default() -> None:
    """Live LLM cost and UX judgement stay explicit and human-reviewed."""
    source = (
        Path(__file__).resolve().parents[1]
        / "scripts"
        / "run_live_agent_manual_review.py"
    ).read_text(encoding="utf-8")

    assert 'quality_scoring": "manual_transcript_review"' in source
    assert 'required=True' in source
    assert 'default_names' not in source
    assert '"PASS"' not in source
    assert '"FAIL"' not in source


def test_demo_chat_uses_the_exact_production_agent_endpoint_and_service() -> None:
    """Demo may change auth/data limits, never the customer Agent implementation."""
    repo = Path(__file__).resolve().parents[2]
    demo_action = (
        repo
        / "frontend"
        / "src"
        / "app"
        / "(dashboard)"
        / "agent-demo"
        / "actions.ts"
    ).read_text(encoding="utf-8")
    production_route = (
        repo / "backend" / "app" / "api" / "routes" / "agent.py"
    ).read_text(encoding="utf-8")

    assert 'tiaRequest<AgentChatResponse>("/agent/chat"' in demo_action
    assert "from app.services.agent_chat import AgentChatError, run_agent_chat" in production_route
    assert "return run_agent_chat(" in production_route
    assert "/demo/agent" not in demo_action
