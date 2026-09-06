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

if ! service_running n8n_db || ! service_running n8n || ! service_running caddy; then
  recover_stack
fi

# Wait briefly for Postgres after a VM/container restart.
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

# Verify the three required production workflows are still active.
ACTIVE_TIA_COUNT="$(docker compose exec -T n8n_db psql -U n8n -d n8n -Atc "SELECT count(*) FROM workflow_entity WHERE id IN ('tiaAutoSched0001','tiaWAInbound0001','tiaWAOutbox00001') AND active = true;")"
if [[ "$ACTIVE_TIA_COUNT" -ne 3 ]]; then
  echo "Expected 3 active Tia production workflows; found $ACTIVE_TIA_COUNT." >&2
  exit 1
fi

# Guard against disk exhaustion. 80% is a warning; 90% makes the health check fail
# so the issue is visible in systemd/journal before PostgreSQL or Docker run out of space.
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

# Check the public n8n endpoint. If containers are running but the endpoint is
# unavailable, restart only n8n + Caddy once, then retry. This does not touch DB data.
if ! curl -fsS --max-time 15 "https://$N8N_HOST_VALUE/" >/dev/null; then
  echo "Public n8n endpoint is unavailable; restarting n8n and Caddy once..."
  docker compose restart n8n caddy >/dev/null
  RECOVERED=1
  sleep 8
  if ! curl -fsS --max-time 15 "https://$N8N_HOST_VALUE/" >/dev/null; then
    echo "Public n8n endpoint is still unavailable after restart." >&2
    exit 1
  fi
fi

if [[ "$RECOVERED" -eq 1 ]]; then
  echo "Health check passed after automatic recovery."
else
  echo "Health check passed."
fi

echo "PostgreSQL: ready"
echo "n8n: running"
echo "Caddy: running"
echo "Active Tia workflows: $ACTIVE_TIA_COUNT/3"
echo "Disk used: ${DISK_USED_PERCENT}%"
echo "HTTPS: https://$N8N_HOST_VALUE/ OK"
