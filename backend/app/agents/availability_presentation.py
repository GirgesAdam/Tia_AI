from __future__ import annotations

from collections import defaultdict
from datetime import datetime
from typing import Any


def _parse_dt(value: object) -> datetime | None:
    if not isinstance(value, str) or not value.strip():
        return None
    try:
        return datetime.fromisoformat(value)
    except ValueError:
        return None


def _display_date(value: object) -> str:
    if not value:
        return ""
    try:
        parsed = datetime.fromisoformat(str(value))
    except ValueError:
        try:
            parsed = datetime.fromisoformat(f"{value}T00:00:00")
        except ValueError:
            return str(value)
    return parsed.strftime("%d/%m/%Y")


def _clock_ar(value: datetime) -> str:
    hour = value.hour
    minute = value.minute
    suffix = "ص" if hour < 12 else "م"
    display_hour = hour % 12 or 12
    if minute == 0:
        return f"{display_hour} {suffix}"
    return f"{display_hour}:{minute:02d} {suffix}"


def availability_windows_from_slots(slots: object) -> list[dict[str, Any]]:
    """Merge verified appointment slots into human-friendly free-time windows.

    Slots remain the execution authority. This function is presentation-only: it
    unions overlapping/touching intervals per doctor so a dense 15-minute grid is
    shown as e.g. 3 PM–6 PM, then 7 PM–9 PM around an existing booking.
    """
    if not isinstance(slots, list):
        return []

    grouped: dict[tuple[str, str], list[tuple[datetime, datetime]]] = defaultdict(list)
    for slot in slots:
        if not isinstance(slot, dict):
            continue
        start = _parse_dt(slot.get("start_local"))
        end = _parse_dt(slot.get("end_local"))
        if start is None or end is None or end <= start:
            continue
        doctor_id = str(slot.get("doctor_id") or "")
        doctor_name = (
            str(slot.get("doctor_name") or "الدكتور المتاح").strip()
            or "الدكتور المتاح"
        )
        grouped[(doctor_id, doctor_name)].append((start, end))

    windows: list[dict[str, Any]] = []
    for (doctor_id, doctor_name), intervals in grouped.items():
        intervals.sort(key=lambda item: (item[0], item[1]))
        merged: list[list[datetime]] = []
        for start, end in intervals:
            if not merged or start > merged[-1][1]:
                merged.append([start, end])
                continue
            if end > merged[-1][1]:
                merged[-1][1] = end

        for start, end in merged:
            windows.append(
                {
                    "doctor_id": doctor_id or None,
                    "doctor_name": doctor_name,
                    "start_local": start.isoformat(),
                    "end_local": end.isoformat(),
                    "start_time_24h": start.strftime("%H:%M"),
                    "end_time_24h": end.strftime("%H:%M"),
                }
            )

    windows.sort(
        key=lambda row: (
            str(row.get("doctor_name") or ""),
            str(row.get("start_local") or ""),
        )
    )
    return windows


def _requested_time(output: dict[str, Any]) -> str:
    requested = str(output.get("requested_start_time") or "").strip()
    if requested:
        return requested
    window = output.get("requested_time_window")
    if not isinstance(window, dict):
        return ""
    lower = str(window.get("not_before_time") or "").strip()
    upper = str(window.get("not_after_time") or "").strip()
    return lower if lower and lower == upper else ""


def _closing(*, reschedule: bool, booking_authorized: bool, ranges: bool) -> str:
    if reschedule:
        return (
            "قولي الوقت اللي يناسبك جوه الفترات دي عشان أغيّر الموعد."
            if ranges
            else "اختار الميعاد اللي يناسبك عشان أغيّره."
        )
    if booking_authorized:
        return (
            "قولي الوقت اللي يناسبك جوه الفترات دي عشان أحجزه."
            if ranges
            else "اختار الميعاد اللي يناسبك عشان أحجزه."
        )
    return (
        "لو حابب تحجز، قولي الوقت اللي يناسبك جوه الفترات دي."
        if ranges
        else "لو حابب تحجز، قولي الميعاد اللي يناسبك."
    )


