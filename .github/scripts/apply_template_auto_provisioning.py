from __future__ import annotations

import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]


def read(path: str) -> str:
    return (ROOT / path).read_text(encoding="utf-8")


def write(path: str, text: str) -> None:
    target = ROOT / path
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(text, encoding="utf-8")


def replace_once(text: str, old: str, new: str, *, path: str) -> str:
    if old not in text:
        raise RuntimeError(f"anchor not found in {path}: {old[:120]!r}")
    return text.replace(old, new, 1)


def regex_once(text: str, pattern: str, repl: str, *, path: str) -> str:
    new, count = re.subn(pattern, repl, text, count=1, flags=re.S)
    if count != 1:
        raise RuntimeError(f"regex anchor count={count} in {path}: {pattern[:120]!r}")
    return new


# 1) Canonical template catalog. These are provisioned for every connected clinic WABA,
# independent of which optional automation toggles are enabled.
write(
    "backend/app/core/meta_whatsapp_templates.py",
    '''from __future__ import annotations

from dataclasses import dataclass
from typing import Literal


TemplateCategory = Literal["UTILITY", "MARKETING"]


@dataclass(frozen=True)
class StandardWhatsAppTemplate:
    rule_key: str
    label_ar: str
    name: str
    language: str
    category: TemplateCategory
    body_text: str
    example_body_parameters: tuple[str, ...]


STANDARD_WHATSAPP_TEMPLATES: tuple[StandardWhatsAppTemplate, ...] = (
    StandardWhatsAppTemplate(
        rule_key="booking_confirmation",
        label_ar="تأكيد الحجز (ثابت)",
        name="tia_booking_confirmation_ar",
        language="ar_EG",
        category="UTILITY",
        body_text=(
            "تمام يا {{1}}، حجز {{2}} اتسجل يوم {{3}} الساعة {{4}} في {{5}}. "
            "لو حابة تغيّري أي حاجة ابعتيلي هنا."
        ),
        example_body_parameters=("مريم", "ليزر", "12/09/2026", "17:00", "Tia Clinic"),
    ),
    StandardWhatsAppTemplate(
        rule_key="appointment_reminder_6h",
        label_ar="تذكير قبل الموعد",
        name="tia_reminder_01",
        language="ar_EG",
        category="UTILITY",
        body_text="أهلًا {{1}} 👋 بفكرك إن عندك جلسة {{2}} الساعة {{3}}. مستنيينك 💛",
        example_body_parameters=("مريم", "ليزر", "17:00"),
    ),
    StandardWhatsAppTemplate(
        rule_key="post_visit_followup",
        label_ar="متابعة بعد الزيارة",
        name="tia_post_visit_01",
        language="ar_EG",
        category="UTILITY",
        body_text="إزيك {{1}}؟ حبيت أطمن عليكي بعد {{2}} اللي كانت يوم {{3}}. كل حاجة تمام؟",
        example_body_parameters=("مريم", "ليزر", "12/09/2026"),
    ),
    StandardWhatsAppTemplate(
        rule_key="cancellation_recovery",
        label_ar="متابعة بعد الإلغاء",
        name="tia_cancellation_recovery_ar",
        language="ar_EG",
        category="UTILITY",
        body_text=(
            "أهلًا {{1}}، حبيت أساعدك بعد إلغاء موعد {{2}} يوم {{3}} الساعة {{4}}. "
            "لو حابة نرتب ميعاد جديد ابعتيلي هنا وأنا أساعدك."
        ),
        example_body_parameters=("مريم", "ليزر", "12/09/2026", "17:00"),
    ),
    StandardWhatsAppTemplate(
        rule_key="lead_not_booked_followup",
        label_ar="متابعة العميل اللي ماحجزش",
        name="tia_ai_followup_ar",
        language="ar_EG",
        category="MARKETING",
        body_text=(
            "أهلًا {{1}}، بنتابع معاكي بخصوص {{2}}. آخر متابعة كانت يوم {{3}} الساعة {{4}} من {{5}}. "
            "لو حابة تكملي الحجز ابعتيلي هنا."
        ),
        example_body_parameters=("مريم", "استفسار عن الليزر", "12/09/2026", "17:00", "Tia Clinic"),
    ),
)

STANDARD_TEMPLATE_BY_RULE_KEY = {
    template.rule_key: template for template in STANDARD_WHATSAPP_TEMPLATES
}


def template_create_payload(template: StandardWhatsAppTemplate) -> dict[str, object]:
    return {
        "name": template.name,
        "language": template.language,
        "category": template.category,
        "components": [
            {
                "type": "BODY",
                "text": template.body_text,
                "example": {"body_text": [list(template.example_body_parameters)]},
            }
        ],
    }
''',
)

