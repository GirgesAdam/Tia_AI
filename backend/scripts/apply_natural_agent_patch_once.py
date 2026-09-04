from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def _read(relative: str) -> str:
    return (ROOT / relative).read_text(encoding="utf-8")


def _write(relative: str, value: str) -> None:
    (ROOT / relative).write_text(value, encoding="utf-8")


def _replace_once(text: str, old: str, new: str, *, label: str) -> str:
    count = text.count(old)
    if count != 1:
        raise RuntimeError(f"{label}: expected exactly one anchor, found {count}")
    return text.replace(old, new, 1)


def _replace_top_level_function(text: str, name: str, replacement: str) -> str:
    lines = text.splitlines(keepends=True)
    start = next(
        (index for index, line in enumerate(lines) if line.startswith(f"def {name}(") or line.startswith(f"def {name}:")),
        None,
    )
    if start is None:
        raise RuntimeError(f"function not found: {name}")
    end = len(lines)
    for index in range(start + 1, len(lines)):
        line = lines[index]
        if line.startswith("def ") or line.startswith("class "):
            end = index
            break
    return "".join(lines[:start]) + replacement.rstrip() + "\n\n" + "".join(lines[end:]).lstrip("\n")


def patch_semantic_actions() -> None:
    path = "app/agents/semantic_actions.py"
    text = _read(path)
    text = _replace_once(
        text,
        "from typing import Any\n",
        "from typing import Any\n\nfrom app.agents.availability_presentation import format_availability_windows_reply\n",
        label="semantic actions import",
    )
    text = _replace_top_level_function(
        text,
        "select_slot_from_structured_selection",
        '''def select_slot_from_structured_selection(
    booking_output: dict[str, Any] | None,
    *,
    selection_index: int | None,
    selection_time: str | None,
    doctor_id: str | None = None,
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
        matches = [
            slot
            for slot in slots
            if isinstance(slot, dict)
            and slot.get("start_time_24h") == normalized
            and (doctor_id is None or str(slot.get("doctor_id") or "") == str(doctor_id))
        ]
        if len(matches) == 1:
            return matches[0]

    return None''',
    )
    text = _replace_top_level_function(
        text,
        "format_booking_success",
        '''def format_booking_success(appointment: dict[str, Any]) -> str:
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
        appointment.get("doctor"),
        " ".join(part for part in (date_text, time_text) if part) or None,
        appointment.get("price"),
    ]
    suffix = "، ".join(str(item) for item in details if item)
    return opening + (f": {suffix}." if suffix else ".")''',
    )
    text = _replace_top_level_function(
        text,
        "_format_slot_choices",
        '''def _format_slot_choices(output: dict[str, Any], *, reschedule: bool) -> str | None:
    return format_availability_windows_reply(
        output,
        reschedule=reschedule,
        booking_authorized=not reschedule,
    )''',
    )
    text = text.replace(
        '"branch_not_found": "ملقتش الفرع المطلوب ضمن الفروع المتاحة. قولي الفرع اللي تقصده.",',
        '"branch_not_found": "مقدرتش أكمل الحجز بالمعلومات الحالية. قولي الخدمة أو الدكتور اللي تقصده.",',
    )
    text = text.replace(
        '"no_active_branch": "مفيش فرع متاح للحجز حاليًا في بيانات العيادة.",',
        '"no_active_branch": "الحجز مش متاح حاليًا. ممكن أساعدك في حاجة تانية.",',
    )
    old_branch_choice = '''    if output.get("needs_branch_choice"):
        choices = _numbered_names(output.get("branches"), "branch_name", "name")
        if choices:
            return "لقيت أكتر من فرع مناسب:\\n" + "\\n".join(choices) + "\\nاختار الفرع اللي يناسبك."

'''
    if old_branch_choice in text:
        text = text.replace(
            old_branch_choice,
            '''    if output.get("needs_branch_choice"):
        return "معلش، مقدرتش أكمل الحجز دلوقتي. جرّب تاني بعد لحظة."

''',
            1,
        )
    _write(path, text)


