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
        raise AssertionError(f"{label}: expected exactly one anchor, found {count}")
    return text.replace(old, new, 1)


# 1) Product rule: configuration only. Execution reuses the existing CRM follow-up runtime.
path = "backend/app/core/automation_rules.py"
text = load(path)
if 'key="lead_not_booked_followup"' not in text:
    anchor = '''    DefaultAutomationRule(\n        key="no_show_followup",\n'''
    rule = '''    DefaultAutomationRule(\n        key="lead_not_booked_followup",\n        name="Lead not-booked follow-up",\n        trigger_kind="after_lead_activity",\n        offset_minutes=1440,\n        channel="whatsapp",\n        template_name="tia_ai_followup_ar",\n        template_language="ar",\n        max_lateness_minutes=1440,\n        enabled_by_default=False,\n    ),\n'''
    text = replace_once(text, anchor, rule + anchor, label="default lead rule")
    save(path, text)


# 2) Persisted trigger-kind contract.
path = "backend/app/models/automation_rule.py"
text = load(path)
if '"after_lead_activity",' not in text:
    text = replace_once(
        text,
        '    "after_cancelled",\n)',
        '    "after_cancelled",\n    "after_lead_activity",\n)',
        label="trigger tuple",
    )
    text = replace_once(
        text,
        "trigger_kind IN ('appointment_created', 'before_appointment', 'after_completed', 'after_no_show', 'after_cancelled')",
        "trigger_kind IN ('appointment_created', 'before_appointment', 'after_completed', 'after_no_show', 'after_cancelled', 'after_lead_activity')",
        label="trigger check",
    )
    save(path, text)


