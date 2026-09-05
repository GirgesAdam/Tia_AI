from __future__ import annotations

from app.agents.availability_presentation import (
    availability_windows_from_slots,
    customer_visible_verified_data,
    format_availability_windows_reply,
)
from app.agents.semantic_actions import (
    format_booking_success,
    select_slot_from_structured_selection,
)


def _slot(
    *,
    doctor_id: str,
    doctor_name: str,
    start: str,
    end: str,
    branch_name: str = "Internal Main Branch",
) -> dict[str, object]:
    return {
        "doctor_id": doctor_id,
        "doctor_name": doctor_name,
        "branch_id": "internal-branch-id",
        "branch_name": branch_name,
        "service_id": "service-id",
        "service_name": "Underarm Laser",
        "start_local": f"2026-09-10T{start}:00+03:00",
        "end_local": f"2026-09-10T{end}:00+03:00",
        "start_time_24h": start,
        "end_time_24h": end,
    }


def test_touching_quarter_hour_slots_become_one_human_window() -> None:
    slots = [
        _slot(doctor_id="d1", doctor_name="د. مريم", start="15:00", end="15:15"),
        _slot(doctor_id="d1", doctor_name="د. مريم", start="15:15", end="15:30"),
        _slot(doctor_id="d1", doctor_name="د. مريم", start="15:30", end="15:45"),
        _slot(doctor_id="d1", doctor_name="د. مريم", start="15:45", end="16:00"),
    ]

    windows = availability_windows_from_slots(slots)

    assert len(windows) == 1
    assert windows[0]["start_time_24h"] == "15:00"
    assert windows[0]["end_time_24h"] == "16:00"


def test_existing_booking_splits_availability_into_two_windows() -> None:
    slots = [
        _slot(doctor_id="d1", doctor_name="د. مريم", start="15:00", end="16:00"),
        _slot(doctor_id="d1", doctor_name="د. مريم", start="16:00", end="17:00"),
        _slot(doctor_id="d1", doctor_name="د. مريم", start="17:00", end="18:00"),
        _slot(doctor_id="d1", doctor_name="د. مريم", start="19:00", end="20:00"),
        _slot(doctor_id="d1", doctor_name="د. مريم", start="20:00", end="21:00"),
    ]

    windows = availability_windows_from_slots(slots)

    assert [(row["start_time_24h"], row["end_time_24h"]) for row in windows] == [
        ("15:00", "18:00"),
        ("19:00", "21:00"),
    ]


def test_windows_never_merge_different_doctors() -> None:
    slots = [
        _slot(doctor_id="d1", doctor_name="د. مريم", start="15:00", end="18:00"),
        _slot(doctor_id="d2", doctor_name="د. سارة", start="15:00", end="18:00"),
    ]

    windows = availability_windows_from_slots(slots)

    assert len(windows) == 2
    assert {row["doctor_id"] for row in windows} == {"d1", "d2"}


def test_customer_reply_uses_ranges_not_quarter_hour_grid_or_branch() -> None:
    slots = [
        _slot(doctor_id="d1", doctor_name="د. مريم", start="15:00", end="15:15"),
        _slot(doctor_id="d1", doctor_name="د. مريم", start="15:15", end="15:30"),
        _slot(doctor_id="d1", doctor_name="د. مريم", start="15:30", end="15:45"),
        _slot(doctor_id="d1", doctor_name="د. مريم", start="15:45", end="16:00"),
        _slot(doctor_id="d1", doctor_name="د. مريم", start="19:00", end="20:00"),
        _slot(doctor_id="d1", doctor_name="د. مريم", start="20:00", end="21:00"),
    ]
    payload = {
        "ok": True,
        "date": "2026-09-10",
        "branch": {"branch_name": "Internal Main Branch"},
        "slots": slots,
        "availability_windows": availability_windows_from_slots(slots),
    }

    reply = format_availability_windows_reply(payload, booking_authorized=True)

    assert reply is not None
    assert "المتاح مع د. مريم من 3 م لـ4 م، ومن 7 م لـ9 م." in reply
    assert "15:15" not in reply
    assert "15:30" not in reply
    assert "Internal Main Branch" not in reply
    assert "فرع" not in reply
    assert "قولي الوقت" in reply


def test_booking_success_does_not_expose_internal_branch() -> None:
    reply = format_booking_success(
        {
            "status": "confirmed",
            "service": "ليزر إبط",
            "branch": "Internal Main Branch",
            "doctor": "د. مريم",
            "start_local": "2026-09-10T15:00:00+03:00",
            "end_local": "2026-09-10T15:15:00+03:00",
            "price": "550 EGP",
        }
    )

    assert "Internal Main Branch" not in reply
    assert "فرع" not in reply
    assert "ليزر إبط" in reply
    assert "د. مريم" in reply


def test_time_selection_does_not_silently_choose_between_doctors() -> None:
    booking_output = {
        "ok": True,
        "slots": [
            _slot(doctor_id="d1", doctor_name="د. مريم", start="15:00", end="15:15"),
            _slot(doctor_id="d2", doctor_name="د. سارة", start="15:00", end="15:15"),
        ],
    }

    selected = select_slot_from_structured_selection(
        booking_output,
        selection_index=None,
        selection_time="15:00",
    )

    assert selected is None


def test_time_selection_uses_explicit_doctor_when_same_time_is_shared() -> None:
    booking_output = {
        "ok": True,
        "slots": [
            _slot(doctor_id="d1", doctor_name="د. مريم", start="15:00", end="15:15"),
            _slot(doctor_id="d2", doctor_name="د. سارة", start="15:00", end="15:15"),
        ],
    }

    selected = select_slot_from_structured_selection(
        booking_output,
        selection_index=None,
        selection_time="15:00",
        doctor_id="d2",
    )

    assert selected is not None
    assert selected["doctor_id"] == "d2"


def test_legacy_numbered_slot_selection_still_works() -> None:
    booking_output = {
        "ok": True,
        "slots": [
            _slot(doctor_id="d1", doctor_name="د. مريم", start="15:00", end="15:15"),
            _slot(doctor_id="d1", doctor_name="د. مريم", start="15:15", end="15:30"),
        ],
    }

    selected = select_slot_from_structured_selection(
        booking_output,
        selection_index=2,
        selection_time=None,
    )

    assert selected is not None
    assert selected["start_time_24h"] == "15:15"


def test_customer_composer_data_strips_all_storage_location_fields() -> None:
    value = {
        "branch": {"branch_id": "b1", "branch_name": "Main"},
        "catalog": {
            "branches": [{"id": "b1", "name": "Main"}],
            "doctors": [
                {
                    "name": "د. مريم",
                    "branch_ids": ["b1"],
                    "scheduled_branch_ids": ["b1"],
                    "service_ids": ["s1"],
                }
            ],
        },
        "service": {"name": "ليزر إبط"},
    }

    clean = customer_visible_verified_data(value)

    encoded = str(clean)
    assert "branch" not in encoded.lower()
    assert "Main" not in encoded
    assert "ليزر إبط" in encoded