def patch_clinic_tools() -> None:
    path = "app/agents/tools/clinic_tools.py"
    text = _read(path)
    text = _replace_once(
        text,
        "from app.integrations.clinic.registry import get_clinic_adapter\n",
        "from app.agents.availability_presentation import availability_windows_from_slots\nfrom app.integrations.clinic.registry import get_clinic_adapter\n",
        label="clinic tools import",
    )
    text = _replace_top_level_function(
        text,
        "_availability_payload",
        '''def _availability_payload(
    ctx: AgentToolContext,
    *,
    branch_id: str | None = None,
    service_id: str | None = None,
    branch: Branch | None = None,
    service: Service | None = None,
    booking_date: date,
    doctor_id: str | UUID | None,
    requested_start: time | None,
    lower_bound: time | None,
    upper_bound: time | None,
    exclude_appointment_id: str | UUID | None = None,
) -> dict:
    resolved_branch_id = branch_id or (str(branch.id) if branch is not None else None)
    resolved_service_id = service_id or (str(service.id) if service is not None else None)
    if resolved_branch_id is None:
        raise TypeError("_availability_payload() requires branch_id or branch")
    if resolved_service_id is None:
        raise TypeError("_availability_payload() requires service_id or service")

    availability = _adapter_availability(
        ctx,
        branch_id=str(resolved_branch_id),
        service_id=str(resolved_service_id),
        booking_date=booking_date,
        doctor_id=str(doctor_id) if doctor_id is not None else None,
        exclude_appointment_id=(
            str(exclude_appointment_id) if exclude_appointment_id is not None else None
        ),
    )
    timezone_name = availability.timezone
    slots = list(availability.slots)
    tz = ZoneInfo(timezone_name)
    window_slots = _filter_slots_by_local_window(
        slots,
        tz=tz,
        lower_bound=lower_bound,
        upper_bound=upper_bound,
    )

    requested_time_unavailable = False
    matching_slot_count = len(window_slots)
    presented_slots = window_slots

    if requested_start is not None:
        exact_slots = [
            (slot, local_start)
            for slot, local_start in window_slots
            if local_start.timetz().replace(tzinfo=None) == requested_start
        ]
        matching_slot_count = len(exact_slots)
        if exact_slots:
            presented_slots = exact_slots
        else:
            requested_time_unavailable = True
            target_minutes = requested_start.hour * 60 + requested_start.minute

            def distance_from_requested(item) -> tuple[int, object]:
                _, local_start = item
                local_minutes = local_start.hour * 60 + local_start.minute
                return abs(local_minutes - target_minutes), local_start

            if lower_bound is not None or upper_bound is not None:
                nearby_pool = window_slots
            else:
                nearby_pool = [(slot, slot.start_at.astimezone(tz)) for slot in slots]
            presented_slots = sorted(nearby_pool, key=distance_from_requested)[:12]

    result_slots: list[dict[str, object]] = []
    for slot, local_start in presented_slots:
        local_end = slot.end_at.astimezone(tz)
        result_slots.append(
            {
                "branch_id": slot.branch_id,
                "branch_name": slot.branch_name,
                "doctor_id": slot.doctor_id,
                "doctor_name": slot.doctor_name or "الدكتور المتاح",
                "service_id": slot.service_id,
                "service_name": slot.service_name,
                "start_local": local_start.isoformat(),
                "end_local": local_end.isoformat(),
                "start_time_24h": local_start.strftime("%H:%M"),
                "end_time_24h": local_end.strftime("%H:%M"),
                "duration_minutes": slot.duration_minutes,
                "timezone": timezone_name,
                "price": _money(slot.price_minor, slot.currency),
            }
        )

    return {
        "date": booking_date.isoformat(),
        "timezone": timezone_name,
        "branch": {
            "branch_id": availability.branch_id,
            "branch_name": availability.branch_name,
        },
        "service": {
            "service_id": availability.service_id,
            "service_name": availability.service_name,
            "duration_minutes": availability.service_duration_minutes,
            "price": (
                _money(availability.service_price_minor, availability.service_currency)
                if availability.service_price_minor is not None
                and availability.service_currency
                else None
            ),
        },
        "requested_start_time": (
            requested_start.strftime("%H:%M") if requested_start else None
        ),
        # Keep all verified starts internally so a customer can choose any clock
        # time from a displayed availability window. These rows are not rendered
        # directly to the customer.
        "slots": result_slots,
        "availability_windows": availability_windows_from_slots(result_slots),
        "matching_slot_count": matching_slot_count,
        "requested_time_unavailable": requested_time_unavailable,
        "more_slots_available": False,
    }''',
    )
    _write(path, text)


