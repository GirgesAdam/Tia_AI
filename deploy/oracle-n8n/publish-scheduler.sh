#!/usr/bin/env bash
set -euo pipefail

cd "$(dirname "${BASH_SOURCE[0]}")"

# Unpublish stable legacy workflow IDs when they still exist.
docker compose exec -T --user node n8n n8n unpublish:workflow --id=tiaWAInbound0001 >/dev/null 2>&1 || true
docker compose exec -T --user node n8n n8n unpublish:workflow --id=tiaWAOutbox00001 >/dev/null 2>&1 || true

# Some historical workflows may have been imported manually and therefore have
# different IDs. Discover only active workflows whose stored node graph still
# contains a retired channel-adapter WhatsApp path, then unpublish those IDs.
mapfile -t legacy_ids < <(
  docker compose exec -T n8n_db \
    psql -U n8n -d n8n -Atc \
    "SELECT id FROM workflow_entity WHERE active IS TRUE AND (CAST(nodes AS text) LIKE '%/adapter/outbox/claim%' OR CAST(nodes AS text) LIKE '%/adapter/outbox/provider-status%' OR CAST(nodes AS text) LIKE '%/channels/adapter/inbound%');" \
    | tr -d '\r'
)

for workflow_id in "${legacy_ids[@]}"; do
  [[ -n "$workflow_id" ]] || continue
  echo "Unpublishing retired WhatsApp workflow: $workflow_id"
  docker compose exec -T --user node n8n \
    n8n unpublish:workflow --id="$workflow_id" >/dev/null
 done

# Publish only the automation + clinic-sync scheduler.
docker compose exec -T --user node n8n n8n publish:workflow --id=tiaAutoSched0001

# CLI publish/unpublish writes the DB; restart is required for trigger registration.
docker compose restart n8n >/dev/null
sleep 8

echo
echo "Active Tia-related workflows after cleanup:"
docker compose exec -T n8n_db \
  psql -U n8n -d n8n \
  -c "SELECT id, name, active FROM workflow_entity WHERE id = 'tiaAutoSched0001' OR CAST(nodes AS text) LIKE '%TIA_API_BASE_URL%' ORDER BY active DESC, name;"

echo
echo "n8n runtime:"
docker compose ps n8n

echo
echo "The automation scheduler should be active. Retired WhatsApp adapter workflows must be inactive."
