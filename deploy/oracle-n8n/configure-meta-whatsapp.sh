#!/usr/bin/env bash
set -euo pipefail

cd "$(dirname "${BASH_SOURCE[0]}")"

WABA_ID="${TIA_META_WABA_ID:-1088607350781750}"
OUTBOX_ID="tiaWAOutbox00001"
INBOUND_ID="tiaWAInbound0001"
SEND_CRED_ID="tiaMetaWhatsApi1"
TRIGGER_CRED_ID="tiaMetaWhatsTrig1"
SEND_CRED_NAME="Tia Meta WhatsApp API"
TRIGGER_CRED_NAME="Tia Meta WhatsApp Trigger"

for cmd in python3 curl; do
  command -v "$cmd" >/dev/null 2>&1 || {
    echo "$cmd is required on the Oracle host." >&2
    exit 1
  }
done

owner_id="$(
  docker compose exec -T n8n_db \
    psql -U n8n -d n8n -Atc 'SELECT id FROM "user" WHERE email IS NOT NULL ORDER BY "createdAt" ASC LIMIT 1;' \
    | tr -d '\r\n'
)"

if [[ -z "$owner_id" ]]; then
  echo "Could not find the n8n owner account." >&2
  exit 1
fi

read -r -s -p "Meta permanent API Access Token: " META_ACCESS_TOKEN
echo
read -r -s -p "Meta App ID: " META_APP_ID
echo
read -r -s -p "Meta App Secret: " META_APP_SECRET
echo

if [[ -z "$META_ACCESS_TOKEN" || -z "$META_APP_ID" || -z "$META_APP_SECRET" ]]; then
  echo "All three Meta values are required." >&2
  exit 1
fi

# App IDs are numeric and are sometimes copied with surrounding whitespace.
META_APP_ID="$(printf '%s' "$META_APP_ID" | tr -d '[:space:]')"
if [[ ! "$META_APP_ID" =~ ^[0-9]+$ ]]; then
  echo "Meta App ID must be numeric. Make sure you copied App ID, not Business ID or another identifier." >&2
  exit 1
fi

tmp_dir="$(mktemp -d)"
cleanup() {
  unset META_ACCESS_TOKEN META_APP_ID META_APP_SECRET
  rm -rf "$tmp_dir"
}
trap cleanup EXIT

print_meta_error() {
  local file="$1"
  python3 - "$file" <<'PY'
import json, pathlib, sys
path = pathlib.Path(sys.argv[1])
try:
    payload = json.loads(path.read_text(encoding="utf-8"))
except Exception:
    print("Meta did not return a readable JSON error.")
    raise SystemExit(0)
err = payload.get("error") if isinstance(payload, dict) else None
if not isinstance(err, dict):
    print("Meta returned an error without structured details.")
    raise SystemExit(0)
message = str(err.get("message") or "Unknown Meta error")
code = err.get("code")
type_ = err.get("type")
print(f"Meta error: {message}")
if type_ is not None:
    print(f"Meta error type: {type_}")
if code is not None:
    print(f"Meta error code: {code}")
PY
}

# Validate the WhatsApp API token against the configured WABA without printing secrets.
status="$(
  curl -sS -o "$tmp_dir/waba-check.json" -w '%{http_code}' \
    -H "Authorization: Bearer ${META_ACCESS_TOKEN}" \
    "https://graph.facebook.com/${WABA_ID}?fields=id" \
    || true
)"
if [[ ! "$status" =~ ^2 ]]; then
  echo "Meta API token validation failed for the configured WhatsApp Business Account (HTTP $status)." >&2
  print_meta_error "$tmp_dir/waba-check.json" >&2
  exit 1
fi

# Validate App ID + Secret using Meta's client-credentials exchange, discarding the returned app token.
status="$(
  curl -sS -o "$tmp_dir/app-check.json" -w '%{http_code}' -G \
    'https://graph.facebook.com/oauth/access_token' \
    --data-urlencode "client_id=${META_APP_ID}" \
    --data-urlencode "client_secret=${META_APP_SECRET}" \
    --data-urlencode 'grant_type=client_credentials' \
    || true
)"
if [[ ! "$status" =~ ^2 ]]; then
  echo "Meta App ID / App Secret validation failed (HTTP $status)." >&2
  print_meta_error "$tmp_dir/app-check.json" >&2
  echo "Open Meta for Developers -> My Apps -> select the WhatsApp app -> App settings -> Basic, then copy App ID and App Secret from that same app." >&2
  exit 1
fi

echo "Meta credentials validated."

auth_json="$tmp_dir/auth-values.json"
META_ACCESS_TOKEN="$META_ACCESS_TOKEN" \
META_APP_ID="$META_APP_ID" \
META_APP_SECRET="$META_APP_SECRET" \
WABA_ID="$WABA_ID" \
SEND_CRED_ID="$SEND_CRED_ID" \
TRIGGER_CRED_ID="$TRIGGER_CRED_ID" \
SEND_CRED_NAME="$SEND_CRED_NAME" \
TRIGGER_CRED_NAME="$TRIGGER_CRED_NAME" \
python3 - "$auth_json" <<'PY'
import json, os, pathlib, sys
out = pathlib.Path(sys.argv[1])
items = {
    "send": [{
        "id": os.environ["SEND_CRED_ID"],
        "name": os.environ["SEND_CRED_NAME"],
        "type": "whatsAppApi",
        "data": {
            "accessToken": os.environ["META_ACCESS_TOKEN"],
            "businessAccountId": os.environ["WABA_ID"],
        },
    }],
    "trigger": [{
        "id": os.environ["TRIGGER_CRED_ID"],
        "name": os.environ["TRIGGER_CRED_NAME"],
        "type": "whatsAppTriggerApi",
        "data": {
            "clientId": os.environ["META_APP_ID"],
            "clientSecret": os.environ["META_APP_SECRET"],
        },
    }],
}
for key, value in items.items():
    (out.parent / f"{key}-credential.json").write_text(
        json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
PY

credential_exists() {
  local credential_id="$1"
  local count
  count="$(
    docker compose exec -T n8n_db \
      psql -U n8n -d n8n -Atc \
      "SELECT COUNT(*) FROM credentials_entity WHERE id = '${credential_id}';" \
      | tr -d '\r\n'
  )"
  [[ "$count" == "1" ]]
}

