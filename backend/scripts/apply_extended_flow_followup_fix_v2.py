from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]


def replace_once(path: str, old: str, new: str) -> None:
    target = ROOT / path
    text = target.read_text(encoding="utf-8")
    count = text.count(old)
    if count != 1:
        raise RuntimeError(f"Expected one anchor in {path}, found {count}: {old[:160]!r}")
    target.write_text(text.replace(old, new, 1), encoding="utf-8")


def main() -> int:
    replace_once(
        "backend/app/services/agent_chat.py",
        '''    for field_name in clear_fields:\n        merged.pop(field_name, None)\n    if "requested_date" in clear_fields:\n''',
        '''    for field_name in clear_fields:\n        merged.pop(field_name, None)\n    if clear_fields.intersection({"service_query", "service_id", "service_candidate_ids"}):\n        merged.pop("service", None)\n    if clear_fields.intersection({"doctor_query", "doctor_id", "doctor_candidate_ids"}):\n        merged.pop("doctor", None)\n    if "requested_date" in clear_fields:\n''',
    )

    replace_once(
        "backend/app/services/agent_chat.py",
        '''        if selected_value:\n            merged.pop(candidates_key, None)\n        elif candidates_value:\n            merged.pop(selected_key, None)\n    return merged\n''',
        '''        if selected_value:\n            merged.pop(candidates_key, None)\n        elif candidates_value:\n            merged.pop(selected_key, None)\n            if entity_name in {"service", "doctor"}:\n                merged.pop(entity_name, None)\n    return merged\n''',
    )

    replace_once(
        "backend/app/services/agent_chat.py",
        '''    appointment_id = text_value("appointment_id")\n    requested_date = text_value("requested_date") or text_value("date")\n''',
        '''    appointment_id = text_value("appointment_id")\n    if not appointment_id and flow is not None and flow.flow_type == "appointment_reschedule":\n        appointment_reference = text_value("appointment_reference")\n        if appointment_reference:\n            try:\n                referenced_start = datetime.fromisoformat(\n                    appointment_reference.replace("Z", "+00:00")\n                )\n            except ValueError:\n                referenced_start = None\n            if referenced_start is not None:\n                timezone_name = tool_context.workspace.timezone or "Africa/Cairo"\n                try:\n                    clinic_tz = ZoneInfo(timezone_name)\n                except ZoneInfoNotFoundError:\n                    clinic_tz = ZoneInfo("Africa/Cairo")\n                if referenced_start.tzinfo is not None:\n                    referenced_start = referenced_start.astimezone(clinic_tz)\n                reference_key = referenced_start.strftime("%Y-%m-%d %H:%M")\n                candidates = list(\n                    tool_context.db.scalars(\n                        select(Appointment).where(\n                            Appointment.workspace_id == tool_context.workspace.id,\n                            Appointment.patient_id == tool_context.patient.id,\n                            Appointment.status.notin_(("cancelled", "no_show")),\n                        )\n                    )\n                )\n                matches = [\n                    row\n                    for row in candidates\n                    if row.start_at.astimezone(clinic_tz).strftime("%Y-%m-%d %H:%M")\n                    == reference_key\n                ]\n                if len(matches) == 1:\n                    appointment_id = str(matches[0].id)\n    requested_date = text_value("requested_date") or text_value("date")\n''',
    )

    print("Applied minimal stale-entity cleanup and exact appointment reference resolution.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
