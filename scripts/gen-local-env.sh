#!/usr/bin/env bash
# Write deploy/compose/.env with random, local-only secrets (once; never overwrites).
set -euo pipefail
f="$(cd "$(dirname "$0")/.." && pwd)/deploy/compose/.env"
if [[ -f "$f" ]]; then
  echo "deploy/compose/.env exists (delete it to regenerate)"
  exit 0
fi
rand() { openssl rand -base64 48 | tr -d '/+=\n' | cut -c1-"$1"; }
umask 077
# SESSION_SECRET and TOKEN_PEPPER must differ (the API refuses to boot otherwise);
# independent draws of 64 characters always do. The demo password is the published login
# of the seeded Lumen demo company (`make demo`), not a secret.
cat > "$f" <<ENV
SESSION_SECRET=$(rand 64)
TOKEN_PEPPER=$(rand 64)
LOCAL_MASTER_KEY=$(rand 64)
SD_DEMO_PASSWORD=${SD_DEMO_PASSWORD:-Demo-Pass-2026}
ENV
echo "wrote deploy/compose/.env"
