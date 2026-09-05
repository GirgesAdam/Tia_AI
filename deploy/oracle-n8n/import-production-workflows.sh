#!/usr/bin/env bash
set -euo pipefail

cd "$(dirname "${BASH_SOURCE[0]}")"

repo_root="$(cd ../.. && pwd)"
workflow_dir="${repo_root}/n8n/workflows"

required_files=(
  "tia_automation_scheduler.json"
  "tia_whatsapp_outbox_worker.json"
  "tia_whatsapp_inbound_status.json"
)

for file in "${required_files[@]}"; do
  if [[ ! -f "${workflow_dir}/${file}" ]]; then
    echo "Missing workflow template: ${workflow_dir}/${file}" >&2
    exit 1
  fi
done

owner_id="$(
  docker compose exec -T n8n_db \
    psql -U n8n -d n8n -Atc 'SELECT id FROM "user" WHERE email IS NOT NULL ORDER BY "createdAt" ASC LIMIT 1;' \
    | tr -d '\r\n'
)"

if [[ -z "$owner_id" ]]; then
  echo "Could not find the n8n owner account. Complete owner setup in the n8n UI first." >&2
  exit 1
fi

import_workflow() {
  local source_name="$1"
  local workflow_id="$2"
  local container_name="$3"
  local source_path="${workflow_dir}/${source_name}"
  local prepared_path="/tmp/${container_name}"

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
}

# n8n CLI imports expect workflow-level IDs. These stable IDs make repeat deploys
# update the same workflows instead of creating duplicates.
import_workflow "tia_automation_scheduler.json" "tiaAutoSched0001" "tia_automation_scheduler.import.json"
import_workflow "tia_whatsapp_outbox_worker.json" "tiaWAOutbox00001" "tia_whatsapp_outbox_worker.import.json"
import_workflow "tia_whatsapp_inbound_status.json" "tiaWAInbound0001" "tia_whatsapp_inbound_status.import.json"

docker compose restart n8n >/dev/null

echo
echo "Imported production workflows (left inactive until credentials are configured):"
docker compose exec -T n8n_db \
  psql -U n8n -d n8n \
  -c 'SELECT id, name, active FROM workflow_entity ORDER BY name;'
