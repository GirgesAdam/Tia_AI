# Tia AI Automations Engine — n8n Setup

Version: 0.10.0

## Architecture

PostgreSQL/Tia remains the source of truth.

n8n only:
1. wakes up on a schedule,
2. asks Tia to plan + claim due jobs,
3. asks Tia to execute each claimed job,
4. lets the existing WhatsApp outbox worker deliver queued messages.

Do not put booking state or "has this reminder already been sent?" logic in n8n.

## Built-in automation rules

The migration creates these rules for every existing workspace:

- booking_confirmation
- appointment_reminder_24h
- appointment_reminder_2h
- post_visit_followup
- no_show_followup

They are intentionally DISABLED by default.

Enable them only after:
- the WhatsApp channel connection exists,
- the patient has a WhatsApp channel identity,
- the required WhatsApp templates are approved/configured.

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
Tia plans idempotent jobs in PostgreSQL and only returns jobs that are due.

## WhatsApp templates

The automation engine queues WhatsApp automation messages with:

message_type = template

and metadata:

whatsapp_template.name
whatsapp_template.language_code

Create and approve matching templates in Meta before enabling each rule.

Default names:

- tia_booking_confirmation_ar
- tia_appointment_reminder_24h_ar
- tia_appointment_reminder_2h_ar
- tia_post_visit_followup_ar
- tia_no_show_followup_ar

The starter workflow expects parameterless templates.
Keep the first versions generic and let the customer reply "تفاصيل", "تأكيد", "تعديل", or "حجز";
the Tia agent can then read the real appointment from PostgreSQL.

## Updated WhatsApp outbox worker

Re-import/replace:

n8n/workflows/tia_whatsapp_outbox_worker.json

It now branches:

template -> WhatsApp Send Template
text     -> WhatsApp Send Text

Both branches report the provider result back to Tia.

## Important safety behavior

- cancelled/rescheduled appointments cancel pending reminder jobs;
- disabled rules cancel pending jobs;
- duplicate scheduler ticks do not create duplicate jobs;
- jobs with no active external channel identity are marked skipped;
- worker tokens are stored as SHA-256 hashes only;
- rule defaults are disabled so deploying the migration cannot accidentally message patients.
