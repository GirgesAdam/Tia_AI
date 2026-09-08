from types import SimpleNamespace
from uuid import UUID

from app.services.automations import _ai_followup_template_candidates, _select_ai_followup_template

TASK = UUID("38d2d461-73ce-4fab-87e6-c7cf25fefe56")
PATIENT = UUID("9cac0792-37aa-4e4c-864f-c29ebc51d96e")

def conn(config: dict):
    return SimpleNamespace(config_json=config)

def test_followup_pool_legacy_compatibility():
    row = conn({"ai_followup_template": {"name": "legacy_ar", "language_code": "ar"}})
    assert _ai_followup_template_candidates(row) == [("legacy_ar", "ar")]

def test_followup_pool_deterministic_and_deduplicated():
    row = conn({"ai_followup_templates": [{"name": "one", "language_code": "ar"}, {"name": "two", "language_code": "ar"}, {"name": "one", "language_code": "ar"}]})
    assert _ai_followup_template_candidates(row) == [("one", "ar"), ("two", "ar")]
    assert _select_ai_followup_template(row, task_id=TASK, patient_id=PATIENT) == _select_ai_followup_template(row, task_id=TASK, patient_id=PATIENT)

def test_followup_pool_avoids_immediate_repeat():
    row = conn({"ai_followup_templates": [{"name": "one", "language_code": "ar"}, {"name": "two", "language_code": "ar"}]})
    first = _select_ai_followup_template(row, task_id=TASK, patient_id=PATIENT)
    assert first is not None
    second = _select_ai_followup_template(row, task_id=TASK, patient_id=PATIENT, previous_template=first[0])
    assert second is not None and second[0] != first[0]
