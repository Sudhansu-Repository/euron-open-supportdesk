#!/usr/bin/env bash
# Run the API integration suite under every backend combination the app supports:
#
#   storage: local disk         | Amazon S3 (Floci)
#   keys:    local AES-GCM key  | AWS KMS (Floci)
#   redis:   on (shared caches, counters, fan-out) | off (in-process, one replica)
#
# Needs Floci with the local-floci Terraform applied (make up). Each combination gets its
# own test database, so a run never reuses another's state.
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
ENV_FILE="$ROOT/deploy/compose/.env"
port() { local v; v="$(grep -s "^$1=" "$ENV_FILE" | cut -d= -f2 || true)"; echo "${v:-$2}"; }
FLOCI_URL="http://localhost:$(port SD_FLOCI_PORT 4866)"
PG="postgresql+asyncpg://supportdesk:supportdesk@localhost:$(port SD_PG_PORT 4842)"
REDIS="redis://localhost:$(port SD_REDIS_PORT 4879)/14"

if ! curl -sf -o /dev/null "$FLOCI_URL/"; then
  echo "Floci is not reachable at $FLOCI_URL. Start the stack first: make up" >&2
  exit 1
fi
"$ROOT/scripts/test-db.sh"

export AWS_ACCESS_KEY_ID=test AWS_SECRET_ACCESS_KEY=test AWS_REGION=us-east-1
export TEST_AWS_ENDPOINT="$FLOCI_URL"
failed=()
runs=0
for storage in local s3; do
  for keys in local kms; do
    for redis in on off; do
      runs=$((runs + 1))
      echo
      echo "== storage=$storage keys=$keys redis=$redis"
      redis_url=""; [[ "$redis" == on ]] && redis_url="$REDIS"
      if ! (cd "$ROOT/apps/api" && TEST_STORAGE=$storage TEST_KEY_MODE=$keys \
            TEST_DATABASE_URL="$PG/supportdesk_test_matrix_${storage}_${keys}_${redis}" \
            TEST_REDIS_URL="$redis_url" \
            uv run pytest tests/integration -m integration -q -p no:warnings -rf); then
        failed+=("storage=$storage keys=$keys redis=$redis")
      fi
    done
  done
done
echo
if ((${#failed[@]})); then
  printf 'matrix: FAILED for %s\n' "${failed[@]}"
  exit 1
fi
echo "matrix: all $runs combinations passed"
