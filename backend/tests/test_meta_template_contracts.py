from pathlib import Path

from app.core.automation_rules import DEFAULT_AUTOMATION_RULES
from app.services.automations import _appointment_template_body_parameters


def _rules():
    return {rule.key: rule for rule in DEFAULT_AUTOMATION_RULES}


def test_meta_product_template_names_match_approved_templates() -> None:
    rules = _rules()
    assert rules["appointment_reminder_6h"].template_name == "tia_reminder_01"
    assert rules["post_visit_followup"].template_name == "tia_post_visit_01"


def test_reminder_template_has_no_fixed_delay_date_or_branch_parameter() -> None:
    params = _appointment_template_body_parameters(
        "appointment_reminder_6h",
        {
            "patient_name": "سارة",
            "service_name": "إزالة الشعر",
            "date": "08/09/2026",
            "time": "15:00",
            "branch_name": "Main",
        },
    )
    assert params == ["سارة", "إزالة الشعر", "15:00"]


def test_post_visit_template_keeps_name_service_and_session_date() -> None:
    params = _appointment_template_body_parameters(
        "post_visit_followup",
        {
            "patient_name": "سارة",
            "service_name": "إزالة الشعر",
            "date": "08/09/2026",
            "time": "15:00",
            "branch_name": "Main",
        },
    )
    assert params == ["سارة", "إزالة الشعر", "08/09/2026"]


def test_known_legacy_default_names_are_migrated_without_overwriting_custom_templates() -> None:
    source = (Path(__file__).resolve().parents[1] / "app/services/automations.py").read_text(encoding="utf-8")
    assert "LEGACY_DEFAULT_TEMPLATE_NAMES" in source
    assert "tia_appointment_reminder_ar" in source
    assert "tia_reminder_6h_01" in source
    assert "tia_post_visit_followup_ar" in source
    assert "if row.template_name in legacy_names" in source
