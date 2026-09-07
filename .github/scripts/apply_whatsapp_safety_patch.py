from pathlib import Path


def read(path: str) -> str:
    return Path(path).read_text(encoding="utf-8")


def write(path: str, text: str) -> None:
    Path(path).write_text(text, encoding="utf-8")


def replace_once(path: str, old: str, new: str) -> None:
    text = read(path)
    if old not in text:
        raise SystemExit(f"Missing patch anchor in {path}: {old[:140]!r}")
    if text.count(old) != 1:
        raise SystemExit(f"Patch anchor not unique in {path}: {old[:140]!r}")
    write(path, text.replace(old, new, 1))


# 1) Explicit WhatsApp opt-in, separate from marketing consent.
migration = Path("backend/alembic/versions/0058_whatsapp_safety.py")
if migration.exists():
    raise SystemExit("0058_whatsapp_safety.py already exists; inspect before rerunning")
migration.write_text(
    '''"""Add explicit WhatsApp opt-in fields for proactive messaging safety.

Revision ID: 0058_whatsapp_safety
Revises: 0057_expense_type
Create Date: 2026-09-07
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "0058_whatsapp_safety"
down_revision: str | Sequence[str] | None = "0057_expense_type"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "patients",
        sa.Column(
            "whatsapp_opt_in",
            sa.Boolean(),
            nullable=False,
            server_default=sa.text("false"),
        ),
    )
    op.add_column(
        "patients",
        sa.Column("whatsapp_opt_in_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.add_column(
        "patients",
        sa.Column("whatsapp_opt_in_source", sa.String(length=32), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("patients", "whatsapp_opt_in_source")
    op.drop_column("patients", "whatsapp_opt_in_at")
    op.drop_column("patients", "whatsapp_opt_in")
''',
    encoding="utf-8",
)

replace_once(
    "backend/app/models/patient.py",
    '''    marketing_consent_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )
    source_created_at: Mapped[datetime | None] = mapped_column(''',
    '''    marketing_consent_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )
    whatsapp_opt_in: Mapped[bool] = mapped_column(
        Boolean,
        nullable=False,
        default=False,
        server_default=text("false"),
    )
    whatsapp_opt_in_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )
    whatsapp_opt_in_source: Mapped[str | None] = mapped_column(String(32), nullable=True)
    source_created_at: Mapped[datetime | None] = mapped_column(''',
)

replace_once(
    "backend/app/schemas/crm.py",
    "    marketing_consent: bool = False\n\n    @field_validator(\"first_name\")",
    "    marketing_consent: bool = False\n    whatsapp_opt_in: bool = False\n\n    @field_validator(\"first_name\")",
)
replace_once(
    "backend/app/schemas/crm.py",
    "    marketing_consent: bool | None = None\n\n    @field_validator(\"first_name\")",
    "    marketing_consent: bool | None = None\n    whatsapp_opt_in: bool | None = None\n\n    @field_validator(\"first_name\")",
)
replace_once(
    "backend/app/schemas/crm.py",
    '''    marketing_consent: bool
    marketing_consent_at: datetime | None
    source_created_at: datetime | None = None''',
    '''    marketing_consent: bool
    marketing_consent_at: datetime | None
    whatsapp_opt_in: bool
    whatsapp_opt_in_at: datetime | None
    whatsapp_opt_in_source: str | None
    source_created_at: datetime | None = None''',
)

