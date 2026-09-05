#!/usr/bin/env bash
set -euo pipefail

cd "$(dirname "${BASH_SOURCE[0]}")"

if [[ ! -f .env ]]; then
  echo "Missing deploy/oracle-n8n/.env. Copy .env.example to .env and fill production values first." >&2
  exit 1
fi

set -a
# shellcheck disable=SC1091
source ./.env
set +a

required_vars=(N8N_HOST TIA_API_BASE_URL N8N_DB_PASSWORD N8N_ENCRYPTION_KEY)
for name in "${required_vars[@]}"; do
  value="${!name:-}"
  if [[ -z "$value" ]]; then
    echo "Missing required variable: $name" >&2
    exit 1
  fi
  if [[ "$value" == *"example.com"* || "$value" == replace-with-* ]]; then
    echo "Refusing production start: $name still contains an example/placeholder value." >&2
    exit 1
  fi
done

if [[ "$TIA_API_BASE_URL" != https://* ]]; then
  echo "TIA_API_BASE_URL must use HTTPS." >&2
  exit 1
fi

if [[ "$TIA_API_BASE_URL" == */ ]]; then
  echo "TIA_API_BASE_URL must not end with a trailing slash." >&2
  exit 1
fi

if ! command -v docker >/dev/null 2>&1; then
  echo "Docker is not installed or not on PATH." >&2
  exit 1
fi

if ! docker compose version >/dev/null 2>&1; then
  echo "Docker Compose plugin is not available." >&2
  exit 1
fi

echo "Validating Docker Compose configuration..."
docker compose config --quiet

echo "Pulling pinned production images..."
docker compose pull

echo "Starting Oracle n8n production runtime..."
docker compose up -d

echo
docker compose ps

echo
echo "Runtime started. Check HTTPS after DNS resolves: https://${N8N_HOST}"
