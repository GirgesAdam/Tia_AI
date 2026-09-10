#!/usr/bin/env bash
set -euo pipefail

cd "$(dirname "${BASH_SOURCE[0]}")"

N8N_HOST_VALUE="$(sed -n 's/^N8N_HOST=//p' .env 2>/dev/null | head -1)"
if [[ -z "$N8N_HOST_VALUE" ]]; then
  echo "N8N_HOST is missing from .env" >&2
  exit 1
fi

RECOVERED=0

service_running() {
  local service="$1"
  local cid
  cid="$(docker compose ps -q "$service" 2>/dev/null || true)"
  [[ -n "$cid" ]] && [[ "$(docker inspect -f '{{.State.Running}}' "$cid" 2>/dev/null || true)" == "true" ]]
}

recover_stack() {
  echo "One or more production containers are down; reconciling Docker Compose stack..."
  docker compose up -d n8n_db n8n caddy
  RECOVERED=1
}

workflow_counts() {
  docker compose exec -T n8n_db psql -U n8n -d n8n -Atc "
    SELECT
      (SELECT count(*) FROM workflow_entity WHERE id = 'tiaAutoSched0001' AND active IS TRUE),
      (SELECT count(*) FROM workflow_entity
         WHERE active IS TRUE
           AND (
             id IN ('tiaWAInbound0001','tiaWAOutbox00001')
             OR CAST(nodes AS text) LIKE '%/adapter/outbox/claim%'
             OR CAST(nodes AS text) LIKE '%/adapter/outbox/provider-status%'
             OR CAST(nodes AS text) LIKE '%/channels/adapter/inbound%'
           ));
  " | tr -d '\r'
}

if ! service_running n8n_db || ! service_running n8n || ! service_running caddy; then
  recover_stack
fi

for _ in $(seq 1 20); do
  if docker compose exec -T n8n_db pg_isready -U n8n -d n8n >/dev/null 2>&1; then
    break
  fi
  sleep 1
done

if ! docker compose exec -T n8n_db pg_isready -U n8n -d n8n >/dev/null 2>&1; then
  echo "PostgreSQL is not ready after recovery attempt." >&2
  exit 1
fi

IFS='|' read -r SCHEDULER_ACTIVE_COUNT LEGACY_ACTIVE_COUNT <<< "$(workflow_counts)"
if [[ "$SCHEDULER_ACTIVE_COUNT" -ne 1 || "$LEGACY_ACTIVE_COUNT" -ne 0 ]]; then
  echo "Workflow state drift detected (scheduler=$SCHEDULER_ACTIVE_COUNT, retired_whatsapp=$LEGACY_ACTIVE_COUNT); applying scheduler-only guardrail..."
  if bash ./publish-scheduler.sh >/dev/null; then
    RECOVERED=1
    IFS='|' read -r SCHEDULER_ACTIVE_COUNT LEGACY_ACTIVE_COUNT <<< "$(workflow_counts)"
  fi
fi

if [[ "$SCHEDULER_ACTIVE_COUNT" -ne 1 ]]; then
  echo "Expected the Tia automation scheduler to be active; found $SCHEDULER_ACTIVE_COUNT." >&2
  exit 1
fi
if [[ "$LEGACY_ACTIVE_COUNT" -ne 0 ]]; then
  echo "Retired Oracle WhatsApp adapter workflows are still active: $LEGACY_ACTIVE_COUNT." >&2
  exit 1
fi

DISK_USED_PERCENT="$(df -P / | awk 'NR==2 {gsub("%", "", $5); print $5}')"
if [[ ! "$DISK_USED_PERCENT" =~ ^[0-9]+$ ]]; then
  echo "Could not determine root disk usage." >&2
  exit 1
fi
if (( DISK_USED_PERCENT >= 90 )); then
  echo "Root disk usage is critically high: ${DISK_USED_PERCENT}%" >&2
  exit 1
elif (( DISK_USED_PERCENT >= 80 )); then
  echo "WARNING: root disk usage is ${DISK_USED_PERCENT}%"
fi

# Use n8n's dedicated readiness endpoint, which verifies the app is ready and
# its database is connected/migrated. The editor root URL is not a health probe.
READY_URL="https://$N8N_HOST_VALUE/healthz/readiness"
if ! curl -fsS --max-time 15 "$READY_URL" >/dev/null; then
  echo "n8n readiness endpoint is unavailable; restarting n8n and Caddy once..."
  docker compose restart n8n caddy >/dev/null
  RECOVERED=1
  sleep 10
  if ! curl -fsS --max-time 15 "$READY_URL" >/dev/null; then
    echo "n8n readiness endpoint is still unavailable after restart." >&2
    exit 1
  fi
fi

if [[ "$RECOVERED" -eq 1 ]]; then
  echo "Health check passed after automatic recovery."
else
  echo "Health check passed."
fi

echo "PostgreSQL: ready"
echo "n8n: ready"
echo "Caddy: running"
echo "Tia scheduler active: $SCHEDULER_ACTIVE_COUNT/1"
echo "Retired WhatsApp workflows active: $LEGACY_ACTIVE_COUNT"
echo "Disk used: ${DISK_USED_PERCENT}%"
echo "n8n readiness: $READY_URL OK"