# 3) Planner + execution guards. No new AutomationJob kind is introduced.
path = "backend/app/services/automations.py"
text = load(path)
if 'LEAD_FOLLOWUP_RULE_KEY = "lead_not_booked_followup"' not in text:
    text = replace_once(
        text,
        "from app.models.handoff_request import HandoffRequest\n",
        "from app.models.handoff_request import HandoffRequest\nfrom app.models.lead import Lead\n",
        label="Lead import",
    )
    text = replace_once(
        text,
        "from app.services.conversation_ownership import record_outbound_activity, return_to_ai\n",
        "from app.services.conversation_ownership import record_outbound_activity, return_to_ai\nfrom app.services.crm_tasks import create_crm_task, sync_lead_next_follow_up\n",
        label="CRM task imports",
    )
    text = replace_once(
        text,
        "AUTOMATION_JOB_STALE_MINUTES = 10\n",
        "AUTOMATION_JOB_STALE_MINUTES = 10\n\n"
        'LEAD_FOLLOWUP_RULE_KEY = "lead_not_booked_followup"\n'
        'LEAD_FOLLOWUP_DEDUPE_PREFIX = "automation:lead-not-booked:"\n'
        'LEAD_FOLLOWUP_ELIGIBLE_STATUSES = frozenset({"new", "contacted", "qualified"})\n',
        label="lead constants",
    )

    helper_anchor = "\ndef plan_automation_jobs(\n"
    helpers = r'''

def _lead_followup_anchor(lead: Lead) -> datetime:
    return lead.last_contact_at or lead.created_at


def _lead_followup_dedupe_key(lead_id: UUID) -> str:
    return f"{LEAD_FOLLOWUP_DEDUPE_PREFIX}{lead_id}"


def _is_system_lead_followup_task(task: CRMTask) -> bool:
    return (
        task.source == "system"
        and task.execution_mode == "ai"
        and task.lead_id is not None
        and str(task.dedupe_key or "").startswith(LEAD_FOLLOWUP_DEDUPE_PREFIX)
    )


def _other_active_lead_followup(
    db: Session,
    *,
    workspace_id: UUID,
    lead_id: UUID,
    exclude_task_id: UUID | None = None,
) -> CRMTask | None:
    stmt = select(CRMTask).where(
        CRMTask.workspace_id == workspace_id,
        CRMTask.lead_id == lead_id,
        CRMTask.task_type == "follow_up",
        CRMTask.status.in_(("pending", "in_progress")),
    )
    if exclude_task_id is not None:
        stmt = stmt.where(CRMTask.id != exclude_task_id)
    return db.scalar(stmt.order_by(CRMTask.due_at, CRMTask.created_at).limit(1))


def _system_lead_followup_ineligible_reason(
    db: Session,
    *,
    task: CRMTask,
    for_update: bool = False,
) -> str | None:
    if not _is_system_lead_followup_task(task):
        return None

    rule_stmt = select(AutomationRule).where(
        AutomationRule.workspace_id == task.workspace_id,
        AutomationRule.key == LEAD_FOLLOWUP_RULE_KEY,
    )
    if for_update:
        rule_stmt = rule_stmt.with_for_update()
    rule = db.scalar(rule_stmt)
    if rule is None or not rule.enabled:
        return "lead_followup_rule_disabled"

    lead_stmt = select(Lead).where(
        Lead.workspace_id == task.workspace_id,
        Lead.id == task.lead_id,
    )
    if for_update:
        lead_stmt = lead_stmt.with_for_update()
    lead = db.scalar(lead_stmt)
    if lead is None or lead.patient_id != task.patient_id:
        return "lead_followup_target_missing"
    if lead.status not in LEAD_FOLLOWUP_ELIGIBLE_STATUSES:
        return "lead_no_longer_eligible"
    if _other_active_lead_followup(
        db,
        workspace_id=task.workspace_id,
        lead_id=lead.id,
        exclude_task_id=task.id,
    ) is not None:
        return "lead_followup_superseded_by_existing_task"
    return None


def _cancel_system_lead_followup_task(
    db: Session,
    *,
    task: CRMTask,
    now: datetime,
    reason: str,
) -> bool:
    if task.status not in {"pending", "in_progress"}:
        return False
    job = db.scalar(
        select(AutomationJob)
        .where(
            AutomationJob.workspace_id == task.workspace_id,
            AutomationJob.crm_task_id == task.id,
            AutomationJob.job_kind == "crm_follow_up",
        )
        .with_for_update()
    )
    if job is not None and job.status == "dispatched":
        if not _cancel_pending_job_dispatch(db, job=job, reason=reason):
            return False
    if job is not None and job.status in {"queued", "failed", "processing", "dispatched"}:
        job.status = "cancelled"
        job.locked_at = None
        job.next_attempt_at = None
        job.completed_at = now
        job.result_json = {**(job.result_json or {}), "reason": reason}
    task.status = "cancelled"
    task.completed_at = now
    sync_lead_next_follow_up(
        db,
        workspace_id=task.workspace_id,
        lead_id=task.lead_id,
    )
    return True


def cancel_system_lead_followups(
    db: Session,
    *,
    workspace_id: UUID,
    now: datetime | None = None,
) -> int:
    now = (now or datetime.now(UTC)).astimezone(UTC)
    tasks = list(
        db.scalars(
            select(CRMTask).where(
                CRMTask.workspace_id == workspace_id,
                CRMTask.source == "system",
                CRMTask.execution_mode == "ai",
                CRMTask.status.in_(("pending", "in_progress")),
                CRMTask.dedupe_key.like(f"{LEAD_FOLLOWUP_DEDUPE_PREFIX}%"),
            )
        )
    )
    cancelled = 0
    for task in tasks:
        if _cancel_system_lead_followup_task(
            db,
            task=task,
            now=now,
            reason="lead_followup_rule_disabled",
        ):
            cancelled += 1
    return cancelled


def _plan_lead_followup_rule(
    db: Session,
    *,
    workspace_id: UUID,
    rule: AutomationRule,
    now: datetime,
    horizon: datetime,
) -> PlanningResult:
    active_system_tasks = list(
        db.scalars(
            select(CRMTask).where(
                CRMTask.workspace_id == workspace_id,
                CRMTask.source == "system",
                CRMTask.execution_mode == "ai",
                CRMTask.dedupe_key.like(f"{LEAD_FOLLOWUP_DEDUPE_PREFIX}%"),
                CRMTask.status.in_(("pending", "in_progress")),
            )
        )
    )
    cancelled = 0
    for task in active_system_tasks:
        reason = _system_lead_followup_ineligible_reason(db, task=task)
        if reason is not None and _cancel_system_lead_followup_task(
            db,
            task=task,
            now=now,
            reason=reason,
        ):
            cancelled += 1

    if not rule.enabled:
        return PlanningResult(planned=0, cancelled=cancelled)

    oldest = now - timedelta(days=30)
    leads = list(
        db.scalars(
            select(Lead).where(
                Lead.workspace_id == workspace_id,
                Lead.status.in_(tuple(LEAD_FOLLOWUP_ELIGIBLE_STATUSES)),
                or_(Lead.created_at >= oldest, Lead.last_contact_at >= oldest),
            )
        )
    )
    planned = 0
    for lead in leads:
        anchor = _lead_followup_anchor(lead)
        when = (anchor + timedelta(minutes=rule.offset_minutes)).astimezone(UTC)
        if when > horizon or when + timedelta(minutes=rule.max_lateness_minutes) < now:
            continue

        dedupe_key = _lead_followup_dedupe_key(lead.id)
        task = db.scalar(
            select(CRMTask).where(
                CRMTask.workspace_id == workspace_id,
                CRMTask.dedupe_key == dedupe_key,
            )
        )
        if task is not None:
            competing = _other_active_lead_followup(
                db,
                workspace_id=workspace_id,
                lead_id=lead.id,
                exclude_task_id=task.id,
            )
            if competing is not None:
                continue
            job = db.scalar(
                select(AutomationJob).where(
                    AutomationJob.workspace_id == workspace_id,
                    AutomationJob.crm_task_id == task.id,
                    AutomationJob.job_kind == "crm_follow_up",
                )
            )
            renewable = (
                task.status == "cancelled"
                and job is not None
                and job.status == "cancelled"
                and str((job.result_json or {}).get("reason") or "")
                == "lead_followup_rule_disabled"
            )
            if renewable:
                task.status = "pending"
                task.execution_mode = "ai"
                task.completed_at = None
                task.due_at = when
                job.status = "queued"
                job.scheduled_for = when
                job.locked_at = None
                job.next_attempt_at = None
                job.completed_at = None
                job.last_error = None
                job.message_id = None
                job.dispatch_id = None
                job.result_json = {}
                sync_lead_next_follow_up(db, workspace_id=workspace_id, lead_id=lead.id)
            elif task.status == "pending" and task.execution_mode == "ai" and job is not None:
                task.due_at = when
                if job.status in {"queued", "failed"}:
                    job.status = "queued"
                    job.scheduled_for = when
                    job.next_attempt_at = None
                    job.locked_at = None
                    job.last_error = None
                sync_lead_next_follow_up(db, workspace_id=workspace_id, lead_id=lead.id)
            continue

        if _other_active_lead_followup(
            db,
            workspace_id=workspace_id,
            lead_id=lead.id,
        ) is not None:
            continue

        create_crm_task(
            db,
            workspace_id=workspace_id,
            patient_id=lead.patient_id,
            lead_id=lead.id,
            title="مساعدة في استكمال الحجز",
            description=(
                "تابع مع العميل بشكل طبيعي لأنه مهتم ولم يكمل الحجز بعد. "
                "جاوب على أسئلته واعرض المساعدة في الحجز بدون اختراع خصم أو استعجال غير حقيقي."
            ),
            due_at=when,
            task_type="follow_up",
            priority="normal",
            source="system",
            execution_mode="ai",
            dedupe_key=dedupe_key,
            commit=False,
        )
        planned += 1
    return PlanningResult(planned=planned, cancelled=cancelled)
'''
    text = replace_once(text, helper_anchor, helpers + helper_anchor, label="lead planner helpers")

    plan_anchor = '''    enabled_rules = [rule for rule in rules if rule.enabled]\n    for rule in enabled_rules:\n'''
    plan_replacement = '''    lead_rules = [rule for rule in rules if rule.trigger_kind == "after_lead_activity"]\n    for lead_rule in lead_rules:\n        lead_result = _plan_lead_followup_rule(\n            db,\n            workspace_id=workspace_id,\n            rule=lead_rule,\n            now=now,\n            horizon=horizon,\n        )\n        planned += lead_result.planned\n        cancelled += lead_result.cancelled\n\n    enabled_rules = [\n        rule\n        for rule in rules\n        if rule.enabled and rule.trigger_kind != "after_lead_activity"\n    ]\n    for rule in enabled_rules:\n'''
    text = replace_once(text, plan_anchor, plan_replacement, label="lead planner integration")

    generic_anchor = '''    if task.execution_mode != "ai" or task.status not in {"pending", "in_progress"}:\n        job.status = "cancelled"\n'''
    initial_guard = '''    lead_followup_reason = _system_lead_followup_ineligible_reason(\n        db,\n        task=task,\n        for_update=True,\n    )\n    if lead_followup_reason is not None:\n        task.status = "cancelled"\n        task.completed_at = now\n        job.status = "cancelled"\n        job.completed_at = now\n        job.locked_at = None\n        job.next_attempt_at = None\n        job.result_json = {"reason": lead_followup_reason}\n        sync_lead_next_follow_up(\n            db,\n            workspace_id=workspace_id,\n            lead_id=task.lead_id,\n        )\n        db.commit()\n        return ExecutionResult(job=job, reason=lead_followup_reason)\n\n'''
    text = replace_once(text, generic_anchor, initial_guard + generic_anchor, label="initial lead guard")

    final_anchor = '''    if final_conversation.last_message_at != last_message_at_snapshot:\n        final_job.status = "failed"\n'''
    final_guard = '''    lead_followup_reason = _system_lead_followup_ineligible_reason(\n        db,\n        task=final_task,\n        for_update=True,\n    )\n    if lead_followup_reason is not None:\n        final_task.status = "cancelled"\n        final_task.completed_at = now\n        final_job.status = "cancelled"\n        final_job.completed_at = now\n        final_job.locked_at = None\n        final_job.next_attempt_at = None\n        final_job.result_json = {"reason": lead_followup_reason}\n        sync_lead_next_follow_up(\n            db,\n            workspace_id=workspace_id,\n            lead_id=final_task.lead_id,\n        )\n        db.commit()\n        return ExecutionResult(job=final_job, reason=lead_followup_reason)\n\n'''
    text = replace_once(text, final_anchor, final_guard + final_anchor, label="final lead guard")
    save(path, text)