replace_once(
    "backend/app/api/routes/crm.py",
    '''    data = payload.model_dump(exclude={"phone", "marketing_consent"})
    patient = Patient(
        workspace_id=access.workspace.id,
        marketing_consent=payload.marketing_consent,
        **data,
    )''',
    '''    data = payload.model_dump(exclude={"phone", "marketing_consent", "whatsapp_opt_in"})
    patient = Patient(
        workspace_id=access.workspace.id,
        marketing_consent=payload.marketing_consent,
        whatsapp_opt_in=payload.whatsapp_opt_in,
        **data,
    )''',
)
replace_once(
    "backend/app/api/routes/crm.py",
    '''    if payload.marketing_consent:
        patient.marketing_consent_at = datetime.now(UTC)
    db.add(patient)''',
    '''    if payload.marketing_consent:
        patient.marketing_consent_at = datetime.now(UTC)
    if payload.whatsapp_opt_in:
        patient.whatsapp_opt_in_at = datetime.now(UTC)
        patient.whatsapp_opt_in_source = "staff_recorded"
    db.add(patient)''',
)
replace_once(
    "backend/app/api/routes/crm.py",
    '    required_fields = {"first_name", "preferred_language", "source", "status", "marketing_consent"}',
    '    required_fields = {"first_name", "preferred_language", "source", "status", "marketing_consent", "whatsapp_opt_in"}',
)
replace_once(
    "backend/app/api/routes/crm.py",
    '''    if "marketing_consent" in updates:
        new_consent = updates["marketing_consent"]
        if new_consent and not patient.marketing_consent:
            patient.marketing_consent_at = datetime.now(UTC)
        elif not new_consent:
            patient.marketing_consent_at = None

    for key, value in updates.items():''',
    '''    if "marketing_consent" in updates:
        new_consent = updates["marketing_consent"]
        if new_consent and not patient.marketing_consent:
            patient.marketing_consent_at = datetime.now(UTC)
        elif not new_consent:
            patient.marketing_consent_at = None
    if "whatsapp_opt_in" in updates:
        new_whatsapp_opt_in = updates["whatsapp_opt_in"]
        if new_whatsapp_opt_in and not patient.whatsapp_opt_in:
            patient.whatsapp_opt_in_at = datetime.now(UTC)
            patient.whatsapp_opt_in_source = "staff_recorded"
        elif not new_whatsapp_opt_in:
            patient.whatsapp_opt_in_at = None
            patient.whatsapp_opt_in_source = None

    for key, value in updates.items():''',
)

