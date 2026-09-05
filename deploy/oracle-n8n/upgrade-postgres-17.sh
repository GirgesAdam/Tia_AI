#!/usr/bin/env bash
set -euo pipefail

cd "$(dirname "${BASH_SOURCE[0]}")"

if [[ ! -f .env ]]; then
  echo "Missing .env" >&2
  exit 1
fi

if ! docker compose ps n8n_db >/dev/null 2>&1; then
  echo "n8n_db service is not available" >&2
  exit 1
fi

mkdir -p backups
stamp="$(date +%Y%m%d-%H%M%S)"
backup="backups/n8n-postgres16-${stamp}.sql"

container_id="$(docker compose ps -q n8n_db)"
if [[ -z "$container_id" ]]; then
  echo "n8n_db container is not running" >&2
  exit 1
fi

volume_name="$(docker inspect "$container_id" --format '{{range .Mounts}}{{if eq .Destination "/var/lib/postgresql/data"}}{{.Name}}{{end}}{{end}}')"
if [[ -z "$volume_name" ]]; then
  echo "Could not identify the n8n PostgreSQL data volume" >&2
  exit 1
fi

echo "Backing up current n8n database to $backup ..."
docker compose exec -T n8n_db pg_dump -U n8n -d n8n > "$backup"

if [[ ! -s "$backup" ]]; then
  echo "Backup is empty; refusing to continue" >&2
  exit 1
fi

echo "Stopping n8n before database migration..."
docker compose stop n8n

echo "Stopping and removing the old PostgreSQL container..."
docker compose stop n8n_db
docker compose rm -f n8n_db

echo "Removing old PostgreSQL 16 data volume: $volume_name"
docker volume rm "$volume_name"

echo "Starting fresh PostgreSQL 17..."
docker compose pull n8n_db
docker compose up -d n8n_db

for _ in $(seq 1 30); do
  status="$(docker inspect "$(docker compose ps -q n8n_db)" --format '{{if .State.Health}}{{.State.Health.Status}}{{else}}{{.State.Status}}{{end}}' 2>/dev/null || true)"
  if [[ "$status" == "healthy" ]]; then
    break
  fi
  sleep 2
done

status="$(docker inspect "$(docker compose ps -q n8n_db)" --format '{{if .State.Health}}{{.State.Health.Status}}{{else}}{{.State.Status}}{{end}}')"
if [[ "$status" != "healthy" ]]; then
  echo "PostgreSQL 17 did not become healthy" >&2
  docker compose logs --tail=100 n8n_db >&2
  exit 1
fi

echo "Restoring n8n database into PostgreSQL 17..."
docker compose exec -T n8n_db psql -v ON_ERROR_STOP=1 -U n8n -d n8n < "$backup"

echo "Starting n8n and Caddy..."
docker compose up -d n8n caddy

sleep 5

echo
echo "Database version:"
docker compose exec -T n8n_db psql -U n8n -d n8n -Atc 'show server_version;'

echo
echo "Owner users:"
docker compose exec -T n8n_db psql -U n8n -d n8n -Atc 'select count(*) from "user" where email is not null;'

echo
echo "Tia workflows:"
docker compose exec -T n8n_db psql -U n8n -d n8n -c "select id, name, active from workflow_entity where id in ('tiaAutoSched0001','tiaWAInbound0001','tiaWAOutbox00001') order by name;"

echo
echo "Runtime status:"
docker compose ps

echo
echo "PostgreSQL 17 migration completed. Backup retained at: $backup"