# 4) Admin disable: CRM follow-up jobs intentionally have no rule_id, so cancel them explicitly.
path = "backend/app/api/routes/automations.py"
text = load(path)
if "cancel_system_lead_followups," not in text:
    text = replace_once(
        text,
        "    cancel_automation_job,\n",
        "    cancel_automation_job,\n    cancel_system_lead_followups,\n",
        label="lead cancellation import",
    )
    anchor = '''            cancelled_job.result_json = {\n                **(cancelled_job.result_json or {}),\n                "reason": "rule_disabled_by_admin",\n            }\n\n    if changed_fields:\n'''
    replacement = '''            cancelled_job.result_json = {\n                **(cancelled_job.result_json or {}),\n                "reason": "rule_disabled_by_admin",\n            }\n        if rule.key == "lead_not_booked_followup":\n            cancel_system_lead_followups(\n                db,\n                workspace_id=access.workspace.id,\n            )\n\n    if changed_fields:\n'''
    text = replace_once(text, anchor, replacement, label="lead rule disable")
    save(path, text)


# 5) Admin UI: opt-in plus the same simple timing input used by existing rules.
path = "frontend/src/app/(dashboard)/automations/page.tsx"
text = load(path)
if 'lead_not_booked_followup: "متابعة العميل اللي ماحجزش"' not in text:
    text = replace_once(
        text,
        '  cancellation_recovery: "استرجاع الحجوزات الملغاة",\n',
        '  cancellation_recovery: "استرجاع الحجوزات الملغاة",\n  lead_not_booked_followup: "متابعة العميل اللي ماحجزش",\n',
        label="lead UI name",
    )
    text = replace_once(
        text,
        '  cancellation_recovery: "اختياري: تتواصل مع العميل بعد إلغاء الموعد وتعرض عليه ترتيب موعد جديد.",\n',
        '  cancellation_recovery: "اختياري: تتواصل مع العميل بعد إلغاء الموعد وتعرض عليه ترتيب موعد جديد.",\n  lead_not_booked_followup: "اختياري: تتابع العميل المهتم لو لسه ماحجزش وتساعده يكمل الحجز.",\n',
        label="lead UI description",
    )
    text = replace_once(
        text,
        '  "cancellation_recovery",\n  "no_show_followup",\n',
        '  "cancellation_recovery",\n  "lead_not_booked_followup",\n  "no_show_followup",\n',
        label="lead UI visibility",
    )
    text = replace_once(
        text,
        'const timingRuleKeys = new Set(["appointment_reminder_6h", "post_visit_followup", "cancellation_recovery", "no_show_followup"]);',
        'const timingRuleKeys = new Set(["appointment_reminder_6h", "post_visit_followup", "cancellation_recovery", "lead_not_booked_followup", "no_show_followup"]);',
        label="lead UI timing set",
    )
    text = replace_once(
        text,
        '  if (rule.trigger_kind === "after_cancelled") return "أرسل بعد إلغاء الموعد بـ";\n',
        '  if (rule.trigger_kind === "after_cancelled") return "أرسل بعد إلغاء الموعد بـ";\n  if (rule.trigger_kind === "after_lead_activity") return "أرسل بعد آخر تواصل بـ";\n',
        label="lead UI timing label",
    )
    save(path, text)