# 2) Provider health and permanent-account fail-safe.
replace_once(
    "backend/app/services/channels.py",
    '''    Only the SHA-256 hash is stored in PostgreSQL. Paused or disconnected
    connections are intentionally rejected so adapters cannot ingest/process
    traffic while a channel is disabled.''',
    '''    Only the SHA-256 hash is stored in PostgreSQL. Paused connections may
    still authenticate so in-flight provider delivery callbacks can be recorded;
    inbound processing and new outbox claims remain guarded by _require_active.''',
)
replace_once(
    "backend/app/services/channels.py",
    '''        select(ChannelConnection).where(
            ChannelConnection.adapter_token_hash == hash_adapter_token(token),
            ChannelConnection.status == "active",
        )''',
    '''        select(ChannelConnection).where(
            ChannelConnection.adapter_token_hash == hash_adapter_token(token),
            ChannelConnection.status.in_(("active", "paused")),
        )''',
)
replace_once(
    "backend/app/services/channels.py",
    '''class ChannelConflictError(ChannelError):
    pass


@dataclass(frozen=True)''',
    '''class ChannelConflictError(ChannelError):
    pass


META_CONNECTION_PAUSE_ERROR_CODES = frozenset({131031})


def _meta_error_details(metadata: dict) -> tuple[int | None, str | None]:
    raw_errors = metadata.get("errors") if isinstance(metadata, dict) else None
    if not isinstance(raw_errors, list):
        return None, None
    for raw in raw_errors:
        if not isinstance(raw, dict):
            continue
        raw_code = raw.get("code")
        try:
            code = int(raw_code) if raw_code is not None else None
        except (TypeError, ValueError):
            code = None
        details = raw.get("title") or raw.get("message")
        error_data = raw.get("error_data")
        if not details and isinstance(error_data, dict):
            details = error_data.get("details")
        return code, str(details)[:2000] if details else None
    return None, None


def _provider_failure_is_permanent(error: str | None, metadata: dict) -> bool:
    code, details = _meta_error_details(metadata)
    text = " ".join(part for part in (error, details) if part).lower()
    return code in META_CONNECTION_PAUSE_ERROR_CODES or "business account locked" in text


def _record_connection_provider_health(
    connection: ChannelConnection,
    *,
    provider_status: str,
    error: str | None,
    metadata: dict,
    occurred_at: datetime | None = None,
) -> bool:
    now = occurred_at or datetime.now(UTC)
    config = dict(connection.config_json or {})
    raw_health = config.get("provider_health")
    health = dict(raw_health) if isinstance(raw_health, dict) else {}
    permanent = False

    if provider_status in {"sent", "delivered", "read"}:
        health["last_accepted_at"] = now.isoformat()
        if provider_status in {"delivered", "read"}:
            health["last_delivery_at"] = now.isoformat()
        if connection.status == "active":
            health["state"] = "healthy"
            health["current_error"] = None
            health["current_error_code"] = None
            health.pop("action_required", None)
    elif provider_status == "failed":
        code, details = _meta_error_details(metadata)
        failure = (error or details or "Provider reported message delivery failure.")[:2000]
        permanent = _provider_failure_is_permanent(failure, metadata)
        health["last_error_at"] = now.isoformat()
        health["current_error"] = failure
        health["current_error_code"] = code
        if permanent:
            connection.status = "paused"
            health["state"] = "disabled"
            health["action_required"] = "meta_account_review"
        elif connection.status == "active":
            health["state"] = "degraded"

    config["provider_health"] = health
    connection.config_json = config
    return permanent


@dataclass(frozen=True)''',
)
replace_once(
    "backend/app/services/channels.py",
    '''    _, patient = _resolve_identity(
        db,
        connection=connection,
        payload=payload,
    )
    conversation = _resolve_conversation(''',
    '''    _, patient = _resolve_identity(
        db,
        connection=connection,
        payload=payload,
    )
    if connection.channel == "whatsapp" and not patient.whatsapp_opt_in:
        patient.whatsapp_opt_in = True
        patient.whatsapp_opt_in_at = datetime.now(UTC)
        patient.whatsapp_opt_in_source = "customer_inbound"
    conversation = _resolve_conversation(''',
)
replace_once(
    "backend/app/services/channels.py",
    '''def _dispatch_is_claimable(
    dispatch: MessageDispatch,
    *,
    now: datetime,
    stale_before: datetime,
) -> bool:''',
    '''def _whatsapp_dispatch_requires_opt_in(
    connection: ChannelConnection, message: Message
) -> bool:
    if connection.channel != "whatsapp":
        return False
    metadata = message.metadata_json or {}
    source = str(metadata.get("source") or "")
    return message.message_type == "template" or source in {
        "automation_engine",
        "ai_followup",
        "crm_campaign",
    }


def _dispatch_is_claimable(
    dispatch: MessageDispatch,
    *,
    now: datetime,
    stale_before: datetime,
) -> bool:''',
)
replace_once(
    "backend/app/services/channels.py",
    '''        if message is None:
            dispatch.status = "failed"
            dispatch.last_error = "Outbound message no longer exists."
            continue

        # Only one provider send may be in flight per conversation.''',
    '''        if message is None:
            dispatch.status = "failed"
            dispatch.last_error = "Outbound message no longer exists."
            continue

        if _whatsapp_dispatch_requires_opt_in(connection, message):
            patient = db.get(Patient, conversation.patient_id)
            if patient is None or not patient.whatsapp_opt_in:
                _mark_dispatch_failed(
                    dispatch,
                    message,
                    error="WhatsApp opt-in is required before proactive messaging.",
                )
                dispatch.metadata_json = {
                    **(dispatch.metadata_json or {}),
                    "policy_block": "whatsapp_opt_in_required",
                }
                reconcile_ai_followup_dispatch(db, dispatch=dispatch, message=message)
                reconcile_campaign_dispatch(db, dispatch=dispatch, message=message)
                continue

        # Only one provider send may be in flight per conversation.''',
)
replace_once(
    "backend/app/services/channels.py",
    '''    dispatch = db.scalar(
        select(MessageDispatch)
        .where(
            MessageDispatch.workspace_id == connection.workspace_id,
            MessageDispatch.channel_connection_id == connection.id,
            MessageDispatch.provider_message_id == provider_message_id,
        )
        .with_for_update()
    )

    if dispatch is not None:''',
    '''    dispatch = db.scalar(
        select(MessageDispatch)
        .where(
            MessageDispatch.workspace_id == connection.workspace_id,
            MessageDispatch.channel_connection_id == connection.id,
            MessageDispatch.provider_message_id == provider_message_id,
        )
        .with_for_update()
    )

    _record_connection_provider_health(
        connection,
        provider_status=provider_status,
        error=error,
        metadata=metadata,
        occurred_at=occurred_at,
    )

    if dispatch is not None:''',
)
replace_once(
    "backend/app/services/channels.py",
    '''    dispatch.metadata_json = {**(dispatch.metadata_json or {}), **metadata}
    dispatch.locked_at = None

    if result_status in {"sent", "delivered", "read"}:''',
    '''    dispatch.metadata_json = {**(dispatch.metadata_json or {}), **metadata}
    dispatch.locked_at = None
    permanent_provider_failure = _record_connection_provider_health(
        connection,
        provider_status=result_status,
        error=error,
        metadata=metadata,
        occurred_at=now,
    )

    if result_status in {"sent", "delivered", "read"}:''',
)
replace_once(
    "backend/app/services/channels.py",
    '''        if retry_after_seconds and _dispatch_has_retry_budget(dispatch):
            dispatch.status = "queued"''',
    '''        if (
            retry_after_seconds
            and _dispatch_has_retry_budget(dispatch)
            and not permanent_provider_failure
        ):
            dispatch.status = "queued"''',
)

