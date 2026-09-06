#!/usr/bin/env bash
set -euo pipefail

cd "$(dirname "${BASH_SOURCE[0]}")"

INBOUND_ID="tiaWAInbound0001"
OUTBOX_ID="tiaWAOutbox00001"
SCHEDULER_ID="tiaAutoSched0001"

# Safety guardrail: never publish outbound messaging during inbound setup.
docker compose exec -T --user node n8n \
  n8n unpublish:workflow --id="$OUTBOX_ID" >/dev/null || true

# Publish the inbound/status workflow. The WhatsApp Trigger will register its
# webhook subscription with Meta when n8n activates the workflow.
docker compose exec -T --user node n8n \
  n8n publish:workflow --id="$INBOUND_ID"

# n8n CLI writes publication state to the database; restart is required so
# the running process registers the trigger with the final webhook URL.
docker compose restart n8n >/dev/null
sleep 10

echo
echo "Workflow publish state:"
docker compose exec -T n8n_db \
  psql -U n8n -d n8n \
  -c "SELECT id, name, active FROM workflow_entity WHERE id IN ('${SCHEDULER_ID}','${INBOUND_ID}','${OUTBOX_ID}') ORDER BY name;"

echo
echo "Recent n8n activation logs:"
docker compose logs --since=90s n8n 2>&1 \
  | grep -Ei 'WhatsApp|Tia v0\.18|Activated workflow|activation|webhook|error|failed' \
  | tail -80 || true

echo
echo "Expected state: scheduler=active, inbound=active, outbox=inactive."
echo "Do not publish the outbox until a controlled inbound test succeeds."
