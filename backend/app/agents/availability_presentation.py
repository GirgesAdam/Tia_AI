from __future__ import annotations

from collections import defaultdict
from datetime import datetime
from typing import Any

from app.services.laser_slot_metadata import decode_laser_slot_branch


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


def _device_from_slot(slot: dict[str, Any]) -> tuple[str, str]:
    device_key = str(slot.get("laser_device_key") or "").strip()
    device_name = str(slot.get("laser_device_name") or "").strip()
    if device_key or device_name:
        return device_key, device_name
    metadata = decode_laser_slot_branch(slot.get("branch_name"))
    return metadata.device_key or "", metadata.device_name or ""


def _regular_start_range(
    intervals: list[tuple[datetime, datetime]],
) -> tuple[datetime, datetime] | None:
    """Summarize a regular sequence of available start-times without hiding real gaps.

    Example: 18:00, 19:00, 20:00 becomes the customer-facing start range 18:00–20:00.
    We require at least three starts with one consistent cadence no larger than one hour. A missing
    middle slot breaks the cadence, so genuinely interrupted availability remains split.
    """

    starts = sorted({start for start, _end in intervals})
    if len(starts) < 3:
        return None
    deltas = [
        int((current - previous).total_seconds())
        for previous, current in zip(starts, starts[1:], strict=True)
    ]
    if not deltas or len(set(deltas)) != 1:
        return None
    cadence = deltas[0]
    if cadence <= 0 or cadence > 60 * 60:
        return None
    return starts[0], starts[-1]


