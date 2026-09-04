from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]


def load(path: str) -> str:
    return (ROOT / path).read_text(encoding="utf-8")


def save(path: str, text: str) -> None:
    (ROOT / path).write_text(text, encoding="utf-8")


def replace_once(text: str, old: str, new: str, *, label: str) -> str:
    count = text.count(old)
    if count != 1:
        raise AssertionError(f"{label}: expected one anchor, found {count}")
    return text.replace(old, new, 1)


# Product catalog: no-show follows the same recovery path as cancellation.
path = "backend/app/core/automation_rules.py"
text = load(path)
block = '''    DefaultAutomationRule(\n        key="no_show_followup",\n        name="No-show recovery follow-up",\n        trigger_kind="after_no_show",\n        offset_minutes=30,\n        channel="whatsapp",\n        template_name="tia_no_show_followup_ar",\n        template_language="ar",\n        max_lateness_minutes=720,\n        enabled_by_default=False,\n    ),\n'''
if block in text:
    text = text.replace(block, "", 1)
    save(path, text)


path = "backend/app/services/automations.py"
text = load(path)
if 'RETIRED_AUTOMATION_RULE_KEYS = frozenset({"no_show_followup"})' not in text:
    text = replace_once(
        text,
        'LEAD_FOLLOWUP_ELIGIBLE_STATUSES = frozenset({"new", "contacted", "qualified"})\n',
        'LEAD_FOLLOWUP_ELIGIBLE_STATUSES = frozenset({"new", "contacted", "qualified"})\nRETIRED_AUTOMATION_RULE_KEYS = frozenset({"no_show_followup"})\n',
        label="retired rule constant",
    )

    old = '''    created = False\n    for definition in DEFAULT_AUTOMATION_RULES:\n        if definition.key in existing:\n            continue\n'''
    new = '''    changed = False\n    for retired_key in RETIRED_AUTOMATION_RULE_KEYS:\n        retired = existing.get(retired_key)\n        if retired is not None and retired.enabled:\n            retired.enabled = False\n            changed = True\n\n    for definition in DEFAULT_AUTOMATION_RULES:\n        if definition.key in existing:\n            continue\n'''
    text = replace_once(text, old, new, label="retire existing rules")
    text = replace_once(text, "        created = True\n    if created:\n", "        changed = True\n    if changed:\n", label="rule change flag")

    old = '''    if rule.trigger_kind == "after_cancelled":\n        return appointment.status == "cancelled" and appointment.cancelled_at is not None\n'''
    new = '''    if rule.trigger_kind == "after_cancelled":\n        return (\n            (appointment.status == "cancelled" and appointment.cancelled_at is not None)\n            or (appointment.status == "no_show" and appointment.no_show_at is not None)\n        )\n'''
    text = replace_once(text, old, new, label="cancellation recovery eligibility")

    old = '''    if rule.trigger_kind == "after_cancelled":\n        oldest = now - timedelta(days=7)\n        return list(\n            db.scalars(\n                select(Appointment).where(\n                    Appointment.workspace_id == workspace_id,\n                    Appointment.status == "cancelled",\n                    Appointment.cancelled_at.is_not(None),\n                    Appointment.cancelled_at >= oldest,\n                )\n            )\n        )\n'''
    new = '''    if rule.trigger_kind == "after_cancelled":\n        oldest = now - timedelta(days=7)\n        return list(\n            db.scalars(\n                select(Appointment).where(\n                    Appointment.workspace_id == workspace_id,\n                    or_(\n                        and_(\n                            Appointment.status == "cancelled",\n                            Appointment.cancelled_at.is_not(None),\n                            Appointment.cancelled_at >= oldest,\n                        ),\n                        and_(\n                            Appointment.status == "no_show",\n                            Appointment.no_show_at.is_not(None),\n                            Appointment.no_show_at >= oldest,\n                        ),\n                    ),\n                )\n            )\n        )\n'''
    text = replace_once(text, old, new, label="cancellation recovery candidates")

    text = replace_once(
        text,
        "                cancelled_at=appointment.cancelled_at,\n",
        "                cancelled_at=appointment.cancelled_at or appointment.no_show_at,\n",
        label="cancellation recovery anchor",
    )

    old = '''            .where(\n                AutomationRule.workspace_id == workspace_id,\n                AutomationRule.enabled.is_(True),\n            )\n'''
    new = '''            .where(\n                AutomationRule.workspace_id == workspace_id,\n                AutomationRule.enabled.is_(True),\n                AutomationRule.key.notin_(RETIRED_AUTOMATION_RULE_KEYS),\n            )\n'''
    text = replace_once(text, old, new, label="overview excludes retired rules")
    save(path, text)


# Admin UI exposes only the unified cancellation recovery feature.
path = "frontend/src/app/(dashboard)/automations/page.tsx"
text = load(path)
text = text.replace('  no_show_followup: "متابعة عدم الحضور",\n', "")
text = text.replace('  no_show_followup: "اختياري: تتواصل مع العميل بعد عدم الحضور لعرض إعادة الحجز.",\n', "")
text = text.replace('  "no_show_followup",\n', "")
text = text.replace(', "no_show_followup"]);', ']);')
save(path, text)


# Exact product-contract tests should match the simplified feature set.
for test_name in ("test_automation_engine.py", "test_automation_product_contract.py"):
    test_path = ROOT / "backend/tests" / test_name
    source = test_path.read_text(encoding="utf-8")
    source = source.replace('        "no_show_followup",\n', "")
    source = source.replace('    assert rules["no_show_followup"].enabled_by_default is False\n', "")
    test_path.write_text(source, encoding="utf-8")


(ROOT / "backend/tests/test_no_show_cancellation_recovery.py").write_text(
    '''from pathlib import Path\n\nfrom app.core.automation_rules import DEFAULT_AUTOMATION_RULES\n\n\ndef test_no_show_has_no_separate_product_automation_rule() -> None:\n    keys = {rule.key for rule in DEFAULT_AUTOMATION_RULES}\n    assert "cancellation_recovery" in keys\n    assert "no_show_followup" not in keys\n\n\ndef test_cancellation_recovery_covers_no_show_and_retires_legacy_rule() -> None:\n    root = Path(__file__).resolve().parents[2]\n    service = (root / "backend/app/services/automations.py").read_text(encoding="utf-8")\n    assert 'RETIRED_AUTOMATION_RULE_KEYS = frozenset({"no_show_followup"})' in service\n    assert 'appointment.status == "no_show" and appointment.no_show_at is not None' in service\n    assert "appointment.cancelled_at or appointment.no_show_at" in service\n    assert "AutomationRule.key.notin_(RETIRED_AUTOMATION_RULE_KEYS)" in service\n\n\ndef test_admin_ui_does_not_offer_duplicate_no_show_followup() -> None:\n    root = Path(__file__).resolve().parents[2]\n    page = (root / "frontend/src/app/(dashboard)/automations/page.tsx").read_text(encoding="utf-8")\n    assert 'cancellation_recovery: "استرجاع الحجوزات الملغاة"' in page\n    assert "no_show_followup" not in page\n''',
    encoding="utf-8",
)

print("no-show automation simplified")
