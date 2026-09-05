#!/usr/bin/env bash
set -euo pipefail

cd "$(dirname "${BASH_SOURCE[0]}")"

repo_root="$(cd ../.. && pwd)"
workflow_dir="${repo_root}/n8n/workflows"
secrets_file=".runtime-secrets/tia-runtime.env"

if [[ ! -f "$secrets_file" ]]; then
  echo "Missing $secrets_file. Generate the Oracle runtime tokens first." >&2
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

docker compose exec -T n8n sh -lc '
  test -n "$TIA_AUTOMATION_TOKEN" && test -n "$TIA_CHANNEL_TOKEN"
' || {
  echo "n8n did not receive the Tia runtime token environment variables." >&2
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

tmp_dir="$(mktemp -d)"
trap 'rm -rf "$tmp_dir"' EXIT

python3 - "$workflow_dir" "$tmp_dir" <<'PY'
import json
import pathlib
import sys

workflow_dir = pathlib.Path(sys.argv[1])
tmp_dir = pathlib.Path(sys.argv[2])

configs = {
    "tia_automation_scheduler.json": {
        "id": "tiaAutoSched0001",
        "header": "X-Automation-Token",
        "env": "TIA_AUTOMATION_TOKEN",
        "nodes": {
            "Tia Plan + Claim",
            "Tia Execute Automation",
            "Tia Clinic Sync Tick",
        },
    },
    "tia_whatsapp_outbox_worker.json": {
        "id": "tiaWAOutbox00001",
        "header": "X-Channel-Token",
        "env": "TIA_CHANNEL_TOKEN",
        "nodes": {
            "Tia Claim Outbox",
            "Tia Record Template Result",
            "Tia Record Text Result",
        },
    },
    "tia_whatsapp_inbound_status.json": {
        "id": "tiaWAInbound0001",
        "header": "X-Channel-Token",
        "env": "TIA_CHANNEL_TOKEN",
        "nodes": {
            "Tia Accept Inbound",
            "Tia Process With AI",
            "Tia Record Delivery Status",
        },
    },
}

for filename, config in configs.items():
    source = workflow_dir / filename
    if not source.is_file():
        raise SystemExit(f"Missing workflow template: {source}")

    data = json.loads(source.read_text(encoding="utf-8"))
    data["id"] = config["id"]
    found = set()

    for node in data.get("nodes", []):
        name = node.get("name")
        if name not in config["nodes"]:
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
                    "name": config["header"],
                    "value": f"={{ $env.{config['env']} }}",
                }
            ]
        }
        found.add(name)

    missing = config["nodes"] - found
    if missing:
        raise SystemExit(
            f"Workflow {filename} is missing expected Tia auth nodes: {sorted(missing)}"
        )

    output = tmp_dir / filename
    output.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"Prepared {filename}: {len(found)} Tia-authenticated HTTP nodes")
PY

import_one() {
  local filename="$1"
  docker compose cp "$tmp_dir/$filename" "n8n:/tmp/$filename" >/dev/null
  docker compose exec -T --user node n8n \
    n8n import:workflow --input="/tmp/$filename" --userId="$owner_id"
}

import_one "tia_automation_scheduler.json"
import_one "tia_whatsapp_outbox_worker.json"
import_one "tia_whatsapp_inbound_status.json"

docker compose restart n8n >/dev/null

echo
echo "Tia runtime authentication is wired into n8n. Raw tokens were not printed."
echo "Workflows remain inactive until WhatsApp/Meta credentials are configured:"
docker compose exec -T n8n_db \
  psql -U n8n -d n8n \
  -c "SELECT id, name, active FROM workflow_entity WHERE id IN ('tiaAutoSched0001','tiaWAOutbox00001','tiaWAInbound0001') ORDER BY name;"