# 6) Migration only widens the existing trigger constraint.
migration = ROOT / "backend/alembic/versions/0055_lead_followup.py"
if not migration.exists():
    migration.write_text(
        '''"""Allow lead follow-up automation rules.\n\nRevision ID: 0055_lead_followup\nRevises: 0054_cancel_recovery\nCreate Date: 2026-09-04\n"""\n\nfrom collections.abc import Sequence\n\nfrom alembic import op\n\nrevision: str = "0055_lead_followup"\ndown_revision: str | Sequence[str] | None = "0054_cancel_recovery"\nbranch_labels: str | Sequence[str] | None = None\ndepends_on: str | Sequence[str] | None = None\n\n\ndef _replace_trigger_constraint(values: str) -> None:\n    op.drop_constraint(\n        "automation_rule_trigger_kind_valid",\n        "automation_rules",\n        type_="check",\n    )\n    op.create_check_constraint(\n        "automation_rule_trigger_kind_valid",\n        "automation_rules",\n        f"trigger_kind IN ({values})",\n    )\n\n\ndef upgrade() -> None:\n    _replace_trigger_constraint(\n        "'appointment_created', 'before_appointment', 'after_completed', 'after_no_show', 'after_cancelled', 'after_lead_activity'"\n    )\n\n\ndef downgrade() -> None:\n    _replace_trigger_constraint(\n        "'appointment_created', 'before_appointment', 'after_completed', 'after_no_show', 'after_cancelled'"\n    )\n''',
        encoding="utf-8",
    )