# 3) Automation-specific opt-in checks before provider work.
replace_once(
    "backend/app/services/automations.py",
    '''    if patient.status != "active":
        task.status = "cancelled"
        task.completed_at = now
        job.status = "skipped"
        job.completed_at = now
        job.locked_at = None
        job.result_json = {"reason": "patient_not_active"}
        db.commit()
        return ExecutionResult(job=job, reason="patient_not_active")

    route = _resolve_followup_route(db, task=task, now=now)''',
    '''    if patient.status != "active":
        task.status = "cancelled"
        task.completed_at = now
        job.status = "skipped"
        job.completed_at = now
        job.locked_at = None
        job.result_json = {"reason": "patient_not_active"}
        db.commit()
        return ExecutionResult(job=job, reason="patient_not_active")
    if not patient.whatsapp_opt_in:
        result = _handoff_followup_to_staff(
            task=task,
            job=job,
            conversation=None,
            reason="whatsapp_opt_in_required",
            now=now,
        )
        db.commit()
        return result

    route = _resolve_followup_route(db, task=task, now=now)''',
)
replace_once(
    "backend/app/services/automations.py",
    '''    conversation, connection = route
    display = _appointment_display_data(''',
    '''    conversation, connection = route
    if connection.channel == "whatsapp" and not patient.whatsapp_opt_in:
        job.status = "skipped"
        job.completed_at = now
        job.locked_at = None
        job.result_json = {"reason": "whatsapp_opt_in_required"}
        db.commit()
        return ExecutionResult(job=job, reason="whatsapp_opt_in_required")

    display = _appointment_display_data(''',
)