def _legacy_slot_reply(
    output: dict[str, Any],
    slots: list[object],
    *,
    reschedule: bool,
    booking_authorized: bool,
) -> str | None:
    """Keep old persisted/fake tool payloads useful without exposing branch data.

    Real current availability payloads contain full interval timestamps and are
    rendered as continuous windows. This path exists only for older/minimal
    payloads that contain verified start times but not enough data to reconstruct
    the continuous interval safely.
    """
    by_doctor: dict[str, list[str]] = defaultdict(list)
    for slot in slots:
        if not isinstance(slot, dict):
            continue
        start = str(slot.get("start_time_24h") or "").strip()
        if not start:
            continue
        doctor = (
            str(slot.get("doctor_name") or "الدكتور المتاح").strip()
            or "الدكتور المتاح"
        )
        if start not in by_doctor[doctor]:
            by_doctor[doctor].append(start)

    lines: list[str] = []
    for doctor, starts in list(by_doctor.items())[:4]:
        if starts:
            lines.append(f"{doctor}: " + "، ".join(starts[:4]))
    if not lines:
        return None

    date_text = _display_date(output.get("date"))
    when = f" يوم {date_text}" if date_text else ""
    if output.get("requested_time_unavailable"):
        requested = _requested_time(output)
        requested_text = f" {requested}" if requested else ""
        intro = f"ميعاد{requested_text}{when} مش متاح. دي أقرب المواعيد المتاحة:"
    else:
        intro = (
            f"دي المواعيد البديلة المتاحة{when}:"
            if reschedule
            else f"دي أقرب المواعيد المتاحة{when}:"
        )
    return "\n".join(
        [intro, *lines, _closing(reschedule=reschedule, booking_authorized=booking_authorized, ranges=False)]
    )


def format_availability_windows_reply(
    output: dict[str, Any],
    *,
    reschedule: bool = False,
    booking_authorized: bool = True,
) -> str | None:
    if output.get("ok") is False:
        return None

    raw_slots = output.get("slots")
    slots = raw_slots if isinstance(raw_slots, list) else []
    windows = output.get("availability_windows")
    if not isinstance(windows, list) or not windows:
        windows = availability_windows_from_slots(slots)

    if not windows:
        if slots:
            return _legacy_slot_reply(
                output,
                slots,
                reschedule=reschedule,
                booking_authorized=booking_authorized,
            )

        date_text = _display_date(output.get("date"))
        when = f" يوم {date_text}" if date_text else ""
        requested_window = output.get("requested_time_window")
        has_requested_window = isinstance(requested_window, dict) and any(
            requested_window.get(key) for key in ("not_before_time", "not_after_time")
        )
        if has_requested_window or output.get("requested_time_unavailable"):
            return (
                f"مفيش مواعيد متاحة في الوقت المطلوب{when}. "
                "ممكن أشوفلك وقت تاني في نفس اليوم لو تحب."
            )
        return f"مفيش مواعيد متاحة{when}. ممكن أشوفلك يوم تاني لو تحب."

    by_doctor: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for window in windows:
        if not isinstance(window, dict):
            continue
        doctor = (
            str(window.get("doctor_name") or "الدكتور المتاح").strip()
            or "الدكتور المتاح"
        )
        by_doctor[doctor].append(window)

    lines: list[str] = []
    for doctor, doctor_windows in list(by_doctor.items())[:4]:
        ranges: list[str] = []
        for window in doctor_windows[:4]:
            start = _parse_dt(window.get("start_local"))
            end = _parse_dt(window.get("end_local"))
            if start is None or end is None:
                continue
            ranges.append(f"من {_clock_ar(start)} لـ{_clock_ar(end)}")
        if not ranges:
            continue
        joined = "، و".join(ranges)
        lines.append(f"المتاح مع {doctor} {joined}.")

    if not lines:
        return _legacy_slot_reply(
            output,
            slots,
            reschedule=reschedule,
            booking_authorized=booking_authorized,
        )

    date_text = _display_date(output.get("date"))
    intro = f"المتاح يوم {date_text}:" if date_text else "المتاح:"
    if output.get("requested_time_unavailable"):
        requested = _requested_time(output)
        requested_text = f" {requested}" if requested else ""
        when = f" يوم {date_text}" if date_text else ""
        intro = f"ميعاد{requested_text}{when} مش متاح. أقرب فترات متاحة:"

    return "\n".join(
        [intro, *lines, _closing(reschedule=reschedule, booking_authorized=booking_authorized, ranges=True)]
    )


_LOCATION_KEYS = {
    "branch",
    "branches",
    "branch_id",
    "branch_name",
    "branch_query",
    "branch_candidate_ids",
    "branch_ids",
    "scheduled_branch_ids",
    "preferred_branch_id",
    "primary_branch_id",
}


def customer_visible_verified_data(value: Any) -> Any:
    """Remove storage-level location metadata before customer-language composition."""
    if isinstance(value, dict):
        return {
            key: customer_visible_verified_data(item)
            for key, item in value.items()
            if key not in _LOCATION_KEYS
        }
    if isinstance(value, list):
        return [customer_visible_verified_data(item) for item in value]
    return value
