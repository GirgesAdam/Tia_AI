#!/usr/bin/env bash
set -euo pipefail

cd "$(dirname "${BASH_SOURCE[0]}")"

WORKFLOW_ID="tiaWAOutbox00001"
TMP_DIR="$(mktemp -d)"
trap 'rm -rf "$TMP_DIR"' EXIT

if ! command -v python3 >/dev/null 2>&1; then
  echo "python3 is required on the Oracle host." >&2
  exit 1
fi

# Export the currently configured workflow so Meta credentials and Tia headers stay intact.
docker compose exec -T --user node n8n \
  n8n export:workflow --id="$WORKFLOW_ID" --output=/tmp/tia-outbox-repair.json >/dev/null

docker compose cp \
  n8n:/tmp/tia-outbox-repair.json \
  "$TMP_DIR/outbox.json" >/dev/null

python3 - "$TMP_DIR/outbox.json" <<'PY'
import json
import pathlib
import sys

path = pathlib.Path(sys.argv[1])
raw = json.loads(path.read_text(encoding="utf-8"))
wrapped = isinstance(raw, list)
if wrapped:
    if len(raw) != 1:
        raise SystemExit("Expected exactly one exported workflow")
    workflow = raw[0]
else:
    workflow = raw

nodes = workflow.setdefault("nodes", [])
connections = workflow.setdefault("connections", {})

builders = {
    "Tia Record Text Result": {
        "name": "Build Text Dispatch Result",
        "id": "tia-build-text-dispatch-result",
        "position": [540, 300],
    },
    "Tia Record Template Result": {
        "name": "Build Template Dispatch Result",
        "id": "tia-build-template-dispatch-result",
        "position": [680, -40],
    },
}

code = """const inputs = $input.all();
return inputs.map((item, index) => {
  const data = item.json ?? {};
  const providerMessageId = data?.messages?.[0]?.id ?? data?.id ?? null;
  const sent = Boolean(providerMessageId);
  const error = sent
    ? null
    : (data?.error?.message
      ?? data?.error?.description
      ?? data?.message
      ?? data?.errorDescription
      ?? 'WhatsApp send failed in n8n');

  return {
    json: {
      status: sent ? 'sent' : 'failed',
      provider_message_id: providerMessageId,
      error,
      retry_after_seconds: sent ? null : 30,
      metadata: {
        transport: 'n8n',
        provider: 'meta_cloud',
      },
    },
    pairedItem: { item: index },
  };
});"""

node_by_name = {node.get("name"): node for node in nodes}

for result_name, builder in builders.items():
    result_node = node_by_name.get(result_name)
    if result_node is None:
        raise SystemExit(f"Missing result node: {result_name}")

    params = result_node.setdefault("parameters", {})
    params["sendBody"] = True
    params["specifyBody"] = "json"
    params["jsonBody"] = "={{ $json }}"

    builder_name = builder["name"]
    existing_builder = node_by_name.get(builder_name)
    if existing_builder is None:
        existing_builder = {
            "parameters": {"jsCode": code},
            "type": "n8n-nodes-base.code",
            "typeVersion": 2,
            "position": builder["position"],
            "id": builder["id"],
            "name": builder_name,
        }
        nodes.append(existing_builder)
        node_by_name[builder_name] = existing_builder
    else:
        existing_builder.setdefault("parameters", {})["jsCode"] = code

    redirected = 0
    for source_name, source_connections in list(connections.items()):
        if source_name == builder_name:
            continue
        for output in source_connections.get("main", []):
            for edge in output:
                if edge.get("node") == result_name:
                    edge["node"] = builder_name
                    redirected += 1

    connections[builder_name] = {
        "main": [[{"node": result_name, "type": "main", "index": 0}]]
    }

    if redirected == 0 and builder_name not in connections:
        raise SystemExit(f"Could not wire result builder for {result_name}")

output = [workflow] if wrapped else workflow
path.write_text(json.dumps(output, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
print("Replaced complex result expressions with deterministic Code nodes.")
PY

docker compose cp "$TMP_DIR/outbox.json" n8n:/tmp/tia-outbox-repaired.json >/dev/null

docker compose exec -T --user node n8n \
  n8n import:workflow --input=/tmp/tia-outbox-repaired.json

echo "Repaired WhatsApp outbox result recording workflow."
