# Tia AI Automations Engine — n8n Setup

## Architecture

PostgreSQL/Tia remains the source of truth. n8n is a shared platform scheduler only:
it wakes Tia on schedule. It does **not** hold a clinic's Meta access token, WhatsApp
credential, WABA ID, phone-number credential, booking state, reminder eligibility,
idempotency, retries, clinic-sync cursors, mapping, or financial decisions.

For the self-service WhatsApp path, Meta calls Tia's webhook directly and Tia sends
to Meta Graph API directly with the encrypted credential belonging to the correct
clinic connection. This means onboarding a new clinic does not require creating a
new n8n workflow or WhatsApp credential.

## Current patient automations

The product intentionally exposes a small set of predefined automations instead
of a workflow builder:

- `booking_confirmation` — optional booking confirmation.
- `appointment_reminder_6h` — appointment reminder. The historical key is kept
  for database compatibility, but the admin controls the timing.
- `post_visit_followup` — optional post-visit message that checks in, offers help
  or the next booking, and asks for feedback in one message.
- `cancellation_recovery` — optional recovery after a cancelled/no-show appointment.
- `lead_not_booked_followup` — optional follow-up for an interested lead that has
  not completed a booking yet.

Only the appointment reminder is enabled by default for new workspaces. Optional
features stay opt-in and can be enabled or disabled independently by the admin.

The admin can configure reminder/follow-up timing in minutes, hours, or days from
the Automations page. Tia stores the resulting `offset_minutes` on the rule and
replans pending jobs deterministically.

Legacy 24-hour, 2-hour, and standalone no-show reminder rules may still exist in
old data/history, but they are not part of the current product UI or default rule
set.

## Automation worker authentication

Create an Automation Worker from:

```text
POST /api/v1/automations/workers
```

The API returns a `worker_token` once. Store it inside an n8n Header Auth
credential:

```text
Header: X-Automation-Token
Value: <worker_token>
```

Never put the raw token into Git, workflow JSON, screenshots, or chat logs.

## Scheduler workflow

Import:

```text
n8n/workflows/tia_automation_scheduler.json
```

Set `TIA_API_BASE_URL` in the n8n environment and use the Automation Worker
header credential for the Tia HTTP nodes.

The workflow runs once per minute. It does not sleep until individual appointment
times. Tia plans idempotent jobs in PostgreSQL and returns only jobs that are due.
The same scheduler also wakes the clinic-sync runtime; the backend owns that sync
state and its retry/backoff behavior.

## WhatsApp self-service onboarding

Tia uses Meta Embedded Signup. The clinic admin is only expected to:

1. sign in to Meta;
2. choose the clinic Business and WhatsApp number;
3. complete Business Verification / Request Review if Meta explicitly requires it;
4. intervene if Meta rejects a required message template.

The clinic admin must **not** be asked to copy a WABA ID, Phone Number ID, access
token, webhook secret, n8n credential, or channel adapter token.

Tia stores the clinic Meta access token encrypted at rest in
`channel_provider_credentials`. The public channel config contains operational IDs
and health/status metadata only; it never stores the raw access token.

The Tia platform itself is configured once with:

```text
META_APP_ID
META_APP_SECRET
META_WHATSAPP_EMBEDDED_SIGNUP_CONFIG_ID
META_GRAPH_API_VERSION
META_WEBHOOK_VERIFY_TOKEN
CHANNEL_CREDENTIAL_ENCRYPTION_KEY
CHANNEL_TRANSPORT_WORKER_TOKEN
```

These are platform/operator settings, not per-clinic onboarding steps.

Meta's callback URL for inbound messages and delivery statuses is the Tia backend:

```text
GET/POST /api/v1/channels/whatsapp/webhook
```

POST webhook bodies are validated with Meta's `X-Hub-Signature-256` HMAC before
Tia accepts any event. Incoming events are resolved to the correct clinic by the
Meta `phone_number_id` already recorded during Embedded Signup.

## WhatsApp templates

The automation engine queues proactive WhatsApp messages as Meta templates. Meta
must approve the templates before the corresponding proactive template dispatch
is released.

Current default template names:

- `tia_booking_confirmation_ar`
- `tia_reminder_01`
- `tia_post_visit_01`
- `tia_cancellation_recovery_ar`

The WhatsApp transport sends the exact number of positional body parameters
required by the selected template. Current variable contracts are:

- appointment reminder — **3 parameters**: customer name, service, appointment time.
- post-visit follow-up — **3 parameters**: customer name, service, session date.
- cancellation recovery — **4 parameters**: customer name, service, cancelled/no-show
  appointment date, appointment time.
- booking confirmation retains its existing five-variable appointment contract.

The reminder copy must stay timing-neutral because the admin controls when it is
sent. Do not hardcode "6 hours" or any other delay inside the approved template.
The current single-location experience also omits branch and appointment-date
placeholders; the reminder sends only the appointment time and stays valid if the
admin changes the lead time.

Recommended natural Arabic copy:

- `tia_reminder_01`: `أهلًا {{1}} 👋 بفكرك إن عندك جلسة {{2}} الساعة {{3}}. مستنيينك 💛`
- `tia_post_visit_01`: `إزيك {{1}}؟ حبيت أطمن عليكي بعد {{2}} اللي كانت يوم {{3}}. كل حاجة تمام؟`