# 2) Default rules: booking confirmation is fixed-on; all standard Arabic templates use ar_EG.
path = "backend/app/core/automation_rules.py"
text = read(path)
text = regex_once(
    text,
    r'(key="booking_confirmation".*?template_language=)"ar"(.*?enabled_by_default=)False',
    r'\1"ar_EG"\2True',
    path=path,
)
text = regex_once(
    text,
    r'(key="cancellation_recovery".*?template_language=)"ar"',
    r'\1"ar_EG"',
    path=path,
)
text = regex_once(
    text,
    r'(key="lead_not_booked_followup".*?template_language=)"ar"',
    r'\1"ar_EG"',
    path=path,
)
write(path, text)

# 3) Remove the product's arbitrary seven-day timing ceiling.
path = "backend/app/schemas/automation.py"
text = read(path)
text = replace_once(
    text,
    '    offset_minutes: int | None = Field(default=None, ge=-10080, le=10080)\n',
    '    offset_minutes: int | None = None\n',
    path=path,
)
text = replace_once(
    text,
    '    max_lateness_minutes: int | None = Field(default=None, ge=0, le=10080)\n',
    '    max_lateness_minutes: int | None = Field(default=None, ge=0)\n',
    path=path,
)
write(path, text)

path = "frontend/src/components/automation-timing-form.tsx"
text = read(path)
text = replace_once(text, '            max="10080"\n', '', path=path)
text = replace_once(
    text,
    '      <p className="mt-2 text-[11px] leading-5 text-[var(--muted)]">الحد الأقصى الحالي 7 أيام حتى تظل المتابعات قريبة من الحدث ومفهومة.</p>\n',
    '',
    path=path,
)
write(path, text)

path = "frontend/src/app/(dashboard)/automations/actions.ts"
text = read(path)
text = replace_once(text, 'import type { ChannelConnection } from "@/lib/types";\n', '', path=path)
text = replace_once(
    text,
    '  if (absoluteMinutes > 10080) {\n    throw new Error("Automation timing cannot exceed 7 days.");\n  }\n\n',
    '  if (!Number.isSafeInteger(absoluteMinutes)) {\n    throw new Error("Invalid automation timing.");\n  }\n\n',
    path=path,
)
text = regex_once(
    text,
    r'\nexport async function saveAiFollowupTemplates\(formData: FormData\) \{.*?\n\}\n\nexport async function resumeWhatsappConnection',
    '\nexport async function resumeWhatsappConnection',
    path=path,
)
write(path, text)

