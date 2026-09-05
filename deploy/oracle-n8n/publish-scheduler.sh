#!/usr/bin/env bash
set -euo pipefail

cd "$(dirname "${BASH_SOURCE[0]}")"

# Guardrail: WhatsApp transport workflows must stay unpublished until Meta
# credentials are configured and a controlled end-to-end test passes.
docker compose exec -T --user node n8n n8n unpublish:workflow --id=tiaWAInbound0001 >/dev/null || true
docker compose exec -T --user node n8n n8n unpublish:workflow --id=tiaWAOutbox00001 >/dev/null || true

# Publish only the automation + clinic sync scheduler.
docker compose exec -T --user node n8n n8n publish:workflow --id=tiaAutoSched0001

# CLI publish/unpublish writes the DB; restart is required for trigger registration.
docker compose restart n8n >/dev/null
sleep 8

echo
echo "Scheduler publish state:"
docker compose exec -T n8n_db \
  psql -U n8n -d n8n \
  -c "SELECT id, name, active FROM workflow_entity WHERE id IN ('tiaAutoSched0001','tiaWAOutbox00001','tiaWAInbound0001') ORDER BY name;"

echo
echo "n8n runtime:"
docker compose ps n8n

echo
echo "Only the scheduler should be active. WhatsApp workflows remain unpublished."
