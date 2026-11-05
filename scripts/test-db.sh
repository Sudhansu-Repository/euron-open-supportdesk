#!/usr/bin/env bash
# Make sure Postgres (pgvector) and Redis are reachable for the integration suite. Reuses
# the Compose services when the stack is up; otherwise starts just those two. Tests never
# use a host-installed Postgres or Redis.
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
ENV_FILE="$ROOT/deploy/compose/.env"
port() { grep -s "^$1=" "$ENV_FILE" | cut -d= -f2 || true; }
PG_PORT="${SD_PG_PORT:-$(port SD_PG_PORT)}"; PG_PORT="${PG_PORT:-4842}"
REDIS_PORT="${SD_REDIS_PORT:-$(port SD_REDIS_PORT)}"; REDIS_PORT="${REDIS_PORT:-4879}"

ready() { (exec 3<>"/dev/tcp/127.0.0.1/$1") 2>/dev/null; }

if ready "$PG_PORT" && ready "$REDIS_PORT"; then
  exit 0
fi
"$ROOT/scripts/gen-local-env.sh" >/dev/null
docker compose --env-file "$ENV_FILE" -f "$ROOT/deploy/compose/compose.yaml" \
  up -d --wait postgres redis