# 4) Booking confirmation is a backend invariant, and planning expands with arbitrary offsets.
path = "backend/app/services/automations.py"
text = read(path)
text = replace_once(
    text,
    '    "appointment_reminder_6h": frozenset(\n        {"tia_appointment_reminder_ar", "tia_appointment_reminder_6h_ar"}\n    ),',
    '    "appointment_reminder_6h": frozenset(\n        {"tia_appointment_reminder_ar", "tia_appointment_reminder_6h_ar", "tia_reminder_6h_01"}\n    ),',
    path=path,
)
old = '''        if definition.key in existing:
            row = existing[definition.key]
            legacy_names = LEGACY_DEFAULT_TEMPLATE_NAMES.get(definition.key, frozenset())
            if row.template_name in legacy_names and row.template_name != definition.template_name:
                row.template_name = definition.template_name
                row.template_language = definition.template_language
                changed = True
            continue
'''
new = '''        if definition.key in existing:
            row = existing[definition.key]
            legacy_names = LEGACY_DEFAULT_TEMPLATE_NAMES.get(definition.key, frozenset())
            if row.template_name in legacy_names and row.template_name != definition.template_name:
                row.template_name = definition.template_name
                row.template_language = definition.template_language
                changed = True
            if (
                row.template_name == definition.template_name
                and row.template_language != definition.template_language
            ):
                row.template_language = definition.template_language
                changed = True
            if definition.key == "booking_confirmation" and not row.enabled:
                row.enabled = True
                changed = True
            continue
'''
text = replace_once(text, old, new, path=path)
text = replace_once(
    text,
    '    if rule.trigger_kind in {"appointment_created", "before_appointment"}:\n        return list(\n',
    '    if rule.trigger_kind in {"appointment_created", "before_appointment"}:\n        appointment_horizon = horizon\n        if rule.trigger_kind == "before_appointment" and rule.offset_minutes < 0:\n            appointment_horizon = horizon + timedelta(minutes=abs(rule.offset_minutes))\n        return list(\n',
    path=path,
)
text = replace_once(text, '                    Appointment.start_at <= horizon,\n', '                    Appointment.start_at <= appointment_horizon,\n', path=path)
text = replace_once(
    text,
    '        oldest = now - timedelta(days=14)\n',
    '        oldest = now - max(\n            timedelta(days=14),\n            timedelta(minutes=max(0, rule.offset_minutes) + rule.max_lateness_minutes),\n        )\n',
    path=path,
)
text = replace_once(
    text,
    '        oldest = now - timedelta(days=7)\n',
    '        oldest = now - max(\n            timedelta(days=7),\n            timedelta(minutes=max(0, rule.offset_minutes) + rule.max_lateness_minutes),\n        )\n',
    path=path,
)
text = replace_once(
    text,
    '        oldest = now - timedelta(days=7)\n',
    '        oldest = now - max(\n            timedelta(days=7),\n            timedelta(minutes=max(0, rule.offset_minutes) + rule.max_lateness_minutes),\n        )\n',
    path=path,
)
text = replace_once(
    text,
    '    oldest = now - timedelta(days=30)\n',
    '    oldest = now - max(\n        timedelta(days=30),\n        timedelta(minutes=max(0, rule.offset_minutes) + rule.max_lateness_minutes),\n    )\n',
    path=path,
)
text = replace_once(
    text,
    '                AutomationRule.key.notin_(RETIRED_AUTOMATION_RULE_KEYS),\n',
    '                AutomationRule.key.notin_(RETIRED_AUTOMATION_RULE_KEYS | {"booking_confirmation"}),\n',
    path=path,
)
write(path, text)

path = "backend/app/api/routes/automations.py"
text = read(path)
anchor = '    changes = payload.model_dump(exclude_unset=True)\n    changed_fields = sorted(changes)\n    previous_enabled = rule.enabled\n\n'
replacement = '''    changes = payload.model_dump(exclude_unset=True)
    changed_fields = sorted(changes)
    previous_enabled = rule.enabled

    if rule.key == "booking_confirmation" and changes.get("enabled") is False:
        raise HTTPException(
            status_code=409,
            detail="Booking confirmation is a fixed Tia message and cannot be disabled.",
        )

'''
text = replace_once(text, anchor, replacement, path=path)
write(path, text)

