# Tia AI Automations Engine — n8n Setup

## Architecture

PostgreSQL/Tia remains the source of truth. n8n only wakes Tia on schedule,
executes the external WhatsApp transport, and reports provider results back.

Do not put booking state, reminder eligibility, idempotency, retries, clinic-sync
cursors, mapping, or financial decisions in n8n.

## Current patient automations

The product intentionally exposes a small set of predefined automations instead
of a workflow builder:

- `booking_confirmation` — optional booking confirmation.
- `appointment_reminder_6h` — appointment reminder. The historical key is kept
  for database compatibility, but the admin now controls the timing.
- `post_visit_followup` — optional post-visit message that checks in, offers help
  or the next booking, and asks for feedback in one message.
- `no_show_followup` — optional no-show recovery message.

Only the appointment reminder is enabled by default for new workspaces. Optional
features stay opt-in and can be enabled or disabled independently by the admin.

The admin can configure reminder/follow-up timing in minutes, hours, or days from
the Automations page. Tia stores the resulting `offset_minutes` on the rule and
replans pending jobs deterministically.

Legacy 24-hour and 2-hour reminder rules may still exist in old data/history,
but they are not part of the current product UI or default rule set.

## Worker authentication

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

## WhatsApp templates

The automation engine queues proactive WhatsApp messages as Meta templates. Meta
must approve the templates before the corresponding rule is enabled in a real
runtime.

Current default template names:

- `tia_booking_confirmation_ar`
- `tia_appointment_reminder_ar`
- `tia_post_visit_followup_ar`
- `tia_no_show_followup_ar`

Template variable contracts:

- appointment reminder: customer name, service, appointment time, clinic name.
- post-visit follow-up: customer name, service, session date.
- booking/no-show templates retain the existing appointment variable contract.

The reminder copy must stay timing-neutral because the admin controls when it is
sent. Do not hardcode "6 hours" in the approved Meta template.

Recommended post-visit intent is one concise message: check how the visit went,
offer help or the next booking, and invite feedback. Do not split these into
multiple automatic messages.

## WhatsApp outbox worker

Import:

```text
n8n/workflows/tia_whatsapp_outbox_worker.json
```

It sends the exact template/text payload prepared by Tia and reports the provider
result back. Provider send nodes are single-attempt; Tia owns retry decisions to
avoid duplicate messages after ambiguous provider responses.

## Safety behavior

- cancelled/rescheduled appointments cancel pending reminders when they can still
  be safely recalled before provider send;
- changing a rule timing replans queued jobs;
- disabling a rule cancels pending jobs;
- manual cancellation stays terminal;
- duplicate scheduler ticks do not create duplicate jobs;
- proactive WhatsApp routing can use the CRM patient phone when there is exactly
  one real sendable WhatsApp connection;
- worker and channel tokens are stored hashed in Tia;
- stale/missing n8n heartbeat is surfaced to the admin.

There is no Gmail automation worker in the current product runtime.
