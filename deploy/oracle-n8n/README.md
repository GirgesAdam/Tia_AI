# Oracle n8n production runtime

This package runs only the external automation runtime on an Oracle VM:

- n8n
- a private PostgreSQL database used only by n8n
- Caddy for public HTTPS

The Tia FastAPI backend stays on Railway. Tia/PostgreSQL remains the source of truth for automation eligibility, timing, retries, booking state, CRM state, and financial logic. n8n only wakes Tia and executes external WhatsApp transport.

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

Edit `.env` and set the real n8n hostname. Generate two independent random values:

```bash
openssl rand -hex 32
openssl rand -hex 32
```

Use one for `N8N_DB_PASSWORD` and the other for `N8N_ENCRYPTION_KEY`. Never commit `.env`.

The production Tia API origin is already documented in `.env.example`:

```text
https://tia-api-production-54c5.up.railway.app
```

Before starting, run the committed validation script. It refuses to start if required values are missing or still use example placeholders:

```bash
bash ./start-production.sh
```

The script validates the Compose file, pulls the pinned images, starts the stack, and prints container status.

Manual equivalent:

```bash
docker compose config --quiet
docker compose pull
docker compose up -d
docker compose ps
```

Check logs:

```bash
docker compose logs --tail=100 n8n
docker compose logs --tail=100 caddy
```

Once DNS is resolving, Caddy obtains and renews the HTTPS certificate automatically.

## Tia runtime configuration

The package sets:

```text
TIA_API_BASE_URL=https://tia-api-production-54c5.up.railway.app
N8N_BLOCK_ENV_ACCESS_IN_NODE=false
```

The env-access setting is required because the committed Tia workflows read `TIA_API_BASE_URL` through `$env`. Keep this n8n instance dedicated to Tia and do not let untrusted users author workflows on it.

Import these workflow JSON files from `n8n/workflows/`:

- `tia_automation_scheduler.json`
- `tia_whatsapp_outbox_worker.json`
- `tia_whatsapp_inbound_status.json`

Do not publish them until the production adapter and worker credentials have been created.

## Credentials that stay only in n8n

Create credentials in the n8n UI for:

- Meta WhatsApp Business Cloud API
- `X-Channel-Token` returned by Tia channel provisioning
- `X-Automation-Token` returned by Tia worker provisioning

Never put those values in Git, `.env.example`, screenshots, or chat messages.

## First activation order

1. Keep the Tia WhatsApp connection and old worker paused.
2. Create a new production automation worker/token.
3. Configure the worker credential in n8n and publish only the scheduler.
4. Confirm the worker heartbeat becomes fresh in Tia.
5. Configure the WhatsApp credential and channel token.
6. Publish inbound/status and outbox workflows.
7. Send the first provider test only to a WhatsApp number you control.
8. Confirm `sent`, `delivered`, and inbound reply handling before enabling patient-facing optional automations.

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

This keeps the Oracle runtime aligned with the same production branch as the application source.

## Backups

The n8n PostgreSQL database contains workflow state and encrypted credentials. The encryption key is required to decrypt those credentials, so protect both.

Example database backup:

```bash
mkdir -p backups
docker compose exec -T n8n_db pg_dump -U n8n n8n > "backups/n8n-$(date +%F-%H%M).sql"
```

Copy backups off the VM. Keep `N8N_ENCRYPTION_KEY` in a separate secure password manager or secret store; do not store it inside the database backup.

## Updating n8n

The image is intentionally pinned rather than using `latest`. Review n8n release notes and security advisories before changing the version in `docker-compose.yml`, then:

```bash
docker compose pull
docker compose up -d
```

After updates, verify the three Tia workflows and run the n8n security audit:

```bash
docker compose exec n8n n8n audit
```