# 5) Setup API returns every standard template with its live Meta status.
path = "backend/app/schemas/whatsapp_setup.py"
text = read(path)
insert = '''\n\nclass WhatsAppTemplateSetupStatus(BaseModel):
    rule_key: str
    label: str
    name: str
    language: str
    category: str
    status: str
    error: str | None = None
'''
text = replace_once(text, '\n\nclass WhatsAppSetupState(BaseModel):\n', insert + '\n\nclass WhatsAppSetupState(BaseModel):\n', path=path)
text = replace_once(
    text,
    '    webhook_verified: bool = False\n',
    '    webhook_verified: bool = False\n    templates: list[WhatsAppTemplateSetupStatus] = Field(default_factory=list)\n',
    path=path,
)
write(path, text)

# 6) Native transport auto-creates the full standard template catalog and monitors all of it.
path = "backend/app/services/meta_whatsapp_transport.py"
text = read(path)
text = replace_once(
    text,
    'from app.core.meta_whatsapp_config import meta_whatsapp_settings\n',
    'from app.core.meta_whatsapp_config import meta_whatsapp_settings\nfrom app.core.meta_whatsapp_templates import (\n    STANDARD_TEMPLATE_BY_RULE_KEY,\n    STANDARD_WHATSAPP_TEMPLATES,\n    template_create_payload,\n)\n',
    path=path,
)
text = replace_once(text, 'from app.models.automation_rule import AutomationRule\n', '', path=path)
text = regex_once(
    text,
    r'def _required_template_names\(db: Session, connection: ChannelConnection\) -> list\[str\]:.*?\n\n\ndef _parse_utc_timestamp',
    'def _required_template_names(db: Session, connection: ChannelConnection) -> list[str]:\n    del db, connection\n    return [template.name for template in STANDARD_WHATSAPP_TEMPLATES]\n\n\ndef _parse_utc_timestamp',
    path=path,
)
provision_fn = '''\n\ndef provision_standard_whatsapp_templates(
    token: str,
    waba_id: str,
    *,
    current_statuses: dict[str, str] | None = None,
) -> tuple[dict[str, str], dict[str, str]]:
    """Create every Tia standard template that is missing from this clinic WABA."""
    errors: dict[str, str] = {}
    if current_statuses is None:
        try:
            statuses = _fetch_template_statuses(token, waba_id)
        except (httpx.HTTPError, MetaWhatsAppTransportError) as exc:
            return {}, {"__all__": str(exc)[:2000]}
    else:
        statuses = dict(current_statuses)

    endpoint = _graph_url(f"{waba_id}/message_templates")
    headers = {"Authorization": f"Bearer {token}"}
    for template in STANDARD_WHATSAPP_TEMPLATES:
        if template.name in statuses:
            continue
        try:
            response = httpx.post(
                endpoint,
                json=template_create_payload(template),
                headers=headers,
                timeout=20.0,
            )
        except httpx.HTTPError as exc:
            errors[template.name] = str(exc)[:2000]
            statuses[template.name] = "error"
            continue
        if response.status_code >= 400:
            message, _ = _provider_error_payload(response)
            errors[template.name] = message[:2000]
            statuses[template.name] = "error"
            continue
        payload = response.json()
        raw_status = payload.get("status") if isinstance(payload, dict) else None
        statuses[template.name] = str(raw_status or "pending").strip().lower()
    return statuses, errors
'''
text = replace_once(text, '\n\ndef _set_provider_health(\n', provision_fn + '\n\ndef _set_provider_health(\n', path=path)
text = replace_once(
    text,
    '        phone_info = _fetch_phone_info(token, phone_number_id)\n        template_statuses = _fetch_template_statuses(token, waba_id)\n',
    '        phone_info = _fetch_phone_info(token, phone_number_id)\n        template_statuses = _fetch_template_statuses(token, waba_id)\n        template_statuses, template_provisioning_errors = provision_standard_whatsapp_templates(\n            token, waba_id, current_statuses=template_statuses\n        )\n',
    path=path,
)
text = replace_once(
    text,
    '            "template_statuses": template_statuses,\n            "templates_checked_at": datetime.now(UTC).isoformat(),\n',
    '            "template_statuses": template_statuses,\n            "template_provisioning_errors": template_provisioning_errors,\n            "templates_checked_at": datetime.now(UTC).isoformat(),\n            "ai_followup_templates": [\n                {\n                    "name": STANDARD_TEMPLATE_BY_RULE_KEY["lead_not_booked_followup"].name,\n                    "language_code": STANDARD_TEMPLATE_BY_RULE_KEY["lead_not_booked_followup"].language,\n                }\n            ],\n            "ai_followup_template": {\n                "name": STANDARD_TEMPLATE_BY_RULE_KEY["lead_not_booked_followup"].name,\n                "language_code": STANDARD_TEMPLATE_BY_RULE_KEY["lead_not_booked_followup"].language,\n            },\n',
    path=path,
)
write(path, text)