# 4) Staff-facing consent UI.
replace_once(
    "frontend/src/lib/types.ts",
    "  marketing_consent: boolean; marketing_consent_at: string | null; last_contact_at: string | null;",
    "  marketing_consent: boolean; marketing_consent_at: string | null; whatsapp_opt_in: boolean; whatsapp_opt_in_at: string | null; whatsapp_opt_in_source: string | null; last_contact_at: string | null;",
)
replace_once(
    "frontend/src/app/(dashboard)/patients/actions.ts",
    "export async function createPatientTask(formData: FormData) {",
    '''export async function setPatientWhatsappOptIn(formData: FormData) {
  const patientId = String(formData.get("patient_id") || "").trim();
  const whatsappOptIn = String(formData.get("whatsapp_opt_in") || "false") === "true";
  if (!patientId) return;

  await tiaRequest(`/crm/patients/${patientId}`, {
    method: "PATCH",
    body: JSON.stringify({ whatsapp_opt_in: whatsappOptIn }),
  });
  revalidatePatient(patientId);
}

export async function createPatientTask(formData: FormData) {''',
)
replace_once(
    "frontend/src/app/(dashboard)/patients/[patientId]/page.tsx",
    'import { addPatientNote, createPatientTask } from "../actions";',
    'import { addPatientNote, createPatientTask, setPatientWhatsappOptIn } from "../actions";',
)
replace_once(
    "frontend/src/app/(dashboard)/patients/[patientId]/page.tsx",
    '''        <Badge tone={toneForStatus(patient.status)}>{labelForStatus(patient.status)}</Badge>
        <Badge>{labelForSource(patient.source)}</Badge>
        {patient.marketing_consent && <Badge tone="green">موافق على الرسائل التسويقية</Badge>}''',
    '''        <Badge tone={toneForStatus(patient.status)}>{labelForStatus(patient.status)}</Badge>
        <Badge>{labelForSource(patient.source)}</Badge>
        <Badge tone={patient.whatsapp_opt_in ? "green" : "gray"}>
          {patient.whatsapp_opt_in ? "موافق على تواصل واتساب" : "موافقة واتساب غير مسجلة"}
        </Badge>''',
)
replace_once(
    "frontend/src/app/(dashboard)/patients/[patientId]/page.tsx",
    '''              <div className="flex justify-between gap-4"><span className="text-[var(--muted)]">آخر تواصل</span><b className="text-left">{formatDateTime(patient.last_contact_at)}</b></div>
            </CardContent>''',
    '''              <div className="flex justify-between gap-4"><span className="text-[var(--muted)]">آخر تواصل</span><b className="text-left">{formatDateTime(patient.last_contact_at)}</b></div>
              <div className="rounded-xl border border-slate-200 bg-slate-50 p-3">
                <div className="flex items-center justify-between gap-3">
                  <div>
                    <div className="text-xs font-bold text-slate-700">موافقة تواصل واتساب</div>
                    <div className="mt-1 text-[11px] leading-5 text-[var(--muted)]">
                      {patient.whatsapp_opt_in
                        ? `مسجلة${patient.whatsapp_opt_in_at ? ` · ${formatDateTime(patient.whatsapp_opt_in_at)}` : ""}`
                        : "لا تبدأ Tia رسائل واتساب تلقائية لهذا العميل حتى تُسجل موافقته."}
                    </div>
                  </div>
                  <form action={setPatientWhatsappOptIn}>
                    <input type="hidden" name="patient_id" value={patient.id} />
                    <input type="hidden" name="whatsapp_opt_in" value={String(!patient.whatsapp_opt_in)} />
                    <Button type="submit" size="sm" variant="outline">
                      {patient.whatsapp_opt_in ? "سحب الموافقة" : "تسجيل الموافقة"}
                    </Button>
                  </form>
                </div>
              </div>
            </CardContent>''',
)

