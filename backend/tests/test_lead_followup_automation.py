from pathlib import Path
from types import SimpleNamespace
from uuid import UUID

from app.core.automation_rules import DEFAULT_AUTOMATION_RULES
from app.services.automations import (
    LEAD_FOLLOWUP_DEDUPE_PREFIX,
    _lead_followup_anchor,
    _lead_followup_dedupe_key,
)


def _root() -> Path:
    return Path(__file__).resolve().parents[2]


def test_lead_followup_is_optional_and_reuses_existing_crm_job_runtime() -> None:
    rules = {rule.key: rule for rule in DEFAULT_AUTOMATION_RULES}
    rule = rules["lead_not_booked_followup"]
    assert rule.enabled_by_default is False
    assert rule.trigger_kind == "after_lead_activity"
    assert rule.offset_minutes == 1440
    service = (_root() / "backend/app/services/automations.py").read_text(encoding="utf-8")
    assert "create_crm_task(" in service
    assert 'execution_mode="ai"' in service
    assert 'job_kind="lead_follow_up"' not in service


def test_lead_followup_anchor_prefers_real_last_contact() -> None:
    created = object()
    contacted = object()
    assert _lead_followup_anchor(SimpleNamespace(created_at=created, last_contact_at=contacted)) is contacted
    assert _lead_followup_anchor(SimpleNamespace(created_at=created, last_contact_at=None)) is created


def test_lead_followup_dedupe_is_one_shot_per_lead() -> None:
    lead_id = UUID("11111111-1111-1111-1111-111111111111")
    assert _lead_followup_dedupe_key(lead_id) == f"{LEAD_FOLLOWUP_DEDUPE_PREFIX}{lead_id}"


def test_lead_followup_guards_status_rule_and_competing_followups() -> None:
    service = (_root() / "backend/app/services/automations.py").read_text(encoding="utf-8")
    assert 'LEAD_FOLLOWUP_ELIGIBLE_STATUSES = frozenset({"new", "contacted", "qualified"})' in service
    assert 'lead.status not in LEAD_FOLLOWUP_ELIGIBLE_STATUSES' in service
    assert service.count("_system_lead_followup_ineligible_reason(") >= 4
    assert '"lead_no_longer_eligible"' in service
    assert '"lead_followup_rule_disabled"' in service
    assert '"lead_followup_superseded_by_existing_task"' in service
    assert "_other_active_lead_followup(" in service


def test_rule_disable_cancels_pending_system_lead_followups() -> None:
    route = (_root() / "backend/app/api/routes/automations.py").read_text(encoding="utf-8")
    assert 'rule.key == "lead_not_booked_followup"' in route
    assert "cancel_system_lead_followups(" in route


def test_lead_followup_ui_is_optional_and_timing_configurable() -> None:
    page = (_root() / "frontend/src/app/(dashboard)/automations/page.tsx").read_text(encoding="utf-8")
    assert 'lead_not_booked_followup: "متابعة العميل اللي ماحجزش"' in page
    assert 'rule.trigger_kind === "after_lead_activity"' in page


def test_lead_followup_migration_only_extends_trigger_constraint() -> None:
    migration = (_root() / "backend/alembic/versions/0055_lead_followup.py").read_text(encoding="utf-8")
    assert 'revision: str = "0055_lead_followup"' in migration
    assert 'down_revision: str | Sequence[str] | None = "0054_cancel_recovery"' in migration
    assert "after_lead_activity" in migration
    assert "create_table" not in migration
    assert "add_column" not in migration