# 7) Direct onboarding provisions templates immediately after credentials are accepted,
# before the admin even finishes the webhook step.
path = "backend/app/services/meta_whatsapp_onboarding.py"
text = read(path)
text = replace_once(
    text,
    'from app.core.meta_whatsapp_config import meta_whatsapp_settings as settings\n',
    'from app.core.meta_whatsapp_config import meta_whatsapp_settings as settings\nfrom app.core.meta_whatsapp_templates import (\n    STANDARD_TEMPLATE_BY_RULE_KEY,\n    STANDARD_WHATSAPP_TEMPLATES,\n)\n',
    path=path,
)
text = replace_once(text, 'from app.models.automation_rule import AutomationRule\n', '', path=path)
text = replace_once(
    text,
    'from app.schemas.whatsapp_setup import WhatsAppSetupState\n',
    'from app.schemas.whatsapp_setup import WhatsAppSetupState, WhatsAppTemplateSetupStatus\n',
    path=path,
)
old_rules = '''    rules = list(
        db.scalars(
            select(AutomationRule).where(
                AutomationRule.workspace_id == workspace_id,
                AutomationRule.enabled.is_(True),
                AutomationRule.channel.in_(("whatsapp", "auto")),
            )
        )
    )
    required_templates = [rule.template_name for rule in rules if rule.template_name]
    statuses = _template_statuses(connection)
    templates_ready = not required_templates or all(
        statuses.get(name, "").lower() == "approved" for name in required_templates
    )
'''
new_rules = '''    statuses = _template_statuses(connection)
    raw_template_errors = config.get("template_provisioning_errors")
    template_errors = raw_template_errors if isinstance(raw_template_errors, dict) else {}
    template_states = [
        WhatsAppTemplateSetupStatus(
            rule_key=template.rule_key,
            label=template.label_ar,
            name=template.name,
            language=template.language,
            category=template.category,
            status=str(statuses.get(template.name) or "missing").lower(),
            error=(
                str(template_errors.get(template.name))
                if template_errors.get(template.name)
                else None
            ),
        )
        for template in STANDARD_WHATSAPP_TEMPLATES
    ]
    templates_ready = all(item.status == "approved" for item in template_states)
'''
text = replace_once(text, old_rules, new_rules, path=path)
old_rejected = '''        rejected_templates = [
            name
            for name in required_templates
            if statuses.get(name, "").lower() == "rejected"
        ]
'''
new_rejected = '''        rejected_templates = [
            item.name for item in template_states if item.status == "rejected"
        ]
'''
text = replace_once(text, old_rejected, new_rejected, path=path)
text = replace_once(
    text,
    '            system_message = "Tia بتتابع اعتماد القوالب المطلوبة للـAutomations المفعلة."\n',
    '            system_message = "Tia أنشأت القوالب القياسية تلقائيًا وبتتابع اعتمادها من Meta."\n',
    path=path,
)
text = replace_once(
    text,
    '        webhook_verified=webhook_verified,\n        admin_action=admin_action,  # type: ignore[arg-type]\n',
    '        webhook_verified=webhook_verified,\n        templates=template_states,\n        admin_action=admin_action,  # type: ignore[arg-type]\n',
    path=path,
)
connect_tail = '''    db.commit()
    db.refresh(connection)
    return build_whatsapp_setup_state(db, workspace_id=workspace_id)
'''
connect_new = '''    db.commit()
    db.refresh(connection)

    from app.services.meta_whatsapp_transport import provision_standard_whatsapp_templates

    template_statuses, template_errors = provision_standard_whatsapp_templates(
        access_token,
        waba_id,
    )
    current_config = dict(connection.config_json or {})
    current_config["template_statuses"] = template_statuses
    current_config["template_provisioning_errors"] = template_errors
    lead_template = STANDARD_TEMPLATE_BY_RULE_KEY["lead_not_booked_followup"]
    current_config["ai_followup_templates"] = [
        {"name": lead_template.name, "language_code": lead_template.language}
    ]
    current_config["ai_followup_template"] = {
        "name": lead_template.name,
        "language_code": lead_template.language,
    }
    connection.config_json = current_config
    db.commit()
    db.refresh(connection)
    return build_whatsapp_setup_state(db, workspace_id=workspace_id)
'''
text = replace_once(text, connect_tail, connect_new, path=path)
write(path, text)