Tia refreshes template statuses from Meta using the clinic's encrypted credential.
If a required template is pending review, Tia waits without turning that into a
clinic-admin setup task. If Meta rejects a required template, the Setup UI surfaces
that as an admin action. Free-form customer-service replies can continue on a
healthy active connection while proactive template sends remain queued until the
required templates are approved.

The post-visit intent is intentionally one concise message: check how the visit
went, offer help or the next booking, and invite feedback. Do not split these
into multiple automatic messages.

### AI CRM follow-ups and the 24-hour WhatsApp window

Existing AI CRM follow-ups use free-form text only while WhatsApp's 24-hour
customer-service window is open. Outside that window, Tia does not try to bypass
Meta policy with free-form text.

For a CRM follow-up that needs proactive delivery outside the window, configure
one or more Meta-approved template names from the Automations page. They are
stored on the WhatsApp connection under `config.ai_followup_templates` as a list
of `{name, language_code}` objects. Tia keeps the legacy
`config.ai_followup_template` key for backward compatibility with older workers.

When more than one approved template is configured, Tia selects a stable template
for the patient/task and avoids immediately repeating the last AI follow-up
template when another approved option is available. This rotation does not add
an LLM call.

If no approved template is configured, the existing CRM follow-up path falls back
to a human CRM task rather than attempting a provider-rejected send.

This is transport safety for the existing CRM runtime; it is not a new admin task
automation feature. Do not store Meta tokens, API keys, or other secrets in the
template-name configuration.

## WhatsApp proactive-message safety

Tia stores WhatsApp opt-in separately from marketing consent. A customer inbound
WhatsApp message records the WhatsApp-contact opt-in, while staff can explicitly
record or withdraw it from the patient profile. Proactive templates and automation
sends are blocked when opt-in is missing.

Provider account-level failures such as Meta error `131031` pause only that
clinic's WhatsApp connection. The Setup UI surfaces the Meta-side action that the
clinic admin must complete. Authentication expiry/error is surfaced as a simple
"reconnect Meta" action rather than asking the clinic for a raw token. AI CRM
follow-ups fall back to staff work instead of retrying indefinitely.

Each clinic keeps its own encrypted WABA/phone credential, so a restriction on one
clinic does not stop other tenants.

## WhatsApp transport worker

Import once for the Tia platform:

```text
n8n/workflows/tia_whatsapp_outbox_worker.json
```

This shared workflow does **not** use an n8n WhatsApp node. It only wakes:

```text
POST /api/v1/channels/whatsapp/transport/tick
```

Use one platform Header Auth credential:

```text
Header: X-Tia-Transport-Token
Value: <CHANNEL_TRANSPORT_WORKER_TOKEN>
```

The backend then selects each clinic connection, decrypts that clinic's provider
credential only in memory, refreshes provider/template health, processes pending
inbound events, claims due outbox dispatches, sends directly to Meta, and records
the result through the existing dispatch state machine.

Do not create one n8n workflow or WhatsApp credential per clinic.

## Safety behavior

- cancelled/rescheduled appointments cancel pending reminders when they can still
  be safely recalled before provider send;
- no-show appointments use the same cancellation-recovery behavior instead of a
  second no-show automation;
- changing a rule timing replans queued jobs;
- disabling a rule cancels pending jobs;
- manual cancellation stays terminal;
- duplicate scheduler ticks do not create duplicate jobs;
- proactive WhatsApp routing can use the CRM patient phone when there is exactly
  one real sendable WhatsApp connection;
- provider tokens are encrypted at rest and never returned to the dashboard;
- generic adapter/worker tokens remain hashed where those legacy/provider-neutral
  paths are still used;
- permanent provider failures stop retries and surface the required action;
- stale/missing automation heartbeat is surfaced to the admin.

There is no Gmail automation worker in the current product runtime.

## Cancellation recovery

`cancellation_recovery` is an optional WhatsApp automation and is disabled by default.
The admin can enable it and choose how long after `appointments.cancelled_at` it should run.
A no-show is treated as a cancellation-recovery case using `appointments.no_show_at`.
It reuses the normal appointment automation job/outbox path; there is no separate cancellation or no-show workflow/state machine.
The Meta template is `tia_cancellation_recovery_ar` with four positional body parameters: customer name, service, original appointment date, and original appointment time.

## Lead not-booked follow-up

`lead_not_booked_followup` is optional and disabled by default. The admin chooses the delay after the lead's latest recorded contact, falling back to lead creation time.
The planner creates one idempotent system AI CRM follow-up task per lead and reuses the existing `crm_follow_up` AutomationJob runtime; there is no lead-specific job type or workflow engine.
Before sending, Tia verifies that the rule is still enabled, the lead is still `new`, `contacted`, or `qualified`, and no other active follow-up task is already handling that lead. `booked`, `won`, `lost`, and `spam` leads are not contacted by this automation.
Inside WhatsApp's 24-hour window the normal AI follow-up composer is used. Outside that window the connection-level approved `ai_followup_templates` pool applies, with legacy `ai_followup_template` compatibility.
