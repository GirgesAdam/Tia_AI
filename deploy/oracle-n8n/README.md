# Oracle n8n production runtime

This package runs the external automation scheduler on an Oracle VM:

- n8n
- a private PostgreSQL database used only by n8n
- Caddy for public HTTPS

The Tia FastAPI backend stays on Railway. Tia/PostgreSQL remains the source of truth for automation eligibility, timing, retries, booking state, CRM state, clinic-sync checkpoints, and financial logic.

WhatsApp transport is **not** owned by Oracle n8n anymore. Meta webhooks go directly to Tia, and Tia sends directly to Meta using encrypted per-clinic credentials. The Railway service `tia-whatsapp-transport-waker` wakes that native transport.

## Before you start

1. Create an Oracle ARM64 Ubuntu LTS VM.
2. Point a DNS A record such as `automation.example.com` to the VM public IPv4 address.
3. Allow inbound TCP 80 and 443. Restrict SSH 22 to your own IP where possible.
4. Do not expose ports 5432 or 5678 publicly.

## Install and start

Install Docker Engine and the Docker Compose plugin on the VM, then clone the Tia repository from the production branch:

```bash
git clone https://github.com/GirgesAdam/Tia_AI.git
cd Tia_AI
git checkout main
cd deploy/oracle-n8n
cp .env.example .env
```

Edit `.env` and set the real n8n hostname. Generate two independent random values for the local n8n database password and encryption key:

```bash
openssl rand -hex 32
openssl rand -hex 32
```

Never commit `.env`.

Start the stack:

```bash
bash ./start-production.sh
```

Manual equivalent:

```bash
docker compose config --quiet
docker compose pull
docker compose up -d
docker compose ps
```

## Active Tia workflow on Oracle

Only this workflow should be active for the current production architecture:

```text
n8n/workflows/tia_automation_scheduler.json
```

It wakes Tia once per minute for:

- reminder / CRM automation planning and execution;
- connector-driven clinic-sync ticks.

It does not receive patient WhatsApp webhooks and does not send provider messages.

Use an n8n HTTP Header Auth credential containing the one-time Tia automation worker token:

```text
Header: X-Automation-Token
Value: <worker_token>
```

Never put that token in Git, workflow JSON, screenshots, or chat logs.

## WhatsApp is native to Tia

Current production path:

```text
Customer WhatsApp
→ Meta webhook
→ Tia /api/v1/channels/whatsapp/webhook/{connection_id}
→ CRM / AI / Booking / Handoff
→ Tia message_dispatches
→ Tia native Meta transport
→ Meta Graph API
→ Meta delivery/status webhook
→ Tia channel_delivery_events
```

The Railway service `tia-whatsapp-transport-waker` calls:

```text
POST /api/v1/channels/whatsapp/transport/tick
```

using the platform transport token. Clinic Meta credentials stay encrypted in Tia and are never stored in Oracle n8n.

`n8n/workflows/tia_whatsapp_outbox_worker.json` remains only a compatible alternate/reference waker for development or recovery. Do not activate it in production while the Railway waker is active.

## Retired Oracle WhatsApp workflows

Any previously imported Oracle workflow that does one of the following must remain disabled:

- receives patient WhatsApp webhooks inside n8n;
- posts inbound messages to the generic Tia channel adapter;
- claims the generic Tia channel outbox;
- sends through n8n WhatsApp provider nodes;
- reports provider delivery state back through the old adapter.

Do not repair old `X-Channel-Token` authentication to keep these workflows alive. They are superseded by Tia's native Meta transport.

## Import / wire scheduler

`import-production-workflows.sh` and `wire-tia-runtime.sh` now prepare only `tia_automation_scheduler.json`.

Generate the scheduler token file with:

```bash
bash ./generate-runtime-tokens.sh
```

Then wire/import the scheduler and configure its `X-Automation-Token` credential without printing the raw token.

## Production update procedure

After changes are merged to `main`:

```bash
cd ~/Tia_AI
git fetch origin
git checkout main
git pull --ff-only origin main
cd deploy/oracle-n8n
bash ./start-production.sh
```

After updating, verify that the scheduler is active and retired WhatsApp workflows remain inactive.

## Backups

The n8n PostgreSQL database contains workflow state and encrypted credentials. Protect both the database backup and `N8N_ENCRYPTION_KEY`.

Example backup:

```bash
mkdir -p backups
docker compose exec -T n8n_db pg_dump -U n8n n8n > "backups/n8n-$(date +%F-%H%M).sql"
```

Copy backups off the VM.

## Runtime verification

1. Confirm Oracle n8n and Caddy are healthy.
2. Confirm `tia_automation_scheduler.json` has a fresh worker heartbeat in Tia.
3. Confirm Railway `tia-whatsapp-transport-waker` logs return HTTP 200 from the native transport tick.
4. Confirm no Oracle n8n workflow is repeatedly calling a retired generic channel-adapter outbox endpoint.
5. Test real provider traffic only with a phone number you control.