# 8) UI: no manual template-name textarea; show each canonical template/status automatically.
path = "frontend/src/app/(dashboard)/automations/whatsapp-direct-onboarding.tsx"
text = read(path)
text = replace_once(
    text,
    '  webhook_verified: boolean;\n',
    '  webhook_verified: boolean;\n  templates: Array<{\n    rule_key: string;\n    label: string;\n    name: string;\n    language: string;\n    category: string;\n    status: string;\n    error: string | null;\n  }>;\n',
    path=path,
)
component = '''\n\nfunction TemplateStatusList({ templates }: { templates: WhatsAppSetupState["templates"] }) {
  const statusLabel = (status: string) => {
    const normalized = status.toLowerCase();
    if (normalized === "approved") return "معتمد ✅";
    if (normalized === "pending") return "قيد مراجعة Meta ⏳";
    if (normalized === "rejected") return "مرفوض ❌";
    if (normalized === "error") return "Tia هتعيد محاولة الإنشاء";
    if (normalized === "disabled") return "متوقف في Meta";
    return "قيد الإنشاء";
  };

  return (
    <div className="rounded-2xl border border-slate-200 bg-white p-5">
      <div className="font-black text-slate-950">قوالب الرسائل</div>
      <p className="mt-1 text-xs leading-5 text-[var(--muted)]">
        Tia بتنشيء كل القوالب القياسية تلقائيًا مرة واحدة في حساب واتساب بتاع العيادة، سواء الـAutomation مفعلة دلوقتي أو لأ.
      </p>
      <div className="mt-4 space-y-2">
        {templates.map((template) => (
          <div key={template.name} className="flex flex-col gap-1 rounded-xl bg-slate-50 px-3 py-2 sm:flex-row sm:items-center sm:justify-between">
            <div>
              <div className="text-sm font-bold text-slate-900">{template.label}</div>
              <div className="font-mono text-[11px] text-slate-500" dir="ltr">{template.name}</div>
              {template.error && <div className="mt-1 text-[11px] text-rose-700">{template.error}</div>}
            </div>
            <div className="text-xs font-bold text-slate-700">{statusLabel(template.status)}</div>
          </div>
        ))}
      </div>
    </div>
  );
}
'''
text = replace_once(text, '\n\nexport function WhatsAppDirectOnboarding', component + '\n\nexport function WhatsAppDirectOnboarding', path=path)
text = regex_once(
    text,
    r'  if \(state\.ready_for_automations\) \{\n    return \(.*?\n    \);\n  \}\n\n  return \(',
    '''  if (state.ready_for_automations) {
    return (
      <div className="space-y-4">
        <div className="rounded-2xl border border-emerald-200 bg-emerald-50 p-5">
          <div className="flex items-center gap-2 font-black text-emerald-950">
            <CheckCircle2 size={20} /> واتساب مربوط وجاهز للـAutomation
          </div>
          <p className="mt-2 text-sm leading-6 text-emerald-900">
            {state.verified_name || state.display_phone_number || "رقم العيادة"} متصل بـMeta، والـWebhook ومسار الإرسال وكل القوالب القياسية جاهزين.
          </p>
        </div>
        <TemplateStatusList templates={state.templates || []} />
      </div>
    );
  }

  return (''',
    path=path,
)
marker = '      {state.connected && state.webhook_verified && !state.ready_for_automations && (\n'
text = replace_once(
    text,
    marker,
    '      {state.connected && <TemplateStatusList templates={state.templates || []} />}\n\n' + marker,
    path=path,
)
write(path, text)