replace_once(
    "frontend/src/app/(dashboard)/appointments/actions.ts",
    '''          preferred_language: "ar",
        }),''',
    '''          preferred_language: "ar",
          whatsapp_opt_in: formData.get("whatsapp_opt_in") === "on",
        }),''',
)
replace_once(
    "frontend/src/app/(dashboard)/appointments/manual-appointment-form.tsx",
    '''        <div className="grid gap-3 sm:grid-cols-2">
          <label>
            <span className="mb-1.5 block text-xs font-bold text-slate-600">اسم العميل</span>
            <Input name="first_name" required maxLength={120} placeholder="الاسم" />
          </label>
          <label>
            <span className="mb-1.5 block text-xs font-bold text-slate-600">رقم الهاتف</span>
            <Input name="phone" required maxLength={40} dir="ltr" placeholder="01xxxxxxxxx" />
          </label>
        </div>''',
    '''        <>
          <div className="grid gap-3 sm:grid-cols-2">
            <label>
              <span className="mb-1.5 block text-xs font-bold text-slate-600">اسم العميل</span>
              <Input name="first_name" required maxLength={120} placeholder="الاسم" />
            </label>
            <label>
              <span className="mb-1.5 block text-xs font-bold text-slate-600">رقم الهاتف</span>
              <Input name="phone" required maxLength={40} dir="ltr" placeholder="01xxxxxxxxx" />
            </label>
          </div>
          <label className="flex items-start gap-2 rounded-xl border border-slate-200 bg-slate-50 p-3 text-xs font-semibold text-slate-700">
            <input name="whatsapp_opt_in" type="checkbox" className="mt-0.5" />
            <span>العميل وافق بوضوح أن العيادة تبدأ معه رسائل واتساب مثل تذكير الموعد والمتابعة.</span>
          </label>
        </>''',
)

# 5) Connection health visible in Automation and explicit recovery after Meta-side fix.
replace_once(
    "frontend/src/app/(dashboard)/automations/actions.ts",
    '  const languageCode = String(formData.get("template_language") || "ar").trim() || "ar";',
    '  const languageCode = String(formData.get("template_language") || "ar_EG").trim() || "ar_EG";',
)
replace_once(
    "frontend/src/app/(dashboard)/automations/actions.ts",
    "export async function retryAutomationJob(formData: FormData) {",
    '''export async function resumeWhatsappConnection(formData: FormData) {
  const id = String(formData.get("connection_id") || "").trim();
  if (!id) return;
  await tiaRequest(`/channels/connections/${id}`, {
    method: "PATCH",
    body: JSON.stringify({ status: "active" }),
  });
  revalidatePath("/automations");
}

export async function retryAutomationJob(formData: FormData) {''',
)
replace_once(
    "frontend/src/app/(dashboard)/automations/page.tsx",
    '''  retryAutomationJob,
  saveAiFollowupTemplates,''',
    '''  retryAutomationJob,
  resumeWhatsappConnection,
  saveAiFollowupTemplates,''',
)
replace_once(
    "frontend/src/app/(dashboard)/automations/page.tsx",
    "function followupTemplateEntries(connection: ChannelConnection) {",
    '''function providerHealth(connection: ChannelConnection) {
  const raw = connection.config_json?.provider_health;
  return raw && typeof raw === "object" && !Array.isArray(raw)
    ? (raw as Record<string, unknown>)
    : null;
}

function followupTemplateEntries(connection: ChannelConnection) {''',
)
replace_once(
    "frontend/src/app/(dashboard)/automations/page.tsx",
    '''  const whatsappConnections = connections.filter(
    (connection) => connection.channel === "whatsapp" && connection.status === "active",
  );''',
    '''  const whatsappConnections = connections.filter(
    (connection) => connection.channel === "whatsapp" && connection.status !== "disconnected",
  );
  const whatsappAttention = whatsappConnections.filter((connection) => {
    const health = providerHealth(connection);
    return connection.status === "paused" || health?.state === "degraded" || health?.state === "disabled";
  });''',
)
replace_once(
    "frontend/src/app/(dashboard)/automations/page.tsx",
    '''      <div className="mb-6 grid gap-3 sm:grid-cols-3">''',
    '''      {whatsappAttention.map((connection) => {
        const health = providerHealth(connection);
        const error = typeof health?.current_error === "string" ? health.current_error : null;
        const errorCode = health?.current_error_code == null ? null : String(health.current_error_code);
        const lastDelivery = typeof health?.last_delivery_at === "string" ? health.last_delivery_at : null;
        return (
          <div key={connection.id} className="mb-4 flex items-start justify-between gap-4 rounded-2xl border border-rose-200 bg-rose-50 p-4 text-sm text-rose-950">
            <div>
              <div className="flex flex-wrap items-center gap-2">
                <b>{connection.display_name || "WhatsApp"}</b>
                <Badge tone="red">{connection.status === "paused" ? "متوقف تلقائيًا" : "يحتاج مراجعة"}</Badge>
              </div>
              <p className="mt-2 leading-6">Tia أوقفت الإرسال التلقائي لهذا الاتصال لحماية العيادة من retries غير المفيدة.</p>
              {error && <p className="mt-1 text-xs">آخر خطأ: {error}{errorCode ? ` · ${errorCode}` : ""}</p>}
              {lastDelivery && <p className="mt-1 text-xs">آخر تسليم ناجح: {formatDateTime(lastDelivery)}</p>}
            </div>
            {ctx.workspace.role === "admin" && connection.status === "paused" && (
              <form action={resumeWhatsappConnection}>
                <input type="hidden" name="connection_id" value={connection.id} />
                <Button type="submit" size="sm" variant="outline">إعادة التفعيل بعد حل مشكلة Meta</Button>
              </form>
            )}
          </div>
        );
      })}

      <div className="mb-6 grid gap-3 sm:grid-cols-3">''',
)
replace_once(
    "frontend/src/app/(dashboard)/automations/page.tsx",
    '                const language = templates[0]?.language_code || "ar";',
    '                const language = templates[0]?.language_code || "ar_EG";',
)
replace_once(
    "frontend/src/app/(dashboard)/automations/page.tsx",
    "                لا يوجد اتصال واتساب نشط حاليًا. القواعد ستبقى آمنة ولن ترسل متابعة خارج نافذة الـ24 ساعة بدون route حقيقي وقالب معتمد.",
    "                لا يوجد اتصال واتساب متصل حاليًا. القواعد ستبقى آمنة ولن ترسل متابعة خارج نافذة الـ24 ساعة بدون route حقيقي وقالب معتمد.",
)

