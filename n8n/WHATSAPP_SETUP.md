# Tia AI — WhatsApp Business Cloud + n8n Bridge

This bridge connects real WhatsApp conversations to Tia AI without making n8n the system of record.
PostgreSQL/Tia AI remains authoritative for patients, conversations, messages, bookings, handoffs, and delivery state.

## Architecture

```text
WhatsApp Business Cloud
        |
        v
n8n WhatsApp Trigger
        |
        v
Tia /channels/adapter/inbound
        |
        v
Tia AI + CRM + Booking + Handoff
        |
        v
Tia message_dispatches outbox
        |
        v
n8n Outbox Worker
        |
        v
WhatsApp Business Cloud
        |
        v
sent / delivered / read / failed callbacks
        |
        v
Tia channel_delivery_events
```

n8n holds the Meta credentials. Tia stores only non-secret account metadata plus a SHA-256 hash of the Tia adapter token.

## What you need from Meta/n8n

Create/configure a Meta Business app with the WhatsApp product. In n8n you will use two credential types:

1. **WhatsApp OAuth credential** for the **WhatsApp Trigger** node.
2. **WhatsApp Business Cloud API credential** for the **WhatsApp Business Cloud** send node. It uses the Meta API access token and WhatsApp Business Account ID.

Do not put Meta access tokens, app secrets, passwords, or Tia adapter tokens inside `channel_connections.config`.

## 1. Apply the database migration

From `backend/`:

```powershell
alembic upgrade head
```

Expected head:

```text
0010_whatsapp_n8n_bridge (head)
```

## 2. Provision the WhatsApp connection in Tia

Get the **Phone Number ID** from Meta WhatsApp API Setup. This is an internal numeric Meta ID, not the visible `+20...` phone number.

Run from `backend/`:

```powershell
python scripts/provision_whatsapp_channel.py --workspace-id YOUR_WORKSPACE_ID --phone-number-id YOUR_META_PHONE_NUMBER_ID --display-name "Tia WhatsApp" --waba-id YOUR_WABA_ID --business-phone "+20XXXXXXXXXX"
```

The command prints:

```text
connection_id=...
adapter_token=tia_ch_...
```

Store the `adapter_token` immediately. Tia stores only its hash and cannot show the same token again.

## 3. Create the Tia Header Auth credential in n8n

In n8n create an **HTTP Header Auth** credential:

```text
Name: Tia Channel Adapter
Header Name: X-Channel-Token
Header Value: tia_ch_...
```

Use the token printed by the provisioning script.

## 4. Import the inbound/status workflow

Import:

```text
n8n/workflows/tia_whatsapp_inbound_status.json
```

Then:

1. Open every Tia HTTP Request node and replace `https://YOUR_TIA_BACKEND_DOMAIN` with the public HTTPS URL of the FastAPI backend.
2. Select the `Tia Channel Adapter` Header Auth credential on those HTTP nodes.
3. Select your **WhatsApp OAuth** credential on `WhatsApp Trigger`.
4. Publish the workflow.

The normalization node currently accepts **text WhatsApp messages**. Media support is intentionally deferred to the media milestone instead of pretending a non-text message is text.

The same workflow also forwards WhatsApp `sent`, `delivered`, `read`, and `failed` callbacks to Tia.

## 5. Import the outbox worker

Import:

```text
n8n/workflows/tia_whatsapp_outbox_worker.json
```

Then:

1. Replace `https://YOUR_TIA_BACKEND_DOMAIN` in all Tia HTTP Request nodes.
2. Select the `Tia Channel Adapter` Header Auth credential on those HTTP nodes.
3. Select the **WhatsApp Business Cloud API** credential on `WhatsApp Business Cloud`.
4. Publish the workflow.

The worker runs every 5 seconds, claims queued Tia dispatches, sends them through WhatsApp, and reports either `sent` or a retryable failure back to Tia.

The Phone Number ID used for sending comes from each Tia channel connection (`external_account_id`), so the workflow does not hard-code one clinic's number.

## Delivery callback race protection

WhatsApp can report `sent`/`delivered` very quickly. A callback can theoretically arrive before n8n reports the provider message ID back to the outbox row.

Tia therefore stores callbacks in `channel_delivery_events` even when a matching dispatch is not known yet. When the outbound result later supplies the provider message ID, pending callbacks are reconciled automatically.

This prevents losing fast delivery/read receipts.

## Webhook testing note

Do not keep switching a live WhatsApp app between n8n's test and production trigger URLs. Use the production/published n8n workflow for staging traffic once the Meta app is subscribed.

## Security rules

- Never commit Meta access tokens or Tia adapter tokens to Git.
- Keep Meta credentials inside n8n's credential store.
- Keep the Tia adapter token in n8n Header Auth credentials.
- Use HTTPS for the public Tia backend and n8n webhook endpoints.
- Rotate the Tia adapter token if it is exposed by rerunning `provision_whatsapp_channel.py` for the same Phone Number ID.
- Production and staging should use separate Meta/n8n/Tia connections.

## End-to-end path to test later

```text
Customer sends WhatsApp text
→ n8n receives it
→ Tia creates/resolves patient identity
→ Tia stores inbound message
→ Tia AI processes it
→ Tia queues outbound reply
→ n8n sends reply to WhatsApp
→ Meta returns message ID
→ Tia marks sent
→ WhatsApp delivery callback arrives
→ Tia marks delivered/read
```

Human handoff uses the same outbound pipeline: a staff reply from Team Inbox is queued into `message_dispatches`, then the same n8n worker delivers it to WhatsApp.
