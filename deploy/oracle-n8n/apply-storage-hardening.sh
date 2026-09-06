#!/usr/bin/env bash
set -euo pipefail

cd "$(dirname "${BASH_SOURCE[0]}")"

if [[ "${EUID}" -ne 0 ]]; then
  echo "Run this script with sudo." >&2
  exit 1
fi

echo "Validating Docker Compose configuration..."
docker compose config >/dev/null

echo "Taking a fresh production backup before container recreation..."
bash ./backup-production.sh >/dev/null

echo "Recreating containers with bounded Docker log rotation and explicit n8n execution pruning..."
docker compose up -d --force-recreate n8n_db n8n caddy

for _ in $(seq 1 30); do
  if docker compose exec -T n8n_db pg_isready -U n8n -d n8n >/dev/null 2>&1; then
    break
  fi
  sleep 1
done

if ! docker compose exec -T n8n_db pg_isready -U n8n -d n8n >/dev/null 2>&1; then
  echo "PostgreSQL did not become ready after recreation." >&2
  exit 1
fi

sleep 8
bash ./healthcheck-production.sh

echo
echo "Storage hardening applied."
echo "Docker log rotation: max 10 MB x 3 files per container, compressed rotations."
echo "n8n finished execution retention: 14 days, max 10,000 executions."
echo "A fresh backup was created before recreation."