# 7) Operational readiness and tests that intentionally pin the current migration head.
path = "backend/app/services/operational_readiness.py"
text = load(path)
if 'EXPECTED_MIGRATION_HEAD = "0055_lead_followup"' not in text:
    text = replace_once(
        text,
        'EXPECTED_MIGRATION_HEAD = "0054_cancel_recovery"',
        'EXPECTED_MIGRATION_HEAD = "0055_lead_followup"',
        label="readiness migration head",
    )
    save(path, text)

for test_path in (ROOT / "backend/tests").glob("test_*.py"):
    source = test_path.read_text(encoding="utf-8")
    updated = source.replace(
        'EXPECTED_MIGRATION_HEAD == "0054_cancel_recovery"',
        'EXPECTED_MIGRATION_HEAD == "0055_lead_followup"',
    ).replace(
        'EXPECTED_MIGRATION_HEAD = "0054_cancel_recovery"',
        'EXPECTED_MIGRATION_HEAD = "0055_lead_followup"',
    )
    if updated != source:
        test_path.write_text(updated, encoding="utf-8")

for test_name in ("test_automation_engine.py", "test_automation_product_contract.py"):
    test_path = ROOT / "backend/tests" / test_name
    source = test_path.read_text(encoding="utf-8")
    if '        "lead_not_booked_followup",\n' not in source:
        source = replace_once(
            source,
            '        "cancellation_recovery",\n        "no_show_followup",',
            '        "cancellation_recovery",\n        "lead_not_booked_followup",\n        "no_show_followup",',
            label=f"{test_name} rule set",
        )
    if test_name == "test_automation_product_contract.py" and 'rules["lead_not_booked_followup"]' not in source:
        source = replace_once(
            source,
            '    assert rules["cancellation_recovery"].enabled_by_default is False\n',
            '    assert rules["cancellation_recovery"].enabled_by_default is False\n    assert rules["lead_not_booked_followup"].enabled_by_default is False\n',
            label="lead default disabled assertion",
        )
    test_path.write_text(source, encoding="utf-8")


