# Tia AI Automations Engine — n8n Setup

Version: 0.38.0

## Architecture

PostgreSQL/Tia remains the source of truth.

n8n only:
1. wakes up on a schedule,
2. asks Tia to plan + claim due automation jobs,
3. asks Tia to execute each claimed job,
4. wakes Tia's clinic-sync runtime on a separate branch,
5. lets the existing WhatsApp outbox worker deliver queued messages.

Do not put booking state, reminder idempotency, clinic-sync cursors, leases,
retries, mapping, or source-authority logic in n8n. PostgreSQL/Tia owns all of it.

## Built-in automation rules

The migration creates these rules for every existing workspace:

- booking_confirmation
- appointment_reminder_24h (legacy, disabled by v0.31.3)
- appointment_reminder_2h (legacy, disabled by v0.31.3)
- appointment_reminder_6h
- post_visit_followup
- no_show_followup

Starting in v0.31.3, the default patient-care lifecycle is:

- `appointment_reminder_6h` — one reminder before the appointment, exactly 6 hours early
- `post_visit_followup` — one check-in 24 hours after the real session completion

The legacy 24h and 2h reminder rules are disabled by the v0.31.3 migration so existing
workspaces do not continue sending the old reminders.

`booking_confirmation` and `no_show_followup` remain opt-in. Before running the automation worker, make sure:
- the WhatsApp channel connection exists,
- the patient has a WhatsApp channel identity,
- the required WhatsApp templates are approved/configured.

If templates are not approved yet, pause the automation worker or temporarily disable the two automatic rules from the Tia Automations page.

## Worker authentication

Create an Automation Worker from:

POST /api/v1/automations/workers

The API returns a `worker_token` once.

Store it inside an n8n Header Auth credential:

Header:
X-Automation-Token

Value:
<worker_token>

Never put the raw token into Git, workflow JSON, screenshots, or chat logs.

## Scheduler workflow

Import:

n8n/workflows/tia_automation_scheduler.json

Replace:

https://YOUR_TIA_BACKEND_DOMAIN

Use the Automation Worker header credential for both Tia HTTP nodes.

The workflow runs once per minute. It does not sleep until individual appointment times.
Tia plans idempotent automation jobs in PostgreSQL and only returns jobs that are due.

The same scheduler also calls `/api/v1/automations/adapter/clinic-sync/tick`.
That call is only a wake-up signal: Tia checks the durable clinic sync schedule,
claims a workspace-scoped lease, reads the current checkpoint, applies bounded
connector pages, and owns retry/backoff. Disabled/not-due/already-locked syncs
return without doing work.

## WhatsApp templates

The automation engine queues WhatsApp automation messages with:

message_type = template

and metadata:

whatsapp_template.name
whatsapp_template.language_code

Create and approve matching templates in Meta before allowing the automation worker to execute the enabled rule.

Default names:

- tia_booking_confirmation_ar
- tia_appointment_reminder_24h_ar (legacy; no longer enabled by default)
- tia_appointment_reminder_2h_ar (legacy; no longer enabled by default)
- tia_appointment_reminder_6h_ar
- tia_post_visit_followup_ar
- tia_no_show_followup_ar

The starter WhatsApp outbox workflow now sends the **exact number of positional body parameters required by each template**. Do not add unused placeholders.

Automatic patient-lifecycle contracts:

- `tia_appointment_reminder_6h_ar` — **4 parameters**:
  1. customer name
  2. service
  3. appointment time (`HH:MM`)
  4. branch / clinic name
- `tia_post_visit_followup_ar` — **3 parameters**:
  1. customer name
  2. service
  3. session date (`DD/MM/YYYY`)

Recommended natural Arabic copy:

- `tia_appointment_reminder_6h_ar`: `أهلًا {{1}} 👋 بفكرك بموعدك لـ{{2}} النهارده الساعة {{3}} في {{4}}، فاضل حوالي 6 ساعات. مستنيينك 💛`
- `tia_post_visit_followup_ar`: `إزيك {{1}}؟ حبيت أطمن عليكي بعد {{2}} اللي كانت يوم {{3}}. كل حاجة تمام؟`

The post-session follow-up intentionally does **not** mention the branch.

### Multiple approved templates with the same variables

Starting in v0.31.6, each automation rule can have a **template pool** instead of one fixed template.
Configure the primary template plus additional approved template names from the Tia **Automations** page.

Tia chooses one template deterministically from `appointment_id + rule_key`, so:

- different appointments are distributed across the available copy variants;
- retries for the same appointment always use the same template;
- no extra LLM call is needed just to vary reminder wording;
- n8n needs no routing logic for the variants because Tia sends the chosen template name in the outbox metadata.

Every template inside one pool **must use the exact same positional variable contract**. For example:

- every 6-hour reminder variant uses 4 variables: name, service, time, branch;
- every post-visit variant uses 3 variables: name, service, session date;
- the post-visit pool must not add a branch placeholder.

Example 6-hour pool: `tia_reminder_6h_01`, `tia_reminder_6h_02`, `tia_reminder_6h_03`.
Example post-visit pool: `tia_post_visit_01`, `tia_post_visit_02`, `tia_post_visit_03`.

These two rules are enabled by default in v0.31.6. The 24h and 2h reminder rules are disabled.
The post-visit rule is anchored to the appointment's real `completed_at`, so it only fires after the session is marked completed.

### AI CRM follow-ups and the 24-hour WhatsApp window

Tia creates the natural follow-up text at execution time only when the customer has messaged
within the last 24 hours. This keeps the message current and avoids an extra LLM call at task creation.

Outside WhatsApp's 24-hour customer-service window, free-form AI text is not sent. Configure one
Meta-approved template on the WhatsApp Channel connection under `config.ai_followup_template`.
The generic AI follow-up template also receives five text variables: customer name, follow-up goal,
execution date, execution time, and clinic name:

```json
{
  "ai_followup_template": {
    "name": "tia_ai_followup_ar",
    "language_code": "ar"
  }
}
```

You can set this from the Tia **Channels** page as an admin. If no approved template is configured,
the due follow-up falls back to a human CRM task instead of attempting a provider-rejected message.
Once the customer replies, the normal AI conversation continues naturally from the latest context.

## Updated WhatsApp outbox worker

Re-import/replace:

n8n/workflows/tia_whatsapp_outbox_worker.json

It now branches:

template -> parameter-count branch -> WhatsApp Send Template (3 / 4 / 5 params)
text     -> WhatsApp Send Text

Both branches report the provider result back to Tia.

## Important safety behavior

- cancelled/rescheduled appointments cancel pending reminder jobs;
- disabled rules cancel pending jobs;
- duplicate scheduler ticks do not create duplicate jobs;
- jobs with no active external channel identity are marked skipped;
- worker tokens are stored as SHA-256 hashes only;
- the 6h reminder and post-visit follow-up are intentionally enabled by default; pause the worker or disable them until their Meta templates are approved.

## v0.31.3 reminder policy

Tia sends **one appointment reminder only: قبل الموعد بـ 6 ساعات**. The legacy 24h and 2h reminder rules are disabled.
