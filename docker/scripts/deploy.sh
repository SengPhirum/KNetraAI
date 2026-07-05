#!/usr/bin/env sh
set -eu

ROOT_DIR="$(CDPATH= cd -- "$(dirname -- "$0")/../.." && pwd)"
ENV_FILE="$ROOT_DIR/docker/.env.production"

if [ ! -f "$ENV_FILE" ]; then
  echo "Missing docker/.env.production"
  echo "Create it first: cp docker/.env.production.example docker/.env.production"
  exit 1
fi

cd "$ROOT_DIR"
docker compose --env-file docker/.env.production -f docker/docker-compose.yml up -d --build
