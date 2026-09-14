from __future__ import annotations

import re
from pathlib import Path
from types import SimpleNamespace
from uuid import UUID

from app.core.meta_whatsapp_templates import (
    STANDARD_TEMPLATE_BY_RULE_KEY,
    STANDARD_TEMPLATES_BY_RULE_KEY,
    STANDARD_WHATSAPP_TEMPLATES,
    approved_standard_templates,
    approved_template_refs_for_rule,
)
from app.services.automations import (
    _select_ai_followup_template,
    _select_rule_template,
)


EXPECTED_PARAMETER_COUNT = {
    "appointment_reminder_6h": 3,
    "post_visit_followup": 3,
    "cancellation_recovery": 4,
    "lead_not_booked_followup": 5,
}


def _root() -> Path:
    return Path(__file__).resolve().parents[2]


def test_standard_catalog_has_three_friendly_variants_per_automation() -> None:
    assert len(STANDARD_WHATSAPP_TEMPLATES) == 12
    assert set(STANDARD_TEMPLATES_BY_RULE_KEY) == set(EXPECTED_PARAMETER_COUNT)
    assert len({template.name for template in STANDARD_WHATSAPP_TEMPLATES}) == 12

    for rule_key, parameter_count in EXPECTED_PARAMETER_COUNT.items():
        templates = STANDARD_TEMPLATES_BY_RULE_KEY[rule_key]
        assert len(templates) == 3
        assert STANDARD_TEMPLATE_BY_RULE_KEY[rule_key] == templates[0]
        expected_placeholders = [str(index) for index in range(1, parameter_count + 1)]
        for template in templates:
            assert re.findall(r"\{\{(\d+)\}\}", template.body_text) == expected_placeholders
            assert len(template.example_body_parameters) == parameter_count


def test_rotation_pool_contains_only_meta_approved_variants() -> None:
    statuses = {
        "tia_reminder_01": "pending",
        "tia_reminder_02": "approved",
        "tia_reminder_03": "rejected",
    }
    approved = approved_standard_templates("appointment_reminder_6h", statuses)
    refs = approved_template_refs_for_rule("appointment_reminder_6h", statuses)

    assert [template.name for template in approved] == ["tia_reminder_02"]
    assert refs == [{"name": "tia_reminder_02", "language_code": "ar_EG"}]


def test_appointment_rotation_is_automatic_and_stable_for_retries() -> None:
    refs = [
        {"name": template.name, "language_code": template.language}
        for template in STANDARD_TEMPLATES_BY_RULE_KEY["appointment_reminder_6h"]
    ]
    rule = SimpleNamespace(
        key="appointment_reminder_6h",
        id=UUID("aaaaaaaa-1111-2222-3333-bbbbbbbbbbbb"),
        template_name="tia_reminder_01",
        template_language="ar_EG",
        config_json={"template_variants": refs, "template_rotation": "automatic"},
    )
    appointment_id = UUID("11111111-2222-3333-4444-555555555555")

    first = _select_rule_template(rule, appointment_id)
    second = _select_rule_template(rule, appointment_id)

    assert first == second
    assert first[0] in {item["name"] for item in refs}


def test_lead_rotation_is_automatic_and_stable_for_retries() -> None:
    refs = [
        {"name": template.name, "language_code": template.language}
        for template in STANDARD_TEMPLATES_BY_RULE_KEY["lead_not_booked_followup"]
    ]
    connection = SimpleNamespace(
        id=UUID("99999999-aaaa-bbbb-cccc-000000000000"),
        config_json={"ai_followup_templates": refs},
    )
    task_id = UUID("aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee")
    patient_id = UUID("11111111-aaaa-bbbb-cccc-222222222222")

    first = _select_ai_followup_template(
        connection,
        task_id=task_id,
        patient_id=patient_id,
    )
    second = _select_ai_followup_template(
        connection,
        task_id=task_id,
        patient_id=patient_id,
    )

    assert first == second
    assert first is not None
    assert first[0] in {item["name"] for item in refs}


def test_scheduler_syncs_approved_rotation_before_planning() -> None:
    scheduler = (_root() / "backend/app/runtime/automation_scheduler.py").read_text(
        encoding="utf-8"
    )
    prefix = scheduler.split("planning = plan_automation_jobs(", 1)[0]

    assert "ensure_default_rules(db, workspace.id)" in prefix
    assert "sync_approved_automation_template_rotation" in prefix


def test_rotation_is_system_owned_with_no_admin_template_picker() -> None:
    page = (_root() / "frontend/src/app/(dashboard)/automations/page.tsx").read_text(
        encoding="utf-8"
    )
    actions = (_root() / "frontend/src/app/(dashboard)/automations/actions.ts").read_text(
        encoding="utf-8"
    )
    service = (
        _root() / "backend/app/services/automation_template_rotation.py"
    ).read_text(encoding="utf-8")

    assert "template_variants" not in page
    assert "template_variants" not in actions
    assert '"template_rotation": "automatic"' in service
    assert "approved_template_refs_for_rule" in service
