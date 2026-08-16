# Tia AI v0.18.0 — Real n8n Runtime

Tia/PostgreSQL remains the system of record. n8n owns external credentials and
transport execution only.

## Workflows

Import these four workflows:

- `tia_whatsapp_inbound_status.json`
- `tia_whatsapp_outbox_worker.json`
- `tia_automation_scheduler.json`
- `tia_gmail_outbox_worker.json`

Replace `https://YOUR_TIA_BACKEND_DOMAIN` with the public HTTPS FastAPI URL in
every Tia HTTP Request node.

## Credentials kept in n8n, never in Tia DB

### WhatsApp inbound trigger

Use the n8n WhatsApp Trigger credential required by the trigger node.

### WhatsApp send

Use an n8n WhatsApp Business Cloud API credential on both WhatsApp send nodes.

### Gmail send

Use a Gmail OAuth2 credential on `Gmail Send Message`. The connected Google
account must match the sender email provisioned in Tia.

### Tia channel adapters

For each real channel connection, create an n8n HTTP Header Auth credential:

- Header name: `X-Channel-Token`
- Header value: the one-time token printed by the Tia provision script

A WhatsApp connection and a Gmail connection have different channel tokens.
Use the appropriate credential in that channel's workflow.

### Automation scheduler

Create an n8n HTTP Header Auth credential:

- Header name: `X-Automation-Token`
- Header value: the one-time token printed by `provision_n8n_automation_worker.py`

## Provision real runtime records

From `backend/`:

```powershell
python scripts/provision_whatsapp_channel.py --workspace-id YOUR_WORKSPACE_ID --phone-number-id YOUR_META_PHONE_NUMBER_ID --display-name "Clinic WhatsApp" --waba-id YOUR_WABA_ID --business-phone "+20..."
```

```powershell
python scripts/provision_gmail_channel.py --workspace-id YOUR_WORKSPACE_ID --sender-email clinic@example.com --display-name "Clinic Gmail"
```

```powershell
python scripts/provision_n8n_automation_worker.py --workspace-id YOUR_WORKSPACE_ID --name "Tia n8n Runtime"
```

Each command prints a raw adapter/worker token once. Put it straight into n8n's
credential store. Do not paste it into workflow JSON, Git, screenshots, or chat.

## WhatsApp execution path

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

The inbound event ID and provider message IDs are used for idempotency. A fast
Meta delivery callback can arrive before the send result; Tia persists the
callback and reconciles it after the provider message ID is known.

## Gmail execution path

```text
Customer asks: "ابعتلي التفاصيل على الإيميل"
→ semantic capability: email_communication
→ send_email_to_customer
→ saved patient.email only
→ Message + MessageDispatch(status=queued)
→ n8n Gmail outbox worker
→ Gmail Send Message
→ Tia dispatch result
```

The AI tool cannot accept a recipient address. It can only use the current
patient's saved CRM email, preventing the customer-facing agent from becoming an
arbitrary mail relay.

A successful tool call means durable queueing, not confirmed Gmail delivery.
The customer-facing agent is instructed not to claim the email was delivered.

## Automation scheduler

`tia_automation_scheduler.json` runs once per minute. Tia plans and claims jobs
in PostgreSQL; n8n does not decide whether reminders are due or already sent.

The worker token heartbeat is updated by authenticated scheduler calls. Runtime
rules plus no recent worker heartbeat remain a Production Readiness failure.

## Retry policy

Transport nodes and Tia HTTP nodes use bounded n8n node retries. If Gmail or
WhatsApp still fails, the workflow reports `failed` with `retry_after_seconds`
to Tia. Tia returns the dispatch to `queued` with `next_attempt_at`, preserving
its database outbox/reclaim semantics.

## Staging vs real runtime

Connections marked `staging_mock`, `mock=true`, `do_not_send=true`, or without
`runtime_kind=real` no longer satisfy the Production Readiness external-channel
check.

This prevents the seeded regression WhatsApp connection from looking like a
real integration.

## First live test order

1. Import/publish the automation scheduler and confirm its real worker heartbeat.
2. Provision/import Gmail and send one email to a staging patient you control.
3. Provision/import WhatsApp and send a staging WhatsApp text from a phone you control.
4. Verify Tia outbound `sent`, then Meta `delivered/read` callbacks.
5. Enable one approved automation rule and verify a real reminder end-to-end.

Do not use real patient contact data for the first live tests.