# 6) Current migration head + tests/docs.
replace_once(
    ".github/workflows/ci.yml",
    'test "$(python -m alembic heads)" = "0057_expense_type (head)"',
    'test "$(python -m alembic heads)" = "0058_whatsapp_safety (head)"',
)
replace_once(
    "backend/app/services/operational_readiness.py",
    'EXPECTED_MIGRATION_HEAD = "0057_expense_type"',
    'EXPECTED_MIGRATION_HEAD = "0058_whatsapp_safety"',
)
for test_path in Path("backend/tests").rglob("*.py"):
    text = test_path.read_text(encoding="utf-8")
    changed = text.replace(
        'EXPECTED_MIGRATION_HEAD == "0057_expense_type"',
        'EXPECTED_MIGRATION_HEAD == "0058_whatsapp_safety"',
    ).replace(
        'EXPECTED_MIGRATION_HEAD = "0057_expense_type"',
        'EXPECTED_MIGRATION_HEAD = "0058_whatsapp_safety"',
    )
    if changed != text:
        test_path.write_text(changed, encoding="utf-8")

safety_test = Path("backend/tests/test_whatsapp_safety_hardening.py")
safety_test.write_text(
    '''from pathlib import Path
from types import SimpleNamespace

from app.schemas.crm import PatientCreate
from app.services.channels import (
    _provider_failure_is_permanent,
    _record_connection_provider_health,
    _whatsapp_dispatch_requires_opt_in,
)


def _root() -> Path:
    return Path(__file__).resolve().parents[2]


def test_whatsapp_opt_in_is_separate_and_defaults_off() -> None:
    patient = PatientCreate(first_name="Adam")
    assert patient.whatsapp_opt_in is False
    model = (_root() / "backend/app/models/patient.py").read_text(encoding="utf-8")
    assert "whatsapp_opt_in" in model
    assert "whatsapp_opt_in_at" in model
    assert "whatsapp_opt_in_source" in model


def test_customer_inbound_whatsapp_records_opt_in() -> None:
    service = (_root() / "backend/app/services/channels.py").read_text(encoding="utf-8")
    assert 'connection.channel == "whatsapp" and not patient.whatsapp_opt_in' in service
    assert 'patient.whatsapp_opt_in_source = "customer_inbound"' in service


def test_proactive_whatsapp_contract_requires_opt_in() -> None:
    connection = SimpleNamespace(channel="whatsapp")
    assert _whatsapp_dispatch_requires_opt_in(
        connection,
        SimpleNamespace(message_type="template", metadata_json={}),
    ) is True
    assert _whatsapp_dispatch_requires_opt_in(
        connection,
        SimpleNamespace(message_type="text", metadata_json={"source": "ai_followup"}),
    ) is True
    assert _whatsapp_dispatch_requires_opt_in(
        connection,
        SimpleNamespace(message_type="text", metadata_json={"source": "channel_adapter"}),
    ) is False


def test_meta_account_lock_pauses_only_the_connection() -> None:
    metadata = {"errors": [{"code": 131031, "title": "Business Account locked"}]}
    assert _provider_failure_is_permanent("Business Account locked", metadata) is True
    assert _provider_failure_is_permanent("temporary provider failure", {}) is False

    connection = SimpleNamespace(status="active", config_json={})
    permanent = _record_connection_provider_health(
        connection,
        provider_status="failed",
        error="Business Account locked",
        metadata=metadata,
    )
    assert permanent is True
    assert connection.status == "paused"
    assert connection.config_json["provider_health"]["state"] == "disabled"
    assert connection.config_json["provider_health"]["current_error_code"] == 131031
    assert connection.config_json["provider_health"]["action_required"] == "meta_account_review"


def test_paused_adapter_can_report_delivery_but_new_work_stays_blocked() -> None:
    service = (_root() / "backend/app/services/channels.py").read_text(encoding="utf-8")
    routes = (_root() / "backend/app/api/routes/channels.py").read_text(encoding="utf-8")
    assert 'ChannelConnection.status.in_(("active", "paused"))' in service
    assert "_require_active(adapter.connection)" in routes
    assert '"/adapter/outbox/provider-status"' in routes


def test_automation_ui_surfaces_provider_health_and_recovery() -> None:
    page = (_root() / "frontend/src/app/(dashboard)/automations/page.tsx").read_text(encoding="utf-8")
    actions = (_root() / "frontend/src/app/(dashboard)/automations/actions.ts").read_text(encoding="utf-8")
    assert "providerHealth" in page
    assert "متوقف تلقائيًا" in page
    assert "resumeWhatsappConnection" in page
    assert 'body: JSON.stringify({ status: "active" })' in actions


def test_whatsapp_safety_migration_is_current_head() -> None:
    migration = (_root() / "backend/alembic/versions/0058_whatsapp_safety.py").read_text(encoding="utf-8")
    readiness = (_root() / "backend/app/services/operational_readiness.py").read_text(encoding="utf-8")
    assert 'revision: str = "0058_whatsapp_safety"' in migration
    assert 'down_revision: str | Sequence[str] | None = "0057_expense_type"' in migration
    assert 'EXPECTED_MIGRATION_HEAD = "0058_whatsapp_safety"' in readiness
''',
    encoding="utf-8",
)

setup_path = Path("n8n/AUTOMATIONS_SETUP.md")
setup = setup_path.read_text(encoding="utf-8")
marker = "## WhatsApp outbox worker\n"
safety_docs = '''## WhatsApp proactive-message safety

Tia stores WhatsApp opt-in separately from marketing consent. A customer inbound WhatsApp message records the WhatsApp-contact opt-in, while staff can explicitly record or withdraw it from the patient profile. Proactive templates and automation sends are blocked when opt-in is missing.

Provider account-level failures such as Meta error `131031` pause only that clinic's WhatsApp connection. The Automation page surfaces provider health and the last provider error. AI CRM follow-ups fall back to staff work instead of retrying indefinitely, and a paused connection must be explicitly re-enabled after the Meta-side issue is resolved. Production onboarding should connect each clinic to its own WABA/phone so a restriction on one clinic does not stop other tenants.

'''
if marker not in setup:
    raise SystemExit("Missing setup docs anchor")
setup_path.write_text(setup.replace(marker, safety_docs + marker, 1), encoding="utf-8")