# 8) Focused contracts: reuse, eligibility, duplicate suppression, UI, and migration shape.
(ROOT / "backend/tests/test_lead_followup_automation.py").write_text(
    '''from pathlib import Path\nfrom types import SimpleNamespace\nfrom uuid import UUID\n\nfrom app.core.automation_rules import DEFAULT_AUTOMATION_RULES\nfrom app.services.automations import (\n    LEAD_FOLLOWUP_DEDUPE_PREFIX,\n    _lead_followup_anchor,\n    _lead_followup_dedupe_key,\n)\n\n\ndef _root() -> Path:\n    return Path(__file__).resolve().parents[2]\n\n\ndef test_lead_followup_is_optional_and_reuses_existing_crm_job_runtime() -> None:\n    rules = {rule.key: rule for rule in DEFAULT_AUTOMATION_RULES}\n    rule = rules["lead_not_booked_followup"]\n    assert rule.enabled_by_default is False\n    assert rule.trigger_kind == "after_lead_activity"\n    assert rule.offset_minutes == 1440\n    service = (_root() / "backend/app/services/automations.py").read_text(encoding="utf-8")\n    assert "create_crm_task(" in service\n    assert 'execution_mode="ai"' in service\n    assert 'job_kind="lead_follow_up"' not in service\n\n\ndef test_lead_followup_anchor_prefers_real_last_contact() -> None:\n    created = object()\n    contacted = object()\n    assert _lead_followup_anchor(SimpleNamespace(created_at=created, last_contact_at=contacted)) is contacted\n    assert _lead_followup_anchor(SimpleNamespace(created_at=created, last_contact_at=None)) is created\n\n\ndef test_lead_followup_dedupe_is_one_shot_per_lead() -> None:\n    lead_id = UUID("11111111-1111-1111-1111-111111111111")\n    assert _lead_followup_dedupe_key(lead_id) == f"{LEAD_FOLLOWUP_DEDUPE_PREFIX}{lead_id}"\n\n\ndef test_lead_followup_guards_status_rule_and_competing_followups() -> None:\n    service = (_root() / "backend/app/services/automations.py").read_text(encoding="utf-8")\n    assert 'LEAD_FOLLOWUP_ELIGIBLE_STATUSES = frozenset({"new", "contacted", "qualified"})' in service\n    assert 'lead.status not in LEAD_FOLLOWUP_ELIGIBLE_STATUSES' in service\n    assert service.count("_system_lead_followup_ineligible_reason(") >= 4\n    assert '"lead_no_longer_eligible"' in service\n    assert '"lead_followup_rule_disabled"' in service\n    assert '"lead_followup_superseded_by_existing_task"' in service\n    assert "_other_active_lead_followup(" in service\n\n\ndef test_rule_disable_cancels_pending_system_lead_followups() -> None:\n    route = (_root() / "backend/app/api/routes/automations.py").read_text(encoding="utf-8")\n    assert 'rule.key == "lead_not_booked_followup"' in route\n    assert "cancel_system_lead_followups(" in route\n\n\ndef test_lead_followup_ui_is_optional_and_timing_configurable() -> None:\n    page = (_root() / "frontend/src/app/(dashboard)/automations/page.tsx").read_text(encoding="utf-8")\n    assert 'lead_not_booked_followup: "متابعة العميل اللي ماحجزش"' in page\n    assert 'rule.trigger_kind === "after_lead_activity"' in page\n\n\ndef test_lead_followup_migration_only_extends_trigger_constraint() -> None:\n    migration = (_root() / "backend/alembic/versions/0055_lead_followup.py").read_text(encoding="utf-8")\n    assert 'revision: str = "0055_lead_followup"' in migration\n    assert 'down_revision: str | Sequence[str] | None = "0054_cancel_recovery"' in migration\n    assert "after_lead_activity" in migration\n    assert "create_table" not in migration\n    assert "add_column" not in migration\n''',
    encoding="utf-8",
)


# 9) Runtime note.
path = "n8n/AUTOMATIONS_SETUP.md"
text = load(path)
if "## Lead not-booked follow-up" not in text:
    text += '''\n\n## Lead not-booked follow-up\n\n`lead_not_booked_followup` is optional and disabled by default. The admin chooses the delay after the lead's latest recorded contact, falling back to lead creation time.\nThe planner creates one idempotent system AI CRM follow-up task per lead and reuses the existing `crm_follow_up` AutomationJob runtime; there is no lead-specific job type or workflow engine.\nBefore sending, Tia verifies that the rule is still enabled, the lead is still `new`, `contacted`, or `qualified`, and no other active follow-up task is already handling that lead. `booked`, `won`, `lost`, and `spam` leads are not contacted by this automation.\nInside WhatsApp's 24-hour window the normal AI follow-up composer is used. Outside that window the existing connection-level approved `ai_followup_template` policy still applies.\n'''
    save(path, text)

print("lead follow-up patch applied")