def patch_agent_chat() -> None:
    path = "app/services/agent_chat.py"
    text = _read(path)
    text = _replace_once(
        text,
        "from app.agents.capability_policy import (\n",
        "from app.agents.availability_presentation import format_availability_windows_reply\nfrom app.agents.capability_policy import (\n",
        label="agent chat availability import",
    )
    text = _replace_top_level_function(
        text,
        "_verified_booking_slots_reply",
        '''def _verified_booking_slots_reply(
    payload: dict[str, object],
    *,
    booking_authorized: bool,
) -> str | None:
    """Present adapter-verified availability as natural free-time windows."""
    if payload.get("ok") is False:
        return None
    if any(
        bool(payload.get(key))
        for key in (
            "needs_service_choice",
            "needs_branch_choice",
            "needs_doctor_choice",
            "needs_appointment_choice",
        )
    ):
        return None
    return format_availability_windows_reply(
        payload,
        booking_authorized=booking_authorized,
    )''',
    )
    old_selection = '''    slot = select_slot_from_structured_selection(
        flow.option_snapshot,
        selection_index=turn.selection_index,
        selection_time=turn.selection_time,
    )
    if slot is None:
        return None
'''
    new_selection = '''    selected_doctor_id = getattr(turn.entity_hints, "doctor_id", None) or (
        (flow.entity_state or {}).get("doctor_id")
    )
    slot = select_slot_from_structured_selection(
        flow.option_snapshot,
        selection_index=turn.selection_index,
        selection_time=turn.selection_time,
        doctor_id=str(selected_doctor_id) if selected_doctor_id else None,
    )
    if slot is None and turn.selection_time:
        normalized_time = str(turn.selection_time).strip()
        if len(normalized_time) == 4 and normalized_time[1] == ":":
            normalized_time = "0" + normalized_time
        matching_doctors = []
        seen_doctors: set[str] = set()
        snapshot_slots = (flow.option_snapshot or {}).get("slots")
        if isinstance(snapshot_slots, list):
            for candidate in snapshot_slots:
                if not isinstance(candidate, dict):
                    continue
                if str(candidate.get("start_time_24h") or "") != normalized_time:
                    continue
                doctor_name = str(candidate.get("doctor_name") or "الدكتور المتاح").strip()
                doctor_key = str(candidate.get("doctor_id") or doctor_name)
                if doctor_key in seen_doctors:
                    continue
                seen_doctors.add(doctor_key)
                matching_doctors.append(doctor_name)
        if len(matching_doctors) > 1:
            names = "، ".join(matching_doctors[:4])
            return (
                f"الساعة {normalized_time} متاحة مع أكتر من دكتور: {names}. "
                "قولي تفضّل مين عشان أحجز من غير ما أختار مكانك.",
                "flow-interpreter:deterministic-slot-ambiguity",
            )
    if slot is None:
        return None
'''
    text = _replace_once(
        text,
        old_selection,
        new_selection,
        label="structured flow selection",
    )
    _write(path, text)


def patch_customer_prompt() -> None:
    path = "app/agents/prompts/customer_service.py"
    text = _read(path)
    text = _replace_once(
        text,
        "- ما تخمنش سعر، ميعاد، دكتور، فرع، خدمة، رصيد باكدج، دفع، أو حالة حجز.\n",
        "- ما تخمنش سعر، ميعاد، دكتور، خدمة، رصيد باكدج، دفع، أو حالة حجز.\n"
        "- تجربة العميل الحالية لمكان واحد فقط. الفروع/مواقع التخزين تفاصيل داخلية: ما تذكرش اسم فرع، ما تسألش عن فرع، وما تعرضش اختيار فرع للعميل.\n"
        "- لما تعرض availability، لخّص الـslots المتصلة كفترات طبيعية لكل دكتور بدل سرد مواعيد كل ربع ساعة.\n",
        label="customer prompt single location",
    )
    _write(path, text)


