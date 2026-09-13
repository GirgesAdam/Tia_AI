from __future__ import annotations

from pathlib import Path


def replace_exact(path: Path, old: str, new: str) -> None:
    text = path.read_text(encoding="utf-8")
    count = text.count(old)
    if count != 1:
        raise SystemExit(f"{path}: expected one edge-fix target, found {count}")
    path.write_text(text.replace(old, new), encoding="utf-8")


grouped = Path("backend/app/services/agent_v2/grouped_visit_operations.py")
replace_exact(
    grouped,
    "    moved: list[tuple[Appointment, Appointment]] = []\n"
    "    with db.begin_nested():\n"
    "        for member in members:\n",
    "    moved: list[tuple[Appointment, Appointment]] = []\n"
    "    excluded_appointment_ids = set(appointment_ids)\n"
    "    with db.begin_nested():\n"
    "        for member in members:\n",
)
replace_exact(
    grouped,
    "                exclude_appointment_ids=appointment_ids,\n"
    "            )\n"
    "            moved.append((replacement, previous))\n",
    "                exclude_appointment_ids=tuple(excluded_appointment_ids),\n"
    "            )\n"
    "            excluded_appointment_ids.add(replacement.id)\n"
    "            moved.append((replacement, previous))\n",
)

tests = Path("backend/tests/test_v2_grouped_visits.py")
text = tests.read_text(encoding="utf-8")
marker = "def test_group_reschedule_excludes_prior_replacements"
if marker in text:
    raise SystemExit("grouped reschedule replacement regression test already exists")
text += '''\n\n\ndef test_group_reschedule_excludes_prior_replacements(monkeypatch):\n    from app.services.agent_v2 import grouped_visit_operations as grouped_ops\n\n    replacement_a = SimpleNamespace(id=uuid4())\n    replacement_b = SimpleNamespace(id=uuid4())\n    members = [SimpleNamespace(id=APPT_A), SimpleNamespace(id=APPT_B)]\n    exclusion_calls = []\n\n    monkeypatch.setattr(\n        grouped_ops,\n        "_visit_members",\n        lambda *_args, **_kwargs: members,\n    )\n\n    def fake_reschedule(*_args, appointment_id, exclude_appointment_ids, **_kwargs):\n        exclusion_calls.append(set(exclude_appointment_ids))\n        replacement = replacement_a if appointment_id == APPT_A else replacement_b\n        return replacement, SimpleNamespace(id=appointment_id)\n\n    monkeypatch.setattr(grouped_ops, "reschedule_appointment_operation", fake_reschedule)\n\n    class NestedScope:\n        def __enter__(self):\n            return self\n\n        def __exit__(self, _exc_type, _exc, _tb):\n            return False\n\n    components = [\n        {\n            "appointment_id": str(APPT_A),\n            "branch_id": str(BRANCH_ID),\n            "doctor_id": str(DOCTOR_ID),\n            "service_id": str(SERVICE_A),\n            "start_at": datetime(2026, 9, 15, 8, 0, tzinfo=UTC).isoformat(),\n        },\n        {\n            "appointment_id": str(APPT_B),\n            "branch_id": str(BRANCH_ID),\n            "doctor_id": str(DOCTOR_ID),\n            "service_id": str(SERVICE_B),\n            "start_at": datetime(2026, 9, 15, 8, 30, tzinfo=UTC).isoformat(),\n        },\n    ]\n    moved = grouped_ops.reschedule_visit_group_operation(\n        SimpleNamespace(begin_nested=lambda: NestedScope()),\n        workspace=SimpleNamespace(id=uuid4()),\n        patient_id=PATIENT_ID,\n        visit_group_id=GROUP_ID,\n        appointment_ids=(APPT_A, APPT_B),\n        components=components,\n    )\n\n    assert len(moved) == 2\n    assert exclusion_calls[0] == {APPT_A, APPT_B}\n    assert exclusion_calls[1] == {APPT_A, APPT_B, replacement_a.id}\n'''
tests.write_text(text, encoding="utf-8")