def availability_windows_from_slots(slots: object) -> list[dict[str, Any]]:
    if not isinstance(slots, list):
        return []

    grouped: dict[tuple[str, str, str, str], list[tuple[datetime, datetime]]] = defaultdict(list)
    for slot in slots:
        if not isinstance(slot, dict):
            continue
        start = _parse_dt(slot.get("start_local"))
        end = _parse_dt(slot.get("end_local"))
        if start is None or end is None or end <= start:
            continue
        doctor_id = str(slot.get("doctor_id") or "")
        doctor_name = str(slot.get("doctor_name") or "الدكتور المتاح").strip() or "الدكتور المتاح"
        device_key, device_name = _device_from_slot(slot)
        grouped[(doctor_id, doctor_name, device_key, device_name)].append((start, end))

    windows: list[dict[str, Any]] = []
    for (doctor_id, doctor_name, device_key, device_name), intervals in grouped.items():
        intervals.sort(key=lambda item: (item[0], item[1]))
        merged: list[list[datetime]] = []
        for start, end in intervals:
            if not merged or start > merged[-1][1]:
                merged.append([start, end])
                continue
            if end > merged[-1][1]:
                merged[-1][1] = end

        # Some booking engines expose a regular grid of valid appointment start-times rather than
        # one continuous free interval. Presenting 18:00, 19:00, 20:00 separately is noisy; when the
        # cadence itself proves there is no missing grid point, expose the compact start range 18–20.
        regular_range = _regular_start_range(intervals) if len(merged) > 1 else None
        if regular_range is not None:
            start, end = regular_range
            windows.append(
                {
                    "doctor_id": doctor_id or None,
                    "doctor_name": doctor_name,
                    "laser_device_key": device_key or None,
                    "laser_device_name": device_name or None,
                    "start_local": start.isoformat(),
                    "end_local": end.isoformat(),
                    "start_time_24h": start.strftime("%H:%M"),
                    "end_time_24h": end.strftime("%H:%M"),
                }
            )
            continue

        for start, end in merged:
            windows.append(
                {
                    "doctor_id": doctor_id or None,
                    "doctor_name": doctor_name,
                    "laser_device_key": device_key or None,
                    "laser_device_name": device_name or None,
                    "start_local": start.isoformat(),
                    "end_local": end.isoformat(),
                    "start_time_24h": start.strftime("%H:%M"),
                    "end_time_24h": end.strftime("%H:%M"),
                }
            )

    windows.sort(
        key=lambda row: (
            str(row.get("laser_device_name") or ""),
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


def _closing(
    *,
    reschedule: bool,
    booking_authorized: bool,
    ranges: bool,
    has_devices: bool = False,
) -> str:
    choice = "الجهاز والوقت" if has_devices else "الوقت"
    if reschedule:
        return f"قولي {choice} اللي يناسبك جوه الفترات دي عشان أغيّر الموعد." if ranges else f"اختار {choice} اللي يناسبك عشان أغيّره."
    if booking_authorized:
        return f"قولي {choice} اللي يناسبك جوه الفترات دي عشان أحجزه." if ranges else f"اختار {choice} اللي يناسبك عشان أحجزه."
    return f"لو حابب تحجز، قولي {choice} اللي يناسبك جوه الفترات دي." if ranges else f"لو حابب تحجز، قولي {choice} اللي يناسبك."


def _legacy_slot_reply(
    output: dict[str, Any],
    slots: list[object],
    *,
    reschedule: bool,
    booking_authorized: bool,
) -> str | None:
    grouped: dict[tuple[str, str], list[str]] = defaultdict(list)
    has_devices = False
    for raw_slot in slots:
        if not isinstance(raw_slot, dict):
            continue
        start = str(raw_slot.get("start_time_24h") or "").strip()
        if not start:
            continue
        doctor = str(raw_slot.get("doctor_name") or "الدكتور المتاح").strip() or "الدكتور المتاح"
        _device_key, device = _device_from_slot(raw_slot)
        has_devices = has_devices or bool(device)
        if start not in grouped[(doctor, device)]:
            grouped[(doctor, device)].append(start)

    lines: list[str] = []
    for (doctor, device), starts in list(grouped.items())[:8]:
        if starts:
            prefix = f"{device} مع {doctor}" if device else doctor
            lines.append(f"{prefix}: " + "، ".join(starts[:4]))
    if not lines:
        return None

    date_text = _display_date(output.get("date"))
    when = f" يوم {date_text}" if date_text else ""
    if output.get("requested_time_unavailable"):
        requested = _requested_time(output)
        requested_text = f" {requested}" if requested else ""
        intro = f"ميعاد{requested_text}{when} مش متاح. دي أقرب المواعيد المتاحة:"
    else:
        intro = f"دي المواعيد البديلة المتاحة{when}:" if reschedule else f"دي أقرب المواعيد المتاحة{when}:"
    return "\n".join([
        intro,
        *lines,
        _closing(
            reschedule=reschedule,
            booking_authorized=booking_authorized,
            ranges=False,
            has_devices=has_devices,
        ),
    ])


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
            return f"مفيش مواعيد متاحة في الوقت المطلوب{when}. ممكن أشوفلك وقت تاني في نفس اليوم لو تحب."
        return f"مفيش مواعيد متاحة{when}. ممكن أشوفلك يوم تاني لو تحب."

    grouped: dict[tuple[str, str], list[dict[str, Any]]] = defaultdict(list)
    has_devices = False
    for window in windows:
        if not isinstance(window, dict):
            continue
        doctor = str(window.get("doctor_name") or "الدكتور المتاح").strip() or "الدكتور المتاح"
        device = str(window.get("laser_device_name") or "").strip()
        has_devices = has_devices or bool(device)
        grouped[(doctor, device)].append(window)

    lines: list[str] = []
    for (doctor, device), group_windows in list(grouped.items())[:8]:
        ranges: list[str] = []
        for window in group_windows[:4]:
            start = _parse_dt(window.get("start_local"))
            end = _parse_dt(window.get("end_local"))
            if start is None or end is None:
                continue
            ranges.append(f"من {_clock_ar(start)} لـ{_clock_ar(end)}")
        if not ranges:
            continue
        label = f"{device} مع {doctor}" if device else f"مع {doctor}"
        lines.append(
            f"المتاح على {label} {'، و'.join(ranges)}."
            if device
            else f"المتاح {label} {'، و'.join(ranges)}."
        )

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

    return "\n".join([
        intro,
        *lines,
        _closing(
            reschedule=reschedule,
            booking_authorized=booking_authorized,
            ranges=True,
            has_devices=has_devices,
        ),
    ])


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
_DURATION_KEYS = {
    "duration",
    "duration_minutes",
    "service_duration_minutes",
}


def customer_visible_verified_data(value: Any) -> Any:
    """Remove internal location and scheduling-duration metadata before customer composition.

    Appointment date/time remains customer-visible. Service/session duration is an
    internal scheduling fact and must never be exposed in Tia's customer reply.
    """
    if isinstance(value, dict):
        return {
            key: customer_visible_verified_data(item)
            for key, item in value.items()
            if key not in _LOCATION_KEYS and key not in _DURATION_KEYS
        }
    if isinstance(value, list):
        return [customer_visible_verified_data(item) for item in value]
    return value
