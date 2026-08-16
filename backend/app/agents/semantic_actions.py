from __future__ import annotations

from datetime import datetime
from typing import Any


def select_slot_from_structured_selection(
    booking_output: dict[str, Any] | None,
    *,
    selection_index: int | None,
    selection_time: str | None,
) -> dict[str, Any] | None:
    if not booking_output or booking_output.get("ok") is not True:
        return None

    slots = booking_output.get("slots")
    if not isinstance(slots, list) or not slots:
        return None

    if selection_index is not None:
        index = selection_index - 1
        if 0 <= index < len(slots) and isinstance(slots[index], dict):
            return slots[index]

    if selection_time:
        normalized = selection_time.strip()
        if len(normalized) == 4 and normalized[1] == ":":
            normalized = "0" + normalized
        for slot in slots:
            if (
                isinstance(slot, dict)
                and slot.get("start_time_24h") == normalized
            ):
                return slot

    return None


def booking_tool_args(slot: dict[str, Any]) -> dict[str, str]:
    return {
        "branch_id": str(slot["branch_id"]),
        "service_id": str(slot["service_id"]),
        "doctor_id": str(slot["doctor_id"]),
        "start_at": str(slot["start_local"]),
        "customer_note": "",
    }


def format_booking_success(appointment: dict[str, Any]) -> str:
    date_text = ""
    time_text = ""
    try:
        start = datetime.fromisoformat(str(appointment.get("start_local")))
        end = datetime.fromisoformat(str(appointment.get("end_local")))
        date_text = start.strftime("%d/%m/%Y")
        time_text = f"{start.strftime('%H:%M')}–{end.strftime('%H:%M')}"
    except Exception:
        pass

    status = appointment.get("status")
    if status == "pending":
        opening = "تمام، الحجز اتسجل ومستني التأكيد"
    elif status == "confirmed":
        opening = "تمام، الحجز اتأكد"
    else:
        opening = "تمام، الحجز اتسجل"

    details = [
        appointment.get("service"),
        appointment.get("branch"),
        appointment.get("doctor"),
        " ".join(part for part in (date_text, time_text) if part) or None,
        appointment.get("price"),
    ]
    suffix = "، ".join(str(item) for item in details if item)
    return opening + (f": {suffix}." if suffix else ".")


def format_handoff_reply(category: str) -> str:
    if category == "medical":
        return (
            "الموضوع ده محتاج تقييم من الفريق الطبي، "
            "فحوّلت المحادثة لفريق العيادة للمراجعة."
        )
    if category == "complaint":
        return "حوّلت المحادثة لفريق العيادة عشان يتابعوا الشكوى معاك."
    if category == "payment":
        return "حوّلت الموضوع لفريق العيادة عشان يراجعوا مسألة الدفع معاك."
    return "حوّلت المحادثة لفريق العيادة عشان يكملوا معاك مباشرة."


def reschedule_tool_args(
    *,
    current_appointment_id: str,
    slot: dict[str, Any],
) -> dict[str, str]:
    return {
        "appointment_id": current_appointment_id,
        "start_at": str(slot["start_local"]),
        "branch_id": str(slot.get("branch_id") or ""),
        "doctor_id": str(slot.get("doctor_id") or ""),
        "reason": "Customer selected a replacement slot in the active workflow.",
    }
