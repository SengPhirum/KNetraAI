#!/usr/bin/env sh
set -eu

if [ "$#" -ne 1 ]; then
  echo "Usage: docker/scripts/restore-postgres.sh backups/file.sql.gz"
  exit 1
fi

ROOT_DIR="$(CDPATH= cd -- "$(dirname -- "$0")/../.." && pwd)"
BACKUP_FILE="$1"

cd "$ROOT_DIR"
gzip -dc "$BACKUP_FILE" | docker compose --env-file docker/.env.production -f docker/docker-compose.yml exec -T postgres \
  sh -c 'psql -U "$POSTGRES_USER" "$POSTGRES_DB"'