path = "frontend/src/app/(dashboard)/automations/page.tsx"
text = read(path)
text = replace_once(text, 'import { Input } from "@/components/ui/input";\n', '', path=path)
text = replace_once(text, '  saveAiFollowupTemplates,\n', '', path=path)
text = replace_once(text, '  "booking_confirmation",\n', '', path=path)
text = regex_once(
    text,
    r'\nfunction followupTemplateEntries\(connection: ChannelConnection\) \{.*?\n\}\n\nexport default async function AutomationsPage',
    '\nexport default async function AutomationsPage',
    path=path,
)
text = replace_once(
    text,
    '  const whatsappAttention = whatsappConnections.filter((connection) => {\n',
    '  const templateStatusByName = new Map(\n    (whatsappSetup?.templates || []).map((template) => [template.name, template.status.toLowerCase()]),\n  );\n  const whatsappAttention = whatsappConnections.filter((connection) => {\n',
    path=path,
)
text = replace_once(
    text,
    '          const timing = timingParts(rule);\n          const hasTiming = timingRuleKeys.has(rule.key);\n          return (\n',
    '          const timing = timingParts(rule);\n          const hasTiming = timingRuleKeys.has(rule.key);\n          const templateStatus = templateStatusByName.get(rule.template_name);\n          const running = Boolean(\n            rule.enabled &&\n            whatsappSetup?.connected &&\n            whatsappSetup.webhook_verified &&\n            whatsappSetup.transport_ready &&\n            templateStatus === "approved"\n          );\n          const waitingForSetup = rule.enabled && !running;\n          return (\n',
    path=path,
)
text = replace_once(
    text,
    '                      <Badge tone={rule.enabled ? "green" : "gray"}>\n                        {rule.enabled ? "مفعّلة" : "متوقفة"}\n                      </Badge>\n',
    '                      <Badge tone={running ? "green" : waitingForSetup ? "yellow" : "gray"}>\n                        {running ? "شغالة" : waitingForSetup ? "في انتظار التجهيز" : "متوقفة"}\n                      </Badge>\n',
    path=path,
)
text = regex_once(
    text,
    r'\n      \{ctx\.workspace\.role === "admin" && \(\n        <details className="mt-6.*?<summary className="cursor-pointer text-sm font-bold text-slate-800">\n            إعدادات قوالب واتساب المعتمدة\n          </summary>.*?\n      \)\}\n\n      <details className="mt-6',
    '\n      <details className="mt-6',
    path=path,
)
write(path, text)

