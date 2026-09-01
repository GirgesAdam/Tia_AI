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
            if isinstance(slot, dict) and slot.get("start_time_24h") == normalized:
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
        return "الموضوع ده محتاج تقييم من الفريق الطبي، فحوّلت المحادثة لفريق العيادة للمراجعة."
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


def _display_date(value: object) -> str:
    if not value:
        return ""
    try:
        return datetime.fromisoformat(str(value)).strftime("%d/%m/%Y")
    except Exception:
        try:
            return datetime.fromisoformat(f"{value}T00:00:00").strftime("%d/%m/%Y")
        except Exception:
            return str(value)


def _numbered_names(items: object, *keys: str, limit: int = 5) -> list[str]:
    if not isinstance(items, list):
        return []
    values: list[str] = []
    for item in items[:limit]:
        if not isinstance(item, dict):
            continue
        value = next((item.get(key) for key in keys if item.get(key)), None)
        if value:
            values.append(str(value))
    return [f"{index}) {value}" for index, value in enumerate(values, start=1)]


def _format_slot_choices(output: dict[str, Any], *, reschedule: bool) -> str | None:
    slots = output.get("slots")
    if not isinstance(slots, list):
        return None

    date_text = _display_date(output.get("date"))
    window = output.get("requested_time_window")
    has_window = isinstance(window, dict) and any(
        window.get(key) for key in ("not_before_time", "not_after_time")
    )

    if not slots:
        when = f" يوم {date_text}" if date_text else ""
        if has_window:
            return (
                f"مفيش مواعيد متاحة في الوقت المطلوب{when}. "
                "ممكن أشوفلك وقت تاني في نفس اليوم لو تحب."
            )
        return f"مفيش مواعيد متاحة{when}. ممكن أشوفلك يوم تاني لو تحب."

    lines: list[str] = []
    for index, slot in enumerate(slots[:4], start=1):
        if not isinstance(slot, dict):
            continue
        start_text = str(slot.get("start_time_24h") or "").strip()
        end_text = str(slot.get("end_time_24h") or "").strip()
        time_text = f"{start_text}–{end_text}" if start_text and end_text else start_text
        doctor = str(slot.get("doctor_name") or "").strip()
        branch = str(slot.get("branch_name") or "").strip()
        details = " - ".join(part for part in (time_text, doctor, branch) if part)
        if details:
            lines.append(f"{index}) {details}")

    if not lines:
        return None

    if output.get("requested_time_unavailable"):
        requested_time = str(output.get("requested_start_time") or "").strip()
        # Compatibility with old persisted/tool results that represented one exact
        # start as equal lower/upper bounds. New turns use requested_start_time.
        if not requested_time and isinstance(window, dict):
            lower = str(window.get("not_before_time") or "").strip()
            upper = str(window.get("not_after_time") or "").strip()
            if lower and lower == upper:
                requested_time = lower
        requested = f" {requested_time}" if requested_time else ""
        when = f" يوم {date_text}" if date_text else ""
        opening = f"ميعاد{requested}{when} مش متاح. دي أقرب المواعيد المتاحة"
    else:
        opening = "دي المواعيد البديلة المتاحة" if reschedule else "دي أقرب المواعيد المتاحة"
        if date_text:
            opening += f" يوم {date_text}"

    action = "اختار الميعاد اللي يناسبك عشان أغيّره." if reschedule else "اختار الميعاد اللي يناسبك عشان أحجزه."
    return f"{opening}:\n" + "\n".join(lines) + f"\n{action}"


def format_verified_tool_fallback(tool_name: str, output: dict[str, Any]) -> str | None:
    """Build a customer-safe reply only from verified composite tool output.

    This is a provider-failure/empty-finalizer safety path, not semantic routing.
    It never inspects customer wording and never authorizes a write.
    """
    if tool_name == "create_follow_up_task":
        if output.get("ok") is not True:
            return "معلش، مقدرتش أسجل المتابعة بالوقت ده. قولي وقت واضح تاني في المستقبل."
        due_text = _display_date(output.get("due_at"))
        return (
            f"تمام، سجلت متابعة للفريق يوم {due_text}."
            if due_text
            else "تمام، سجلت متابعة للفريق."
        )

    if tool_name not in {"get_booking_options", "get_reschedule_options"}:
        return None

    if output.get("ok") is not True:
        reason = str(output.get("reason") or "")
        messages = {
            "service_not_found": "ملقتش خدمة مطابقة للطلب في بيانات العيادة. قولي اسم الخدمة بشكل تاني.",
            "branch_not_found": "ملقتش الفرع المطلوب ضمن الفروع المتاحة. قولي الفرع اللي تقصده.",
            "doctor_not_found": "ملقتش الدكتور المطلوب متاح للخدمة والفرع دول. ممكن أقولك الدكاترة المتاحين.",
            "appointment_not_found": "ملقتش حجز قادم مطابق أقدر أغيّر ميعاده.",
            "no_active_branch": "مفيش فرع متاح للحجز حاليًا في بيانات العيادة.",
        }
        return messages.get(reason) or "معلش، مقدرتش أكمل البحث بالمعلومات الحالية. قولي التفاصيل المطلوبة تاني."

    if output.get("needs_service_choice"):
        choices = _numbered_names(output.get("services"), "service_name", "name")
        if choices:
            return "لقيت أكتر من خدمة مطابقة:\n" + "\n".join(choices) + "\nاختار الخدمة اللي تقصدها."

    if output.get("needs_branch_choice"):
        choices = _numbered_names(output.get("branches"), "branch_name", "name")
        if choices:
            return "لقيت أكتر من فرع مناسب:\n" + "\n".join(choices) + "\nاختار الفرع اللي يناسبك."

    if output.get("needs_doctor_choice"):
        choices = _numbered_names(output.get("doctors"), "doctor_name", "name")
        if choices:
            return "لقيت أكتر من دكتور مطابق:\n" + "\n".join(choices) + "\nاختار الدكتور اللي تقصده."

    if output.get("needs_appointment_choice"):
        appointments = output.get("appointments")
        if isinstance(appointments, list):
            lines: list[str] = []
            for index, appointment in enumerate(appointments[:5], start=1):
                if not isinstance(appointment, dict):
                    continue
                service = str(appointment.get("service") or "").strip()
                date_text = _display_date(appointment.get("start_local"))
                details = " - ".join(part for part in (service, date_text) if part)
                if details:
                    lines.append(f"{index}) {details}")
            if lines:
                return "لقيت أكتر من حجز قادم:\n" + "\n".join(lines) + "\nاختار الحجز اللي عايز تغيّره."

    return _format_slot_choices(
        output,
        reschedule=tool_name == "get_reschedule_options",
    )
