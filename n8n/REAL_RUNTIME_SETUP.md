# Tia AI — Real n8n Runtime

Tia/PostgreSQL remains the system of record. n8n owns external credentials and
transport execution only. It must not own booking state, sync checkpoints,
identity resolution, source authority, retries, or financial decisions.

Patient communication in the current product contract is WhatsApp-based. There
is no Gmail automation runtime in the project.

The production FastAPI backend currently runs at:

```text
https://tia-api-production-54c5.up.railway.app
```

The lightweight Oracle deployment package for the always-on automation runtime
is in `deploy/oracle-n8n/`. It runs n8n, a PostgreSQL database used only by n8n,
and Caddy for HTTPS. FastAPI stays on Railway and is not duplicated on the VM.

## Active workflows

Import these three workflows:

- `tia_whatsapp_inbound_status.json`
- `tia_whatsapp_outbox_worker.json`
- `tia_automation_scheduler.json`

Set these environment variables on the self-hosted n8n runtime:

```text
TIA_API_BASE_URL=https://tia-api-production-54c5.up.railway.app
N8N_BLOCK_ENV_ACCESS_IN_NODE=false
```

Use the public HTTPS FastAPI origin only, with no trailing slash. All active Tia
HTTP Request nodes read `TIA_API_BASE_URL` at runtime. Recent n8n versions can
block `$env` access in expressions, so the dedicated Tia n8n runtime must allow
environment access with `N8N_BLOCK_ENV_ACCESS_IN_NODE=false`. Do not use this
setting on a shared/untrusted n8n instance where arbitrary workflow authors can
read process environment variables.

For local Docker development the workflow JSON keeps
`http://host.docker.internal:8000` as a fallback, so no URL editing is required
when switching between local and hosted environments.

## Credentials kept in n8n

### WhatsApp inbound

Use the n8n WhatsApp Trigger credential required by the trigger node.

### WhatsApp send

Use an n8n WhatsApp Business Cloud API credential on the WhatsApp send nodes.

### Tia channel adapter

Create an n8n HTTP Header Auth credential for the WhatsApp channel connection:

- Header: `X-Channel-Token`
- Value: the one-time token returned by Tia provisioning.

### Automation + clinic-sync scheduler

Create an n8n HTTP Header Auth credential:

- Header: `X-Automation-Token`
- Value: the one-time worker token returned by Tia provisioning.

Never put raw adapter/worker tokens in Git, workflow JSON, screenshots, or chat
logs.

## Provision runtime records

From `backend/`:

```powershell
python scripts/provision_whatsapp_channel.py --workspace-id YOUR_WORKSPACE_ID --phone-number-id YOUR_META_PHONE_NUMBER_ID --display-name "Clinic WhatsApp" --waba-id YOUR_WABA_ID --business-phone "+20..."
python scripts/provision_n8n_automation_worker.py --workspace-id YOUR_WORKSPACE_ID --name "Tia n8n Runtime"
```

Do not reuse the paused staging worker token or a demo channel token in
production. Provision a new worker token and a production channel token, then
store their plaintext values only in n8n credentials.

## WhatsApp path

```text
Customer WhatsApp
→ n8n WhatsApp Trigger
→ Tia normalized inbound
→ CRM / AI / Booking / Handoff
→ Tia message_dispatches
→ n8n WhatsApp outbox worker
→ Meta send
→ Tia dispatch result
→ Meta sent/delivered/read/failed webhook
→ Tia channel_delivery_events
```

Inbound event IDs and provider message IDs are used for idempotency. Tia owns
outbox/retry state and reconciles delivery callbacks in PostgreSQL.

## Automation + incremental clinic sync

`tia_automation_scheduler.json` wakes Tia once per minute on two independent
branches using the same `X-Automation-Token`:

1. automation planning/claiming for reminders and CRM jobs;
2. connector-driven incremental clinic sync via
   `/api/v1/automations/adapter/clinic-sync/tick`.

Automation enable/disable state and admin-selected timing live in Tia/PostgreSQL.
n8n does not own separate per-rule schedules; it only wakes the backend and
executes the WhatsApp transport for jobs that Tia has already validated as due.

The clinic-sync call is only a wake-up signal. The backend decides whether the
workspace is enabled, due, already leased, or temporarily backed off. It then
owns the deterministic sync runtime and durable checkpoints.

## Retry policy

n8n may retry idempotent Tia HTTP requests, but provider send nodes must not be
blindly retried. Tia remains responsible for business retries, outbox reclaim,
sync leases, checkpoints, and scheduler backoff. This avoids duplicate WhatsApp
messages when a provider response is ambiguous.

## Production safety state before n8n activation

Keep the real WhatsApp connection paused and the old n8n worker paused until the
new production n8n instance is online and has fresh credentials. This prevents a
partially configured runtime from sending messages.

Connections marked `staging_mock`, `mock=true`, `do_not_send=true`, or without
`runtime_kind=real` do not satisfy the Production Readiness external-channel
check.

## First live test order

1. Start the Oracle n8n package and confirm HTTPS.
2. Provision a new automation worker and configure `X-Automation-Token` in n8n.
3. Import/publish only the automation scheduler and confirm a fresh worker heartbeat.
4. Provision/configure the production WhatsApp channel token and Meta credential.
5. Publish inbound/status and outbox workflows.
6. Send the first provider test only to a phone number you control.
7. Verify Tia outbound `sent`, then Meta `delivered/read` callbacks and an inbound reply.
8. Enable one approved automation rule and verify a real reminder end-to-end.
9. Configure an external clinic connector only when a real clinic integration is ready.
