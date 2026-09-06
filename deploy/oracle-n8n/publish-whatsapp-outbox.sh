#!/usr/bin/env bash
set -euo pipefail

cd "$(dirname "${BASH_SOURCE[0]}")"

# Keep result recording deterministic before publishing. This preserves the
# already-configured Meta credentials by repairing the exported live workflow.
bash ./repair-whatsapp-outbox-results.sh

# Controlled rollout: inbound has already passed an end-to-end test.
docker compose exec -T --user node n8n n8n publish:workflow --id=tiaWAOutbox00001

# Ensure scheduler and inbound remain published.
docker compose exec -T --user node n8n n8n publish:workflow --id=tiaAutoSched0001 >/dev/null
docker compose exec -T --user node n8n n8n publish:workflow --id=tiaWAInbound0001 >/dev/null

# CLI publish writes the DB; restart is required for trigger registration.
docker compose restart n8n >/dev/null
sleep 8

echo
echo "Workflow publish state:"
docker compose exec -T n8n_db \
  psql -U n8n -d n8n \
  -c "SELECT id, name, active FROM workflow_entity WHERE id IN ('tiaAutoSched0001','tiaWAOutbox00001','tiaWAInbound0001') ORDER BY name;"

echo
echo "Recent n8n logs:"
docker compose logs --since=2m n8n | tail -60

echo
echo "Expected state: scheduler=active, inbound=active, outbox=active."
