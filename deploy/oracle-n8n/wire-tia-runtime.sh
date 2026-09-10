#!/usr/bin/env bash
set -euo pipefail

cd "$(dirname "${BASH_SOURCE[0]}")"

repo_root="$(cd ../.. && pwd)"
workflow_dir="${repo_root}/n8n/workflows"
secrets_file=".runtime-secrets/tia-runtime.env"

if [[ ! -f "$secrets_file" ]]; then
  echo "Missing $secrets_file. Generate the Oracle runtime token first." >&2
  exit 1
fi

if [[ "$(stat -c '%a' "$secrets_file")" != "600" ]]; then
  echo "Refusing to continue: $secrets_file must have permissions 600." >&2
  exit 1
fi

if ! command -v python3 >/dev/null 2>&1; then
  echo "python3 is required on the Oracle host." >&2
  exit 1
fi

# Recreate n8n so Docker Compose loads the local runtime-token env file.
docker compose up -d --force-recreate n8n >/dev/null

docker compose exec -T n8n sh -lc 'test -n "$TIA_AUTOMATION_TOKEN"' || {
  echo "n8n did not receive TIA_AUTOMATION_TOKEN." >&2
  exit 1
}

owner_id="$(
  docker compose exec -T n8n_db \
    psql -U n8n -d n8n -Atc 'SELECT id FROM "user" WHERE email IS NOT NULL ORDER BY "createdAt" ASC LIMIT 1;' \
    | tr -d '\r\n'
)"

if [[ -z "$owner_id" ]]; then
  echo "Could not find the n8n owner account." >&2
  exit 1
fi

source_name="tia_automation_scheduler.json"
source_path="${workflow_dir}/${source_name}"
workflow_id="tiaAutoSched0001"
tmp_dir="$(mktemp -d)"
trap 'rm -rf "$tmp_dir"' EXIT

python3 - "$source_path" "$tmp_dir/$source_name" <<'PY'
import json
import pathlib
import sys

source = pathlib.Path(sys.argv[1])
output = pathlib.Path(sys.argv[2])

if not source.is_file():
    raise SystemExit(f"Missing workflow template: {source}")

data = json.loads(source.read_text(encoding="utf-8"))
data["id"] = "tiaAutoSched0001"
expected_nodes = {
    "Tia Plan + Claim",
    "Tia Execute Automation",
    "Tia Clinic Sync Tick",
}
found = set()

for node in data.get("nodes", []):
    name = node.get("name")
    if name not in expected_nodes:
        continue
    if node.get("type") != "n8n-nodes-base.httpRequest":
        raise SystemExit(f"Expected HTTP Request node: {name}")

    params = node.setdefault("parameters", {})
    params.pop("authentication", None)
    params.pop("genericAuthType", None)
    params["sendHeaders"] = True
    params["headerParameters"] = {
        "parameters": [
            {
                "name": "X-Automation-Token",
                "value": "={{ $env.TIA_AUTOMATION_TOKEN }}",
            }
        ]
    }
    found.add(name)

missing = expected_nodes - found
if missing:
    raise SystemExit(f"Scheduler is missing expected Tia auth nodes: {sorted(missing)}")

output.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
print(f"Prepared {source.name}: {len(found)} Tia-authenticated HTTP nodes")
PY

workflow_exists() {
  local count
  count="$(
    docker compose exec -T n8n_db \
      psql -U n8n -d n8n -Atc \
      "SELECT COUNT(*) FROM workflow_entity WHERE id = '${workflow_id}';" \
      | tr -d '\r\n'
  )"
  [[ "$count" == "1" ]]
}

docker compose cp "$tmp_dir/$source_name" "n8n:/tmp/$source_name" >/dev/null

if workflow_exists; then
  echo "Updating existing scheduler: $workflow_id"
  docker compose exec -T --user node n8n \
    n8n import:workflow --input="/tmp/$source_name"
else
  echo "Creating scheduler for owner: $workflow_id"
  docker compose exec -T --user node n8n \
    n8n import:workflow --input="/tmp/$source_name" --userId="$owner_id"
fi

docker compose restart n8n >/dev/null

echo
echo "Tia automation scheduler authentication is wired into n8n. Raw token was not printed."
echo "WhatsApp transport credentials are intentionally not wired into Oracle n8n."
docker compose exec -T n8n_db \
  psql -U n8n -d n8n \
  -c "SELECT id, name, active FROM workflow_entity WHERE id = '${workflow_id}';"
