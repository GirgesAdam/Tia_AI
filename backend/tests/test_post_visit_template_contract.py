from pathlib import Path


def _root() -> Path:
    return Path(__file__).resolve().parents[2]


def test_post_visit_followup_copy_does_not_mention_branch() -> None:
    source = (_root() / "backend/app/services/automations.py").read_text(encoding="utf-8")
    block = source.split('if rule_key == "post_visit_followup":', 1)[1].split('if rule_key == "no_show_followup":', 1)[0]
    assert "branch_name" not in block
    assert "كل حاجة تمام؟" in block


def test_post_visit_template_has_exactly_three_parameters() -> None:
    source = (_root() / "backend/app/services/automations.py").read_text(encoding="utf-8")
    helper = source.split("def _appointment_template_body_parameters", 1)[1].split("def _resolve_external_route", 1)[0]
    assert 'if rule_key == "post_visit_followup":' in helper
    assert 'return [patient_name, service_name, date]' in helper
