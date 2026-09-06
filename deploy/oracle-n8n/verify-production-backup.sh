#!/usr/bin/env bash
set -euo pipefail

cd "$(dirname "${BASH_SOURCE[0]}")"
umask 077

BACKUP_ROOT="${TIA_BACKUP_DIR:-$PWD/backups/production}"
ARCHIVE="${1:-}"

if [[ -z "$ARCHIVE" ]]; then
  ARCHIVE="$(find "$BACKUP_ROOT" -maxdepth 1 -type f -name 'tia-production-*.tar.gz' -printf '%T@ %p\n' 2>/dev/null | sort -nr | head -1 | cut -d' ' -f2-)"
fi

if [[ -z "$ARCHIVE" || ! -f "$ARCHIVE" ]]; then
  echo "No production backup archive found." >&2
  exit 1
fi

TMP_DIR="$(mktemp -d)"
VERIFY_CONTAINER="tia-n8n-backup-verify-$$"
VERIFY_NETWORK="tia-n8n-backup-verify-$$"
VERIFY_PASSWORD="$(openssl rand -hex 24)"

cleanup() {
  docker rm -f "$VERIFY_CONTAINER" >/dev/null 2>&1 || true
  docker network rm "$VERIFY_NETWORK" >/dev/null 2>&1 || true
  rm -rf "$TMP_DIR"
}
trap cleanup EXIT

chmod 700 "$TMP_DIR"

echo "Verifying archive: $ARCHIVE"
tar -xzf "$ARCHIVE" -C "$TMP_DIR"

for required in n8n-postgres.dump n8n-data.tar.gz runtime.env tia-runtime.env manifest.txt SHA256SUMS; do
  if [[ ! -s "$TMP_DIR/$required" ]]; then
    echo "Backup is missing required file: $required" >&2
    exit 1
  fi
done

echo "Checking backup checksums..."
(
  cd "$TMP_DIR"
  sha256sum -c SHA256SUMS
)

echo "Checking n8n data archive..."
tar -tzf "$TMP_DIR/n8n-data.tar.gz" >/dev/null

if ! grep -Eq '^N8N_ENCRYPTION_KEY=.+' "$TMP_DIR/runtime.env"; then
  echo "Backup runtime.env is missing N8N_ENCRYPTION_KEY." >&2
  exit 1
fi
if ! grep -Eq '^TIA_(AUTOMATION|CHANNEL)_TOKEN=.+' "$TMP_DIR/tia-runtime.env"; then
  echo "Backup tia-runtime.env does not contain the Tia runtime tokens." >&2
  exit 1
fi

echo "Checking PostgreSQL dump structure..."
docker run --rm --entrypoint pg_restore \
  -v "$TMP_DIR:/backup:ro" \
  postgres:17-alpine \
  --list /backup/n8n-postgres.dump >/dev/null

echo "Restoring PostgreSQL dump into an isolated temporary Postgres 17 container..."
docker network create "$VERIFY_NETWORK" >/dev/null
docker run -d \
  --name "$VERIFY_CONTAINER" \
  --network "$VERIFY_NETWORK" \
  -e POSTGRES_DB=n8n_verify \
  -e POSTGRES_USER=n8n \
  -e POSTGRES_PASSWORD="$VERIFY_PASSWORD" \
  postgres:17-alpine >/dev/null

for _ in $(seq 1 30); do
  if docker exec "$VERIFY_CONTAINER" pg_isready -U n8n -d n8n_verify >/dev/null 2>&1; then
    break
  fi
  sleep 1
done

if ! docker exec "$VERIFY_CONTAINER" pg_isready -U n8n -d n8n_verify >/dev/null 2>&1; then
  echo "Temporary PostgreSQL did not become ready." >&2
  exit 1
fi

docker exec -i "$VERIFY_CONTAINER" \
  pg_restore -U n8n -d n8n_verify --no-owner --no-acl \
  < "$TMP_DIR/n8n-postgres.dump"

WORKFLOW_COUNT="$(docker exec "$VERIFY_CONTAINER" psql -U n8n -d n8n_verify -Atc 'SELECT count(*) FROM workflow_entity;')"
CREDENTIAL_COUNT="$(docker exec "$VERIFY_CONTAINER" psql -U n8n -d n8n_verify -Atc 'SELECT count(*) FROM credentials_entity;')"
ACTIVE_TIA_COUNT="$(docker exec "$VERIFY_CONTAINER" psql -U n8n -d n8n_verify -Atc \"SELECT count(*) FROM workflow_entity WHERE id IN ('tiaAutoSched0001','tiaWAInbound0001','tiaWAOutbox00001') AND active = true;\")"

if [[ "$WORKFLOW_COUNT" -lt 3 ]]; then
  echo "Restored backup has too few workflows: $WORKFLOW_COUNT" >&2
  exit 1
fi
if [[ "$CREDENTIAL_COUNT" -lt 1 ]]; then
  echo "Restored backup has no credentials." >&2
  exit 1
fi
if [[ "$ACTIVE_TIA_COUNT" -ne 3 ]]; then
  echo "Expected 3 active Tia production workflows in restored backup; found $ACTIVE_TIA_COUNT." >&2
  exit 1
fi

echo
echo "Restore verification passed."
echo "Workflows restored: $WORKFLOW_COUNT"
echo "Credentials restored: $CREDENTIAL_COUNT"
echo "Active Tia workflows restored: $ACTIVE_TIA_COUNT/3"
echo "Production containers/data were not modified."