# 9) Regression coverage for the new product contract.
write(
    "backend/tests/test_whatsapp_template_auto_provisioning.py",
    '''from pathlib import Path
from types import SimpleNamespace

from app.core.automation_rules import DEFAULT_AUTOMATION_RULES
from app.core.meta_whatsapp_templates import (
    STANDARD_TEMPLATE_BY_RULE_KEY,
    STANDARD_WHATSAPP_TEMPLATES,
    template_create_payload,
)
from app.services import meta_whatsapp_transport as transport


def test_every_product_whatsapp_template_has_a_canonical_meta_contract() -> None:
    assert {template.rule_key for template in STANDARD_WHATSAPP_TEMPLATES} == {
        "booking_confirmation",
        "appointment_reminder_6h",
        "post_visit_followup",
        "cancellation_recovery",
        "lead_not_booked_followup",
    }
    assert len({template.name for template in STANDARD_WHATSAPP_TEMPLATES}) == len(
        STANDARD_WHATSAPP_TEMPLATES
    )
    assert all(template.language == "ar_EG" for template in STANDARD_WHATSAPP_TEMPLATES)
    assert STANDARD_TEMPLATE_BY_RULE_KEY["lead_not_booked_followup"].category == "MARKETING"
    assert all(
        len(template.example_body_parameters) == template.body_text.count("{{")
        for template in STANDARD_WHATSAPP_TEMPLATES
    )
    for template in STANDARD_WHATSAPP_TEMPLATES:
        payload = template_create_payload(template)
        assert payload["name"] == template.name
        assert payload["language"] == "ar_EG"
        assert payload["components"]


def test_booking_confirmation_is_fixed_on_by_default() -> None:
    booking = next(rule for rule in DEFAULT_AUTOMATION_RULES if rule.key == "booking_confirmation")
    assert booking.enabled_by_default is True


def test_provisioning_creates_all_missing_templates(monkeypatch) -> None:
    calls = []

    def fake_post(url, *, json, headers, timeout):
        calls.append((url, json, headers, timeout))
        return SimpleNamespace(status_code=200, json=lambda: {"status": "PENDING"})

    monkeypatch.setattr(transport.httpx, "post", fake_post)
    statuses, errors = transport.provision_standard_whatsapp_templates(
        "token",
        "123",
        current_statuses={},
    )
    assert not errors
    assert len(calls) == len(STANDARD_WHATSAPP_TEMPLATES)
    assert set(statuses) == {template.name for template in STANDARD_WHATSAPP_TEMPLATES}
    assert set(statuses.values()) == {"pending"}


def test_provisioning_does_not_recreate_existing_templates(monkeypatch) -> None:
    approved = {template.name: "approved" for template in STANDARD_WHATSAPP_TEMPLATES}

    def unexpected_post(*args, **kwargs):
        raise AssertionError("existing standard templates must not be recreated")

    monkeypatch.setattr(transport.httpx, "post", unexpected_post)
    statuses, errors = transport.provision_standard_whatsapp_templates(
        "token",
        "123",
        current_statuses=approved,
    )
    assert statuses == approved
    assert not errors


def test_automation_ui_has_no_manual_template_names_or_seven_day_limit() -> None:
    backend = Path(__file__).resolve().parent.parent
    repo = backend.parent
    page = (repo / "frontend/src/app/(dashboard)/automations/page.tsx").read_text(encoding="utf-8")
    onboarding = (
        repo / "frontend/src/app/(dashboard)/automations/whatsapp-direct-onboarding.tsx"
    ).read_text(encoding="utf-8")
    timing = (repo / "frontend/src/components/automation-timing-form.tsx").read_text(encoding="utf-8")
    actions = (repo / "frontend/src/app/(dashboard)/automations/actions.ts").read_text(encoding="utf-8")
    schema = (backend / "app/schemas/automation.py").read_text(encoding="utf-8")

    assert "إعدادات قوالب واتساب المعتمدة" not in page
    assert "saveAiFollowupTemplates" not in page
    assert "قوالب الرسائل" in onboarding
    assert "10080" not in timing
    assert "cannot exceed 7 days" not in actions
    assert "le=10080" not in schema
''',
)

print("template auto-provisioning patch applied")
