#!/usr/bin/env bash
set -euo pipefail

cd "$(dirname "${BASH_SOURCE[0]}")"

repo_root="$(cd ../.. && pwd)"
workflow_dir="${repo_root}/n8n/workflows"
source_name="tia_automation_scheduler.json"
source_path="${workflow_dir}/${source_name}"

if [[ ! -f "$source_path" ]]; then
  echo "Missing workflow template: $source_path" >&2
  exit 1
fi

owner_id="$(
  docker compose exec -T n8n_db \
    psql -U n8n -d n8n -Atc 'SELECT id FROM "user" WHERE email IS NOT NULL ORDER BY "createdAt" ASC LIMIT 1;' \
    | tr -d '\r\n'
)"

if [[ -z "$owner_id" ]]; then
  echo "Could not find the n8n owner account. Complete owner setup in the n8n UI first." >&2
  exit 1
fi

workflow_id="tiaAutoSched0001"
container_name="tia_automation_scheduler.import.json"
prepared_path="/tmp/${container_name}"

awk -v workflow_id="$workflow_id" '
  NR == 1 {
    print
    print "  \"id\": \"" workflow_id "\","
    next
  }
  { print }
' "$source_path" > "$prepared_path"

docker compose cp "$prepared_path" "n8n:/tmp/${container_name}"
docker compose exec -T --user node n8n \
  n8n import:workflow \
    --input="/tmp/${container_name}" \
    --userId="$owner_id"

rm -f "$prepared_path"
docker compose restart n8n >/dev/null

echo
echo "Imported Tia production scheduler only."
echo "WhatsApp inbound/outbox legacy workflows are intentionally not imported;"
echo "WhatsApp transport is owned by Tia and the Railway transport waker."
docker compose exec -T n8n_db \
  psql -U n8n -d n8n \
  -c "SELECT id, name, active FROM workflow_entity WHERE id = '${workflow_id}';"
