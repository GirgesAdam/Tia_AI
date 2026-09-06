#!/usr/bin/env bash
set -euo pipefail

cd "$(dirname "${BASH_SOURCE[0]}")"
umask 077

BACKUP_ROOT="${TIA_BACKUP_DIR:-$PWD/backups/production}"
RETENTION_DAYS="${TIA_BACKUP_RETENTION_DAYS:-14}"
STAMP="$(date -u +%Y%m%dT%H%M%SZ)"
TMP_DIR="$BACKUP_ROOT/.tmp-$STAMP"
ARCHIVE="$BACKUP_ROOT/tia-production-$STAMP.tar.gz"

cleanup() {
  rm -rf "$TMP_DIR"
}
trap cleanup EXIT

mkdir -p "$BACKUP_ROOT" "$TMP_DIR"
chmod 700 "$BACKUP_ROOT" "$TMP_DIR"

echo "Checking production containers..."
docker compose ps --status running

echo "Backing up n8n PostgreSQL..."
docker compose exec -T n8n_db \
  pg_dump -U n8n -d n8n --format=custom --no-owner --no-acl \
  > "$TMP_DIR/n8n-postgres.dump"

echo "Backing up n8n persistent data..."
docker compose exec -T n8n \
  sh -c 'tar -C /home/node -czf - .n8n' \
  > "$TMP_DIR/n8n-data.tar.gz"

# These files contain the encryption key/runtime tokens required to decrypt
# credentials and reconnect Tia after disaster recovery. They remain only in
# the local, mode-600 backup archive and are never committed to Git.
if [[ -f .env ]]; then
  cp .env "$TMP_DIR/runtime.env"
fi
if [[ -f .runtime-secrets/tia-runtime.env ]]; then
  cp .runtime-secrets/tia-runtime.env "$TMP_DIR/tia-runtime.env"
fi

{
  echo "created_at_utc=$STAMP"
  echo "git_commit=$(git rev-parse HEAD 2>/dev/null || echo unknown)"
  echo "hostname=$(hostname)"
  echo "n8n_host=$(sed -n 's/^N8N_HOST=//p' .env 2>/dev/null | head -1)"
  echo "docker_compose_version=$(docker compose version --short 2>/dev/null || echo unknown)"
} > "$TMP_DIR/manifest.txt"

(
  cd "$TMP_DIR"
  sha256sum ./* > SHA256SUMS
)

tar -C "$TMP_DIR" -czf "$ARCHIVE" .
chmod 600 "$ARCHIVE"

# Validate the archive before reporting success.
tar -tzf "$ARCHIVE" >/dev/null

# Keep recent backups locally; old archives are removed automatically.
find "$BACKUP_ROOT" -maxdepth 1 -type f -name 'tia-production-*.tar.gz' \
  -mtime "+$RETENTION_DAYS" -delete

SIZE="$(du -h "$ARCHIVE" | awk '{print $1}')"

echo
echo "Backup complete."
echo "Archive: $ARCHIVE"
echo "Size: $SIZE"
echo "Retention: $RETENTION_DAYS days"
echo "Permissions: $(stat -c '%a' "$ARCHIVE")"
echo
echo "Contents:"
tar -tzf "$ARCHIVE" | sed -n '1,20p'