def patch_grounded_response() -> None:
    path = "app/agents/grounded_response.py"
    text = _read(path)
    text = _replace_once(
        text,
        "from app.agents.llm_runtime import LLMProviderError, invoke_model, invoke_with_model_chain\n",
        "from app.agents.availability_presentation import customer_visible_verified_data\nfrom app.agents.llm_runtime import LLMProviderError, invoke_model, invoke_with_model_chain\n",
        label="grounded response import",
    )
    text = _replace_once(
        text,
        '            "- Never print internal UUIDs or implementation metadata.\\n"\n',
        '            "- Never print internal UUIDs or implementation metadata.\\n"\n'
        '            "- The customer experience is single-location. Never mention or ask about branches; "\n'
        '            "storage-level branch data is internal only.\\n"\n'
        '            "- When availability_windows are provided, summarize those natural continuous windows "\n'
        '            "per doctor instead of listing dense quarter-hour slot starts.\\n"\n',
        label="grounded response UX rules",
    )
    text = _replace_once(
        text,
        '        "verified_data": verified_data,\n',
        '        "verified_data": customer_visible_verified_data(verified_data),\n',
        label="grounded response sanitize",
    )
    _write(path, text)


def patch_fallback_agent() -> None:
    path = "app/agents/tia_customer_agent.py"
    text = _read(path)
    text = _replace_once(
        text,
        "from app.agents.llm_runtime import LLMProviderError, invoke_model, invoke_with_fallback\n",
        "from app.agents.availability_presentation import customer_visible_verified_data\nfrom app.agents.llm_runtime import LLMProviderError, invoke_model, invoke_with_fallback\n",
        label="fallback agent import",
    )
    text = _replace_once(
        text,
        '                "result": payload if payload is not None else str(message.content),\n',
        '                "result": customer_visible_verified_data(payload) if payload is not None else str(message.content),\n',
        label="fallback finalizer sanitize",
    )
    _write(path, text)


def patch_turn_interpreter() -> None:
    path = "app/agents/turn_interpreter.py"
    text = _read(path)
    text = _replace_top_level_function(
        text,
        "_option_summary",
        '''def _option_summary(flow: ConversationFlowState | None) -> dict[str, object]:
    if flow is None or not isinstance(flow.option_snapshot, dict):
        return {}

    summary: dict[str, object] = {}
    windows = flow.option_snapshot.get("availability_windows")
    if isinstance(windows, list) and windows:
        summary["availability_windows"] = [
            {
                "doctor_id": window.get("doctor_id"),
                "doctor_name": window.get("doctor_name"),
                "start_time_24h": window.get("start_time_24h"),
                "end_time_24h": window.get("end_time_24h"),
            }
            for window in windows[:12]
            if isinstance(window, dict)
        ]
    else:
        slots = flow.option_snapshot.get("slots")
        if isinstance(slots, list):
            summary["slots"] = [
                {
                    "index": index + 1,
                    "start_time_24h": slot.get("start_time_24h"),
                    "end_time_24h": slot.get("end_time_24h"),
                    "doctor_name": slot.get("doctor_name"),
                }
                for index, slot in enumerate(slots[:8])
                if isinstance(slot, dict)
            ]

    choice_specs = (
        ("services", ("service_name", "name")),
        ("doctors", ("doctor_name", "name")),
    )
    for collection_name, name_keys in choice_specs:
        choices = flow.option_snapshot.get(collection_name)
        if not isinstance(choices, list):
            continue
        summarized: list[dict[str, object]] = []
        for index, choice in enumerate(choices[:8]):
            if not isinstance(choice, dict):
                continue
            display_name = next(
                (choice.get(key) for key in name_keys if choice.get(key)),
                None,
            )
            canonical_id = choice.get("service_id") or choice.get("doctor_id") or choice.get("id")
            summarized.append(
                {
                    "index": index + 1,
                    "id": canonical_id,
                    "name": display_name,
                }
            )
        if summarized:
            summary[collection_name] = summarized
    return summary''',
    )
    text = _replace_once(
        text,
        '        "For a presented slot selection, set selection_index to the displayed option index.\\n\\n"\n',
        '        "For a numbered option selection, set selection_index to the displayed option index. "\n'
        '        "When availability was shown as a continuous time window and the customer chooses a clock "\n'
        '        "time inside it, set selection_time to HH:MM instead. Never invent a doctor when the same "\n'
        '        "clock time is available with multiple doctors.\\n\\n"\n',
        label="turn selection prompt",
    )
    _write(path, text)


def main() -> None:
    patch_semantic_actions()
    patch_clinic_tools()
    patch_agent_chat()
    patch_customer_prompt()
    patch_grounded_response()
    patch_fallback_agent()
    patch_turn_interpreter()
    print("Natural agent patch applied.")


if __name__ == "__main__":
    main()