import_credential() {
  local host_file="$1"
  local credential_id="$2"
  local container_file="/tmp/$(basename "$host_file")"

  docker compose cp "$host_file" "n8n:${container_file}" >/dev/null
  if credential_exists "$credential_id"; then
    echo "Updating existing n8n credential: $credential_id"
    docker compose exec -T --user node n8n \
      n8n import:credentials --input="$container_file"
  else
    echo "Creating n8n credential for owner: $credential_id"
    docker compose exec -T --user node n8n \
      n8n import:credentials --input="$container_file" --userId="$owner_id"
  fi
}

import_credential "$tmp_dir/send-credential.json" "$SEND_CRED_ID"
import_credential "$tmp_dir/trigger-credential.json" "$TRIGGER_CRED_ID"

export_workflow() {
  local workflow_id="$1"
  local filename="$2"
  docker compose exec -T --user node n8n \
    n8n export:workflow --id="$workflow_id" --output="/tmp/$filename" >/dev/null
  docker compose cp "n8n:/tmp/$filename" "$tmp_dir/$filename" >/dev/null
}

export_workflow "$OUTBOX_ID" "outbox.json"
export_workflow "$INBOUND_ID" "inbound.json"

SEND_CRED_ID="$SEND_CRED_ID" \
TRIGGER_CRED_ID="$TRIGGER_CRED_ID" \
SEND_CRED_NAME="$SEND_CRED_NAME" \
TRIGGER_CRED_NAME="$TRIGGER_CRED_NAME" \
python3 - "$tmp_dir/outbox.json" "$tmp_dir/inbound.json" <<'PY'
import json, os, pathlib, sys

def load_one(path: pathlib.Path):
    data = json.loads(path.read_text(encoding="utf-8"))
    if isinstance(data, list):
        if len(data) != 1:
            raise SystemExit(f"Expected one workflow in {path}")
        return data[0]
    return data

outbox_path = pathlib.Path(sys.argv[1])
inbound_path = pathlib.Path(sys.argv[2])
outbox = load_one(outbox_path)
inbound = load_one(inbound_path)

send_ref = {
    "id": os.environ["SEND_CRED_ID"],
    "name": os.environ["SEND_CRED_NAME"],
}
trigger_ref = {
    "id": os.environ["TRIGGER_CRED_ID"],
    "name": os.environ["TRIGGER_CRED_NAME"],
}

send_count = 0
for node in outbox.get("nodes", []):
    if node.get("type") == "n8n-nodes-base.whatsApp":
        node.setdefault("credentials", {})["whatsAppApi"] = send_ref
        send_count += 1

trigger_count = 0
for node in inbound.get("nodes", []):
    if node.get("type") == "n8n-nodes-base.whatsAppTrigger":
        node.setdefault("credentials", {})["whatsAppTriggerApi"] = trigger_ref
        node.setdefault("webhookId", "a8bf3e11-6fd1-4cf3-a2fc-3eae6a0c7ad1")
        trigger_count += 1

if send_count == 0:
    raise SystemExit("No WhatsApp send nodes found in outbox workflow")
if trigger_count != 1:
    raise SystemExit(f"Expected exactly one WhatsApp Trigger node, found {trigger_count}")

outbox_path.write_text(json.dumps(outbox, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
inbound_path.write_text(json.dumps(inbound, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
print(f"Wired Meta API credential to {send_count} WhatsApp send nodes.")
print("Wired Meta App credential to the WhatsApp Trigger node.")
PY

import_workflow_update() {
  local host_file="$1"
  local filename="$(basename "$host_file")"
  docker compose cp "$host_file" "n8n:/tmp/$filename" >/dev/null
  docker compose exec -T --user node n8n \
    n8n import:workflow --input="/tmp/$filename"
}

import_workflow_update "$tmp_dir/outbox.json"
import_workflow_update "$tmp_dir/inbound.json"

docker compose restart n8n >/dev/null

echo
echo "Meta WhatsApp credentials are configured and linked."
echo "WhatsApp workflows are intentionally still inactive."
docker compose exec -T n8n_db \
  psql -U n8n -d n8n \
  -c "SELECT id, name, active FROM workflow_entity WHERE id IN ('${OUTBOX_ID}','${INBOUND_ID}') ORDER BY name;"

echo
echo "Stored n8n credentials (secret data is encrypted and not displayed):"
docker compose exec -T n8n_db \
  psql -U n8n -d n8n \
  -c "SELECT id, name, type FROM credentials_entity WHERE id IN ('${SEND_CRED_ID}','${TRIGGER_CRED_ID}') ORDER BY name;"
